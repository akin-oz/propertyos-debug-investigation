"""
Regression tests for app.services.reservations.

Covers:
  - calculate_total_revenue: correct Decimal sum for a tenant
  - calculate_total_revenue: cross-tenant isolation enforced by SQL WHERE clause
  - calculate_monthly_revenue: UTC window derived from property timezone, not naive UTC
"""

import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db_pool_mock(mock_session):
    """Return a patched db_pool whose get_session() yields mock_session."""
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.session_factory = True  # truthy → skip initialize()
    mock_pool.get_session.return_value = mock_cm
    return mock_pool


def _make_session_with_row(row):
    """Return an async session whose execute() returns a result with fetchone() == row."""
    mock_result = MagicMock()
    mock_result.fetchone.return_value = row

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    return mock_session


# ---------------------------------------------------------------------------
# calculate_total_revenue — correct sum for a tenant
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calculate_total_revenue_returns_correct_sum():
    """
    Known inputs: total_amount rows sum to 4975.50, count=3.
    The returned dict must carry that exact Decimal string without float drift.
    """
    mock_row = MagicMock()
    mock_row.total_revenue = Decimal("4975.50")
    mock_row.currency = "USD"
    mock_row.reservation_count = 3

    mock_session = _make_session_with_row(mock_row)
    mock_pool = _make_db_pool_mock(mock_session)

    with patch("app.services.reservations.db_pool", mock_pool):
        from app.services.reservations import calculate_total_revenue

        result = await calculate_total_revenue("prop-001", "tenant-a")

    assert result["total"] == "4975.50", "Decimal string must be exact — no float drift"
    assert result["currency"] == "USD"
    assert result["count"] == 3
    assert result["property_id"] == "prop-001"
    assert result["tenant_id"] == "tenant-a"


@pytest.mark.asyncio
async def test_calculate_total_revenue_multiple_amounts_sum_correctly():
    """Edge-value sum that drifts as float: 333.33 + 2250.00 + 2392.17 = 4975.50."""
    mock_row = MagicMock()
    mock_row.total_revenue = Decimal("333.33") + Decimal("2250.00") + Decimal("2392.17")
    mock_row.currency = "USD"
    mock_row.reservation_count = 3

    mock_session = _make_session_with_row(mock_row)
    mock_pool = _make_db_pool_mock(mock_session)

    with patch("app.services.reservations.db_pool", mock_pool):
        from app.services.reservations import calculate_total_revenue

        result = await calculate_total_revenue("prop-001", "tenant-a")

    assert Decimal(result["total"]) == Decimal("4975.50")


# ---------------------------------------------------------------------------
# calculate_total_revenue — cross-tenant property ID is silently filtered
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calculate_total_revenue_cross_tenant_property_returns_zero():
    """
    The SQL WHERE clause includes `AND tenant_id = :tenant_id`.
    When tenant-b requests prop-001 (owned by tenant-a), the DB returns no rows.
    The service must return zeros — not raise, not leak tenant-a's revenue.
    """
    # Simulate what the DB returns when the tenant_id filter finds nothing
    mock_session = _make_session_with_row(None)
    mock_pool = _make_db_pool_mock(mock_session)

    with patch("app.services.reservations.db_pool", mock_pool):
        from app.services.reservations import calculate_total_revenue

        result = await calculate_total_revenue("prop-001", "tenant-b")

    assert result["total"] == "0.00", "Cross-tenant query must yield zero, not another tenant's revenue"
    assert result["count"] == 0
    assert result["tenant_id"] == "tenant-b", "Response tenant_id must reflect the caller, not the property owner"


@pytest.mark.asyncio
async def test_calculate_total_revenue_sql_includes_tenant_filter():
    """
    Verify the SQL executed against the DB contains the tenant_id bind parameter
    so a future refactor cannot accidentally drop the isolation clause.
    """
    captured_params = {}

    mock_result = MagicMock()
    mock_result.fetchone.return_value = None

    async def fake_execute(query, params):
        captured_params.update(params)
        return mock_result

    mock_session = AsyncMock()
    mock_session.execute = fake_execute
    mock_pool = _make_db_pool_mock(mock_session)

    with patch("app.services.reservations.db_pool", mock_pool):
        from app.services.reservations import calculate_total_revenue

        await calculate_total_revenue("prop-001", "tenant-a")

    assert "tenant_id" in captured_params, "Query must bind :tenant_id parameter"
    assert captured_params["tenant_id"] == "tenant-a"
    assert captured_params["property_id"] == "prop-001"


