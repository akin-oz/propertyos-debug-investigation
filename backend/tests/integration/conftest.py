"""
Shared fixtures for integration tests.

Integration tests require a live PostgreSQL (exposed by docker-compose on
host port 5433) and optionally a live Redis (port 6380).

Override the URL via:
  TEST_DATABASE_URL   e.g. postgresql://postgres:postgres@localhost:5433/propertyflow
"""

import asyncio
import os
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# ---------------------------------------------------------------------------
# Connection URLs
# ---------------------------------------------------------------------------

ASYNCPG_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5433/propertyflow",
)
SQLALCHEMY_URL = ASYNCPG_URL.replace("postgresql://", "postgresql+asyncpg://")


# ---------------------------------------------------------------------------
# pytest marker registration
# ---------------------------------------------------------------------------


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: marks tests that require a running PostgreSQL / Redis instance",
    )


# ---------------------------------------------------------------------------
# DB availability probe (runs synchronously so it can gate fixture setup)
# ---------------------------------------------------------------------------


def _postgres_reachable() -> bool:
    """
    Synchronous probe using psycopg2 (no event loop required).
    Safe to call from async fixtures and sync session-scoped fixtures alike.
    """
    try:
        import psycopg2
        conn = psycopg2.connect(ASYNCPG_URL, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Function-scoped SQLAlchemy session (async, self-contained engine)
#
# Each test gets a fresh engine + connection in a rolled-back transaction.
# This avoids all session-scope / event-loop lifetime issues.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sa_session():
    """
    Async SQLAlchemy session within a rolled-back connection-level transaction.
    Creates its own engine per-test — slightly slower but never suffers from
    event-loop lifetime conflicts between session-scoped and function-scoped fixtures.
    """
    if not _postgres_reachable():
        pytest.skip("PostgreSQL unreachable — run `docker-compose up db` or set TEST_DATABASE_URL")

    engine = create_async_engine(SQLALCHEMY_URL, echo=False)
    conn = await engine.connect()
    await conn.begin()
    session = AsyncSession(bind=conn, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        await conn.rollback()
        await conn.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# Function-scoped: raw asyncpg connection with auto-rollback
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def pg_conn():
    """
    Direct asyncpg connection within a rolled-back transaction.
    Use for tests that need raw SQL, SET LOCAL, or RLS gymnastics.
    """
    if not _postgres_reachable():
        pytest.skip("PostgreSQL unreachable")
    conn = await asyncpg.connect(ASYNCPG_URL)
    await conn.execute("BEGIN")
    try:
        yield conn
    finally:
        # ROLLBACK may fail if the transaction is already aborted; ignore
        try:
            await conn.execute("ROLLBACK")
        except Exception:
            pass
        await conn.close()


# ---------------------------------------------------------------------------
# db_pool patcher — routes service calls through the test session
# ---------------------------------------------------------------------------


@pytest.fixture
def db_pool_from(sa_session):
    """
    Returns a mock db_pool whose get_session() yields the test sa_session.
    Patch into the module under test so service calls use the same
    rolled-back transaction as the test fixture.

    Usage:
        with patch("app.services.reservations.db_pool", db_pool_from):
            result = await calculate_total_revenue(...)
    """

    @asynccontextmanager
    async def _get_session(**kwargs):
        yield sa_session

    mock_pool = MagicMock()
    mock_pool.session_factory = True   # truthy → skip initialize()
    mock_pool.get_session = _get_session
    return mock_pool


# ---------------------------------------------------------------------------
# In-memory Redis substitute
# ---------------------------------------------------------------------------


class _FakeRedis:
    """dict-backed async Redis stand-in covering the subset used by cache.py."""

    def __init__(self, store: dict):
        self._store = store

    async def get(self, key: str):
        return self._store.get(key)

    async def setex(self, key: str, ttl: int, value: str):
        self._store[key] = value

    async def delete(self, key: str):
        self._store.pop(key, None)


@pytest.fixture
def fake_redis():
    """Returns (FakeRedis instance, backing dict).  Patch into app.services.cache.redis_client."""
    store: dict = {}
    return _FakeRedis(store), store
