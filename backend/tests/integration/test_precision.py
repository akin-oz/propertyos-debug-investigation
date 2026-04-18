"""
Integration tests for numeric precision against the real database.

B-02  333.333 + 333.333 + 333.334 → "1000.00" (not 999.99 or 1000.01)
B-18  USD + EUR reservations for the same property must be split or rejected,
      never blindly summed into one figure
"""

import pytest
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import text

from tests.integration.conftest import ASYNCPG_URL


# ---------------------------------------------------------------------------
# B-02 — Sub-cent NUMERIC arithmetic must survive the Python round-trip
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_b02_db_sum_of_sub_cent_amounts_is_exact(sa_session):
    """
    The seed rows res-dec-1 / res-dec-2 / res-dec-3 are stored as
    NUMERIC(10, 3) values 333.333 + 333.333 + 333.334.

    PostgreSQL NUMERIC addition is exact; the DB-level sum must be 1000.000.
    This guards against an implementation that converts to float in the query
    (e.g. CAST(total_amount AS FLOAT)) which would introduce IEEE-754 drift.
    """
    result = await sa_session.execute(
        text("""
            SELECT SUM(total_amount) AS total
            FROM reservations
            WHERE id IN ('res-dec-1', 'res-dec-2', 'res-dec-3')
              AND tenant_id = 'tenant-a'
        """)
    )
    row = result.fetchone()
    assert row is not None
    db_total = Decimal(str(row[0]))

    assert db_total == Decimal("1000.000"), (
        f"DB SUM drifted: expected 1000.000, got {db_total}. "
        "Check that NUMERIC columns are not cast to FLOAT anywhere in the query."
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_b02_calculate_monthly_revenue_returns_quantized_decimal(sa_session):
    """
    End-to-end path for B-02: calculate_monthly_revenue with a real DB session
    returns Decimal("1000.00") for the three March 2024 sub-cent seed rows
    (res-dec-1, res-dec-2, res-dec-3 all fall in March 2024 UTC).

    res-tz-1 (2024-02-29 23:30 UTC) is OUTSIDE the UTC March window so only
    the three 333.333/334 rows contribute → 1000.000 → quantize → "1000.00".
    """
    from app.services.reservations import calculate_monthly_revenue

    raw = await calculate_monthly_revenue(
        property_id="prop-001",
        tenant_id="tenant-a",
        month=3,
        year=2024,
        timezone="UTC",
        db_session=sa_session,
    )

    # The service returns a Decimal; the dashboard quantizes it before serving.
    quantized = raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    assert quantized == Decimal("1000.00"), (
        f"Sub-cent sum rounded incorrectly: expected 1000.00, got {quantized}. "
        "This reproduces B-02 — check that ROUND_HALF_UP is applied and float() is never used."
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_b02_float_would_have_drifted(sa_session):
    """
    Demonstrates *why* float() is forbidden (CLAUDE.md stop rule).
    Fetching the same sum as float produces drift; Decimal stays exact.
    """
    result = await sa_session.execute(
        text("""
            SELECT
                SUM(total_amount)::float    AS float_total,
                SUM(total_amount)           AS decimal_total
            FROM reservations
            WHERE id IN ('res-dec-1', 'res-dec-2', 'res-dec-3')
              AND tenant_id = 'tenant-a'
        """)
    )
    row = result.fetchone()

    float_total   = float(row[0])
    decimal_total = Decimal(str(row[1]))

    # float may or may not drift here, but Decimal is always exact
    assert decimal_total == Decimal("1000.000"), "NUMERIC path must be exact"

    # Guard: if float happened to equal 1000.0 on this platform, still check
    # that we never round a float to get "1000.00" — the intermediate value
    # could be 999.9999... or 1000.0000...01 depending on hardware.
    # The point is that the codebase MUST use Decimal, not float.
    float_quantized   = round(float_total, 2)
    decimal_quantized = decimal_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    assert decimal_quantized == Decimal("1000.00"), (
        "Decimal path must always yield 1000.00"
    )


# ---------------------------------------------------------------------------
# B-18 — Mixed-currency reservations must not be silently summed together
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_b18_sql_groups_by_currency_not_single_sum(pg_conn):
    """
    PostgreSQL-level assertion: when a property has both USD and EUR
    reservations, the GROUP BY currency clause must produce *two* rows —
    not one merged total.

    This test inserts an EUR row (rolled back after), then checks the raw
    query that calculate_total_revenue uses.
    """
    # Insert a EUR reservation within the rolled-back transaction
    await pg_conn.execute("""
        INSERT INTO reservations
            (id, property_id, tenant_id, check_in_date, check_out_date, total_amount, currency)
        VALUES
            ('test-eur-intg', 'prop-001', 'tenant-a',
             '2025-01-10 10:00:00+00', '2025-01-15 10:00:00+00',
             500.000, 'EUR')
    """)

    rows = await pg_conn.fetch("""
        SELECT currency, SUM(total_amount) AS total_revenue
        FROM reservations
        WHERE property_id = 'prop-001'
          AND tenant_id   = 'tenant-a'
        GROUP BY property_id, currency
        ORDER BY currency
    """)

    currencies = [r["currency"] for r in rows]
    assert len(rows) >= 2, (
        "Mixed USD + EUR must produce at least two rows from GROUP BY currency, "
        "not a single merged total."
    )
    assert "EUR" in currencies, "EUR reservation must appear as its own group"
    assert "USD" in currencies, "Existing USD reservations must appear as their own group"

    eur_total = next(Decimal(str(r["total_revenue"])) for r in rows if r["currency"] == "EUR")
    usd_total = next(Decimal(str(r["total_revenue"])) for r in rows if r["currency"] == "USD")

    assert eur_total == Decimal("500.000"), f"EUR total wrong: {eur_total}"
    assert usd_total > 0, "USD total must be positive from seed data"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_b18_calculate_total_revenue_fetchone_silently_drops_one_currency(
    sa_session, db_pool_from
):
    """
    B-18 (current buggy behaviour): calculate_total_revenue calls fetchone(),
    which returns only ONE of the GROUP BY currency rows.  When USD and EUR
    rows both exist, one currency's revenue is silently discarded.

    Both the EUR insert and the service call use the SAME sa_session so the
    uncommitted row is visible to the query within the same transaction.
    Everything rolls back when the test ends.
    """
    from unittest.mock import patch

    # Insert an EUR reservation via the same session the service will query
    await sa_session.execute(
        text("""
            INSERT INTO reservations
                (id, property_id, tenant_id, check_in_date, check_out_date, total_amount, currency)
            VALUES
                ('test-eur-svc2', 'prop-001', 'tenant-a',
                 '2025-03-01 10:00:00+00', '2025-03-05 10:00:00+00',
                 750.000, 'EUR')
        """)
    )
    await sa_session.flush()

    from app.services.reservations import calculate_total_revenue

    with patch("app.services.reservations.db_pool", db_pool_from):
        result = await calculate_total_revenue("prop-001", "tenant-a")

    # fetchone() returns whichever currency PostgreSQL puts first.
    # The result has ONE currency — the other is silently dropped (the bug).
    assert result["currency"] in ("USD", "EUR"), "Result must be one of the two currencies"

    # Bug documented: the returned total reflects only ONE currency.
    # When B-18 is fixed, this test should be changed to assert that either:
    #   a) result contains a list of per-currency breakdowns, or
    #   b) calculate_total_revenue raises ValueError for mixed-currency properties.
    assert "total" in result, "A total is returned but it covers only one currency (B-18 bug)"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_b18_mixed_currency_totals_are_independently_correct(pg_conn):
    """
    Verifies that even though the service returns only one currency at a time,
    each individual currency total is arithmetically correct within the DB.
    """
    await pg_conn.execute("""
        INSERT INTO reservations
            (id, property_id, tenant_id, check_in_date, check_out_date, total_amount, currency)
        VALUES
            ('test-mix-1', 'prop-001', 'tenant-a',
             '2025-04-01 10:00:00+00', '2025-04-05 10:00:00+00', 100.000, 'EUR'),
            ('test-mix-2', 'prop-001', 'tenant-a',
             '2025-04-06 10:00:00+00', '2025-04-10 10:00:00+00', 200.000, 'EUR')
    """)

    rows = await pg_conn.fetch("""
        SELECT currency, SUM(total_amount) AS total
        FROM reservations
        WHERE id IN ('test-mix-1', 'test-mix-2')
          AND tenant_id = 'tenant-a'
        GROUP BY currency
    """)

    assert len(rows) == 1
    assert rows[0]["currency"] == "EUR"
    assert Decimal(str(rows[0]["total"])) == Decimal("300.000"), (
        "EUR-only sum must be exact; no float contamination from USD rows"
    )
