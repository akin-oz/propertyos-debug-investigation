"""
Integration test for PostgreSQL Row Level Security.

B-08  With RLS enabled + a non-superuser app role:
      a session scoped to tenant-a must see zero rows that belong to tenant-b
      in the reservations and properties tables.

Prerequisites
─────────────
Requires docker-compose PostgreSQL with schema.sql, 001_rls_policies.sql,
and seed.sql loaded.

The tests create a `app_user` role on first run (idempotent).  The role has
no SUPERUSER / BYPASSRLS so PostgreSQL RLS applies.

Why this matters
────────────────
The backend currently connects as the postgres superuser, which bypasses RLS
unconditionally.  These tests confirm the *policy logic* is correct so that
switching DATABASE_URL to app_user (the B-08 fix) will enforce isolation.
"""

import asyncio
import pytest
import pytest_asyncio
import asyncpg

from tests.integration.conftest import ASYNCPG_URL, _postgres_reachable

_APP_ROLE     = "app_user"
_APP_PASSWORD = "app_test_password_not_for_prod"
_APP_URL = ASYNCPG_URL.replace(
    "postgresql://postgres:postgres@",
    f"postgresql://{_APP_ROLE}:{_APP_PASSWORD}@",
)


# ---------------------------------------------------------------------------
# One-time setup: create the restricted app role
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def ensure_app_role():
    """Create app_user role once per module (idempotent)."""
    if not _postgres_reachable():
        pytest.skip("PostgreSQL unreachable")

    async def _setup():
        conn = await asyncpg.connect(ASYNCPG_URL)
        try:
            await conn.execute(f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_roles WHERE rolname = '{_APP_ROLE}'
                    ) THEN
                        CREATE ROLE {_APP_ROLE}
                            WITH LOGIN PASSWORD '{_APP_PASSWORD}'
                            NOSUPERUSER NOCREATEDB NOCREATEROLE
                            NOINHERIT NOREPLICATION;
                    END IF;
                END
                $$;
            """)
            await conn.execute(f"GRANT CONNECT ON DATABASE propertyflow TO {_APP_ROLE}")
            await conn.execute(f"GRANT USAGE ON SCHEMA public TO {_APP_ROLE}")
            await conn.execute(
                f"GRANT SELECT ON tenants, properties, reservations TO {_APP_ROLE}"
            )
        finally:
            await conn.close()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_setup())
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Helper: app_user connection within a tenant-scoped transaction
#
# SET LOCAL only works inside a transaction, so we use BEGIN / SET LOCAL /
# ... queries ... / ROLLBACK.  This is also the correct production pattern:
# the middleware should set the tenant on each request transaction.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def tenant_a_conn():
    conn = await asyncpg.connect(_APP_URL)
    await conn.execute("BEGIN")
    await conn.execute("SET LOCAL app.current_tenant_id = 'tenant-a'")
    try:
        yield conn
    finally:
        try:
            await conn.execute("ROLLBACK")
        except Exception:
            pass
        await conn.close()


@pytest_asyncio.fixture
async def tenant_b_conn():
    conn = await asyncpg.connect(_APP_URL)
    await conn.execute("BEGIN")
    await conn.execute("SET LOCAL app.current_tenant_id = 'tenant-b'")
    try:
        yield conn
    finally:
        try:
            await conn.execute("ROLLBACK")
        except Exception:
            pass
        await conn.close()


# ---------------------------------------------------------------------------
# B-08 — RLS isolates tenant rows at the DB layer
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_b08_rls_tenant_a_sees_no_tenant_b_reservations(tenant_a_conn):
    """
    tenant-a session must not see any of tenant-b's reservation rows.
    The RLS policy USING clause: tenant_id = current_setting('app.current_tenant_id', true)
    """
    rows = await tenant_a_conn.fetch(
        "SELECT id FROM reservations WHERE tenant_id = 'tenant-b'"
    )
    assert len(rows) == 0, (
        f"RLS failure (B-08): tenant-a session can read {len(rows)} tenant-b rows. "
        "The tenant_isolation policy on reservations is not being enforced."
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_b08_rls_tenant_b_sees_no_tenant_a_reservations(tenant_b_conn):
    """Mirror: tenant-b session must not see any of tenant-a's rows."""
    rows = await tenant_b_conn.fetch(
        "SELECT id FROM reservations WHERE tenant_id = 'tenant-a'"
    )
    assert len(rows) == 0, (
        f"RLS failure: tenant-b session reads {len(rows)} tenant-a rows."
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_b08_rls_tenant_a_sees_own_reservations(tenant_a_conn):
    """
    Positive control: RLS must filter, not block everything.
    A tenant-a session must be able to read its own reservations.
    """
    rows = await tenant_a_conn.fetch(
        "SELECT id FROM reservations WHERE tenant_id = 'tenant-a'"
    )
    assert len(rows) > 0, (
        "RLS over-blocked tenant-a: no rows visible even for their own tenant_id. "
        "Check USING clause: tenant_id = current_setting('app.current_tenant_id', true). "
        "SET LOCAL must be inside a BEGIN/COMMIT block for the GUC to take effect."
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_b08_rls_unfiltered_select_returns_only_own_rows(tenant_a_conn, tenant_b_conn):
    """
    SELECT * FROM reservations (no WHERE) must act as if filtered by tenant.
    RLS is an implicit filter — the clause should be applied unconditionally.
    """
    rows_a = await tenant_a_conn.fetch("SELECT DISTINCT tenant_id FROM reservations")
    rows_b = await tenant_b_conn.fetch("SELECT DISTINCT tenant_id FROM reservations")

    tenant_ids_a = {r["tenant_id"] for r in rows_a}
    tenant_ids_b = {r["tenant_id"] for r in rows_b}

    assert tenant_ids_a <= {"tenant-a"}, (
        f"RLS must restrict tenant-a to only its rows; found: {tenant_ids_a}"
    )
    assert tenant_ids_b <= {"tenant-b"}, (
        f"RLS must restrict tenant-b to only its rows; found: {tenant_ids_b}"
    )
    assert len(rows_a) > 0, "tenant-a must see its own reservations (positive control)"
    assert len(rows_b) > 0, "tenant-b must see its own reservations (positive control)"
    assert tenant_ids_a.isdisjoint(tenant_ids_b), (
        "tenant-a and tenant-b must see completely disjoint row sets"
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_b08_rls_properties_table_enforced(tenant_a_conn, tenant_b_conn):
    """
    The properties table also carries tenant_isolation RLS.
    tenant-a must not see prop-004/prop-005 (tenant-b), and vice versa.
    """
    # tenant-a cannot see tenant-b's properties
    rows_a = await tenant_a_conn.fetch(
        "SELECT id FROM properties WHERE id IN ('prop-004', 'prop-005')"
    )
    assert len(rows_a) == 0, (
        f"RLS on properties not enforced: tenant-a sees {len(rows_a)} tenant-b properties."
    )

    # tenant-b cannot see tenant-a's properties
    rows_b = await tenant_b_conn.fetch(
        "SELECT id FROM properties WHERE id IN ('prop-002', 'prop-003')"
    )
    assert len(rows_b) == 0, (
        f"RLS on properties not enforced: tenant-b sees {len(rows_b)} tenant-a properties."
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_b08_superuser_bypasses_rls_documents_current_risk():
    """
    Documents the current (unfixed) risk: the postgres superuser bypasses
    RLS and reads rows from every tenant.

    This test PASSES today (because the bug exists) and should be INVERTED
    once B-08 is fixed by changing DATABASE_URL to use app_user.
    """
    conn = await asyncpg.connect(ASYNCPG_URL)   # postgres superuser
    try:
        all_tenants = await conn.fetch(
            "SELECT DISTINCT tenant_id FROM reservations ORDER BY tenant_id"
        )
        tenant_set = {r["tenant_id"] for r in all_tenants}
        # Superuser sees both — this is the ongoing risk
        assert "tenant-a" in tenant_set and "tenant-b" in tenant_set, (
            "Superuser bypass confirmed: both tenants visible. "
            "B-08 fix = switch DATABASE_URL to app_user (NOSUPERUSER NOINHERIT)."
        )
    finally:
        await conn.close()
