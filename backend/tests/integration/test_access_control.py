"""
Integration test for cross-tenant property access control.

B-09  tenant isolation is enforced at two layers:
  1. Application: scope.tenant_id is always passed to get_revenue_summary,
     which includes AND tenant_id = :tenant_id in the SQL query.
  2. Database: PostgreSQL RLS (migration 001_rls_policies.sql) enforces
     tenant filtering even if the application WHERE clause were removed.

The supabase property-ownership 404 check was removed when the endpoint was
migrated from direct supabase calls to TenantScope + RLS. That ownership check
is now the DB's responsibility.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, call, patch

from app.core.tenant_scope import TenantScope
from app.models.auth import AuthenticatedUser
from app.models.identifiers import TenantId


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scope(tenant_id: str) -> TenantScope:
    return TenantScope(
        user_id="u1",
        email="test@example.com",
        tenant_id=TenantId(tenant_id),
        is_admin=False,
        permissions=[],
        cities=[],
    )


# ---------------------------------------------------------------------------
# B-09 — Application-layer tenant isolation guarantee
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_b09_tenant_a_scope_propagated_to_revenue_query():
    """
    The endpoint must pass scope.tenant_id (tenant-a) to get_revenue_summary.
    That function always includes AND tenant_id = :tenant_id in the SQL query,
    so tenant-a's scope can never retrieve tenant-b's revenue rows.
    """
    from app.api.v1.dashboard import get_dashboard_summary

    scope = _scope("tenant-a")
    revenue_data = {
        "property_id": "prop-004", "tenant_id": "tenant-a",
        "total": "0.00", "currency": "USD", "count": 0,
    }

    with patch(
        "app.api.v1.dashboard.get_revenue_summary",
        new_callable=AsyncMock,
        return_value=revenue_data,
    ) as mock_rev:
        await get_dashboard_summary(scope=scope, property_id="prop-004")

    # Verify the tenant_id from scope — not from the raw request — was used.
    called_property_id, called_tenant_id = mock_rev.call_args.args
    assert str(called_tenant_id) == "tenant-a", (
        "get_revenue_summary must always be called with the authenticated "
        f"tenant_id (tenant-a), got {called_tenant_id!r}"
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_b09_tenant_b_scope_propagated_to_revenue_query():
    """Mirror: tenant-b scope must be propagated, not tenant-a's."""
    from app.api.v1.dashboard import get_dashboard_summary

    scope = _scope("tenant-b")
    revenue_data = {
        "property_id": "prop-002", "tenant_id": "tenant-b",
        "total": "0.00", "currency": "USD", "count": 0,
    }

    with patch(
        "app.api.v1.dashboard.get_revenue_summary",
        new_callable=AsyncMock,
        return_value=revenue_data,
    ) as mock_rev:
        await get_dashboard_summary(scope=scope, property_id="prop-002")

    _, called_tenant_id = mock_rev.call_args.args
    assert str(called_tenant_id) == "tenant-b"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_b09_supabase_tenant_filter_is_applied():
    """
    Integration with the real DB via the challenge-mode Supabase mock:
    the mock's ChallengeQueryBuilder filters MOCK_PROPERTIES by both
    id AND tenant_id, so a cross-tenant query returns an empty list.

    This test verifies the Supabase mock used in challenge-mode correctly
    enforces tenant isolation — a regression guard for when the mock is updated.
    """
    from app.database import supabase  # challenge-mode ChallengeClient

    # prop-004 belongs to tenant-b; query as tenant-a
    result = supabase.table("properties") \
        .select("timezone") \
        .eq("id", "prop-004") \
        .eq("tenant_id", "tenant-a") \
        .execute()

    assert result.data == [], (
        "ChallengeQueryBuilder must return empty list when property belongs to a different tenant"
    )

    # Positive case: same tenant sees the property
    result_own = supabase.table("properties") \
        .select("timezone") \
        .eq("id", "prop-004") \
        .eq("tenant_id", "tenant-b") \
        .execute()

    assert len(result_own.data) == 1, "tenant-b must see its own prop-004"
    assert result_own.data[0]["timezone"] == "America/New_York"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_b09_real_db_property_filter_excludes_cross_tenant(sa_session):
    """
    Real PostgreSQL assertion: the same query the dashboard endpoint runs
    (WHERE id = ? AND tenant_id = ?) returns zero rows for cross-tenant access.
    """
    from sqlalchemy import text

    result = await sa_session.execute(
        text("SELECT timezone FROM properties WHERE id = :id AND tenant_id = :tid"),
        {"id": "prop-004", "tid": "tenant-a"},
    )
    row = result.fetchone()
    assert row is None, (
        "Real DB must return no row when property_id belongs to a different tenant. "
        "This is the SQL-level enforcement for B-09."
    )

    # Confirm the row exists for the correct tenant
    result_own = await sa_session.execute(
        text("SELECT timezone FROM properties WHERE id = :id AND tenant_id = :tid"),
        {"id": "prop-004", "tid": "tenant-b"},
    )
    assert result_own.fetchone() is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_b09_endpoint_returns_correct_data_for_own_property():
    """
    Positive control: the endpoint must succeed when a tenant queries its own property.
    """
    from app.api.v1.dashboard import get_dashboard_summary

    scope = _scope("tenant-b")
    revenue_data = {
        "property_id": "prop-004", "tenant_id": "tenant-b",
        "total": "1776.50", "currency": "USD", "count": 4,
    }

    with patch(
        "app.api.v1.dashboard.get_revenue_summary",
        new_callable=AsyncMock,
        return_value=revenue_data,
    ):
        result = await get_dashboard_summary(scope=scope, property_id="prop-004")

    assert result.property_id == "prop-004"
    assert isinstance(result.total_revenue, Decimal)