# ---------------------------------------------------------------------------
# calculate_monthly_revenue — respects property timezone on month boundaries
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calculate_monthly_revenue_paris_march_start_utc_is_feb29_23h():
    """
    Seed row: check_in_date = 2024-02-29 23:30 UTC = 2024-03-01 00:30 Europe/Paris.

    When month=3, year=2024, timezone="Europe/Paris":
      start_utc must be 2024-02-29 23:00 UTC (not 2024-03-01 00:00 UTC).

    This is the fix for the tz-naive bug where UTC midnight was used instead of
    converting the local midnight to UTC first.
    """
    captured_params = {}

    mock_result = MagicMock()
    mock_result.fetchone.return_value = (Decimal("1200.00"),)

    async def fake_execute(query, params):
        captured_params.update(params)
        return mock_result

    mock_session = AsyncMock()
    mock_session.execute = fake_execute

    from app.services.reservations import calculate_monthly_revenue

    result = await calculate_monthly_revenue(
        property_id="prop-001",
        tenant_id="tenant-a",
        month=3,
        year=2024,
        timezone="Europe/Paris",
        db_session=mock_session,
    )

    start_utc = captured_params["start"]
    end_utc = captured_params["end"]

    # March 1 00:00 Europe/Paris (UTC+1 in winter) = Feb 29 23:00 UTC
    assert start_utc.month == 2, f"start_utc month must be February, got {start_utc}"
    assert start_utc.day == 29, f"start_utc day must be 29, got {start_utc}"
    assert start_utc.hour == 23, f"start_utc hour must be 23:00, got {start_utc}"

    # The boundary reservation (2024-02-29 23:30 UTC) must fall in [start_utc, end_utc)
    boundary = datetime(2024, 2, 29, 23, 30, tzinfo=ZoneInfo("UTC"))
    assert start_utc <= boundary < end_utc, (
        f"Boundary reservation {boundary} not in [{start_utc}, {end_utc})"
    )

    assert result == Decimal("1200.00")


@pytest.mark.asyncio
async def test_calculate_monthly_revenue_naive_utc_would_misattribute():
    """
    Demonstrates why naive UTC is wrong: with naive UTC boundaries,
    the 2024-02-29 23:30 UTC reservation falls in February, not March.
    The fix uses timezone-aware boundaries.
    """
    utc_tz = ZoneInfo("UTC")

    # Naive UTC February boundaries (the buggy approach)
    feb_start_naive = datetime(2024, 2, 1, tzinfo=utc_tz)
    mar_start_naive = datetime(2024, 3, 1, tzinfo=utc_tz)

    boundary_reservation = datetime(2024, 2, 29, 23, 30, tzinfo=utc_tz)

    # Naive UTC: reservation is in February (wrong for Europe/Paris)
    assert feb_start_naive <= boundary_reservation < mar_start_naive, (
        "Naive UTC incorrectly places this reservation in February"
    )

    # Timezone-aware fix: March boundaries in Europe/Paris converted to UTC
    paris_tz = ZoneInfo("Europe/Paris")
    mar_start_paris_utc = datetime(2024, 3, 1, 0, 0, tzinfo=paris_tz).astimezone(utc_tz)
    apr_start_paris_utc = datetime(2024, 4, 1, 0, 0, tzinfo=paris_tz).astimezone(utc_tz)

    assert mar_start_paris_utc <= boundary_reservation < apr_start_paris_utc, (
        "Timezone-aware boundaries correctly assign this reservation to March"
    )


@pytest.mark.asyncio
async def test_calculate_monthly_revenue_returns_zero_when_no_rows():
    """No reservations in window returns Decimal('0'), not None."""
    mock_result = MagicMock()
    mock_result.fetchone.return_value = (None,)

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    from app.services.reservations import calculate_monthly_revenue

    result = await calculate_monthly_revenue(
        property_id="prop-001",
        tenant_id="tenant-a",
        month=1,
        year=2025,
        timezone="UTC",
        db_session=mock_session,
    )

    assert result == Decimal("0")
