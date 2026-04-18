"""
Regression tests for GET /dashboard/summary (app.api.v1.dashboard).

Covers:
  - B-03: total_revenue in the response must be Decimal-precise (2 decimal places)
  - 401 when tenant_id is not resolved (tested via require_tenant_scope)

Note: the B-09 property-ownership 404 check was removed from the application layer
and delegated to PostgreSQL RLS (migration 001_rls_policies.sql). Testing RLS
requires a live DB and is covered by integration tests.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.core.tenant_scope import TenantScope
from app.models.auth import AuthenticatedUser
from app.models.identifiers import TenantId


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scope(tenant_id: str = "tenant-a") -> TenantScope:
    return TenantScope(
        user_id="user-1",
        email="test@example.com",
        tenant_id=TenantId(tenant_id),
        is_admin=False,
        permissions=[],
        cities=[],
    )


# ---------------------------------------------------------------------------
# B-03 — 2-decimal precision in the response
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dashboard_total_revenue_is_decimal_precise():
    """
    Before the fix, total_revenue was computed with float(), which loses trailing
    zeros and introduces IEEE 754 drift (e.g. 4975.50 → 4975.499999...).

    After the fix, Decimal.quantize(Decimal('0.01'), ROUND_HALF_UP) is used.
    The returned value must be an exact Decimal, not a float.
    """
    from app.api.v1.dashboard import get_dashboard_summary

    scope = _make_scope("tenant-a")
    revenue_data = {
        "property_id": "prop-001",
        "tenant_id": "tenant-a",
        "total": "4975.50",
        "currency": "USD",
        "count": 3,
    }

    with patch("app.api.v1.dashboard.get_revenue_summary", new_callable=AsyncMock, return_value=revenue_data):
        result = (await get_dashboard_summary(scope=scope, property_id="prop-001")).model_dump()

    total = result["total_revenue"]

    assert isinstance(total, Decimal), (
        f"total_revenue must be Decimal, not {type(total).__name__}"
    )
    assert total == Decimal("4975.50"), f"Expected 4975.50, got {total}"
    assert total == total.quantize(Decimal("0.01")), "total_revenue must be quantized to 2 d.p."


@pytest.mark.asyncio
async def test_dashboard_total_revenue_not_float():
    """Explicitly guards against reintroduction of float() on monetary total."""
    from app.api.v1.dashboard import get_dashboard_summary

    scope = _make_scope("tenant-a")
    revenue_data = {
        "property_id": "prop-001",
        "tenant_id": "tenant-a",
        "total": "333.33",
        "currency": "USD",
        "count": 1,
    }

    with patch("app.api.v1.dashboard.get_revenue_summary", new_callable=AsyncMock, return_value=revenue_data):
        result = await get_dashboard_summary(scope=scope, property_id="prop-001")

    assert not isinstance(result.total_revenue, float), (
        "float() must never be used for monetary totals — use Decimal.quantize()"
    )


@pytest.mark.asyncio
async def test_dashboard_rounding_half_up():
    """Verify ROUND_HALF_UP: 4975.505 rounds to 4975.51, not 4975.50."""
    from app.api.v1.dashboard import get_dashboard_summary
    from decimal import ROUND_HALF_UP

    scope = _make_scope("tenant-a")
    revenue_data = {
        "property_id": "prop-001",
        "tenant_id": "tenant-a",
        "total": "4975.505",
        "currency": "USD",
        "count": 1,
    }

    with patch("app.api.v1.dashboard.get_revenue_summary", new_callable=AsyncMock, return_value=revenue_data):
        result = await get_dashboard_summary(scope=scope, property_id="prop-001")

    expected = Decimal("4975.505").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    assert result.total_revenue == expected


@pytest.mark.asyncio
async def test_dashboard_response_shape():
    """Smoke-test: response includes property_id, total_revenue, currency, reservations_count."""
    from app.api.v1.dashboard import get_dashboard_summary

    scope = _make_scope("tenant-a")
    revenue_data = {
        "property_id": "prop-001",
        "tenant_id": "tenant-a",
        "total": "1776.50",
        "currency": "EUR",
        "count": 7,
    }

    with patch("app.api.v1.dashboard.get_revenue_summary", new_callable=AsyncMock, return_value=revenue_data):
        result = await get_dashboard_summary(scope=scope, property_id="prop-001")

    assert result.property_id == "prop-001"
    assert result.currency == "EUR"
    assert result.reservations_count == 7
    assert isinstance(result.total_revenue, Decimal)


# ---------------------------------------------------------------------------
# 401 — tenant_id not resolved → require_tenant_scope raises before endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_require_tenant_scope_401_when_tenant_id_missing():
    """
    A user with no tenant_id (failed tenant resolution) must be rejected before
    any property or revenue lookup is attempted.
    """
    from fastapi import HTTPException
    from app.core.tenant_scope import require_tenant_scope

    user = AuthenticatedUser(
        id="user-1", email="broken@example.com", permissions=[],
        cities=[], is_admin=False, tenant_id=None,
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_tenant_scope(user=user)

    assert exc_info.value.status_code == 401
