"""
Integration tests for DB pool failure handling.

B-04 / B-05  DB pool down → response is 503, not silent mock data or an
             unhandled exception that leaks internal state.
"""

import pytest
from contextlib import asynccontextmanager
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# B-04 / B-05 — DB pool failure surfaces as 503
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_db_pool_connection_failure_returns_503():
    """
    When db_pool.get_session() raises (e.g. all connections exhausted,
    DB host unreachable, pool not initialised), calculate_total_revenue
    must catch the error and raise HTTPException(503).

    Before the fix (B-06): the function propagated the raw exception,
    leaking internal DB details and crashing the endpoint.
    """
    @asynccontextmanager
    async def failing_get_session(**kwargs):
        raise ConnectionRefusedError("DB host unreachable (simulated for B-04/B-05)")
        yield  # make it a generator

    mock_pool = MagicMock()
    mock_pool.session_factory = True
    mock_pool.get_session = failing_get_session

    with patch("app.services.reservations.db_pool", mock_pool):
        from app.services.reservations import calculate_total_revenue

        with pytest.raises(HTTPException) as exc_info:
            await calculate_total_revenue("prop-001", "tenant-a")

    assert exc_info.value.status_code == 503, (
        f"DB pool failure must surface as 503 Service Unavailable, "
        f"not {exc_info.value.status_code}. "
        "Raw DB errors must never reach the client."
    )
    assert exc_info.value.detail, "503 response must include a user-facing detail message"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_db_pool_query_error_returns_503():
    """
    Even when the connection is established, a query-time error (e.g. network
    interruption mid-query, statement timeout, role revoked) must also yield 503.
    """
    mock_session = AsyncMock()
    mock_session.execute.side_effect = OSError("Connection reset by peer")

    @asynccontextmanager
    async def session_with_query_error(**kwargs):
        yield mock_session

    mock_pool = MagicMock()
    mock_pool.session_factory = True
    mock_pool.get_session = session_with_query_error

    with patch("app.services.reservations.db_pool", mock_pool):
        from app.services.reservations import calculate_total_revenue

        with pytest.raises(HTTPException) as exc_info:
            await calculate_total_revenue("prop-001", "tenant-a")

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.integration
async def test_db_pool_not_initialised_raises_503_not_500():
    """
    Before B-04 fix: QueuePool (sync) was passed to create_async_engine,
    causing a crash at pool-init time.  That crash propagated as a 500
    (or worse, an unhandled exception with a Python traceback in the response).

    After the fix: pool failure raises a managed 503 so the client gets a
    clean error and no internal details leak.
    """
    @asynccontextmanager
    async def uninitialised_pool(**kwargs):
        raise RuntimeError("Database pool not initialised (async pool misconfigured)")
        yield

    mock_pool = MagicMock()
    mock_pool.session_factory = None  # falsy — pool not initialised
    mock_pool.initialize = AsyncMock(side_effect=RuntimeError("asyncpg pool init failed"))
    mock_pool.get_session = uninitialised_pool

    with patch("app.services.reservations.db_pool", mock_pool):
        from app.services.reservations import calculate_total_revenue

        with pytest.raises(HTTPException) as exc_info:
            await calculate_total_revenue("prop-001", "tenant-a")

    code = exc_info.value.status_code
    assert code == 503, (
        f"Pool initialisation failure must yield 503, got {code}. "
        "B-04: QueuePool → AsyncAdaptedQueuePool fix ensures the pool starts; "
        "this test guards against any future regression where pool failure leaks as 500."
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_db_failure_does_not_return_mock_data():
    """
    B-05: the DB failure path must raise an exception, never silently fall
    back to fabricated or cached mock data.

    There must be no try/except block that swallows the error and returns
    {"total": "0.00", "count": 0} without a 503.
    """
    call_count = [0]

    @asynccontextmanager
    async def failing_pool(**kwargs):
        call_count[0] += 1
        raise TimeoutError("DB connect timed out")
        yield

    mock_pool = MagicMock()
    mock_pool.session_factory = True
    mock_pool.get_session = failing_pool

    with patch("app.services.reservations.db_pool", mock_pool):
        from app.services.reservations import calculate_total_revenue

        try:
            result = await calculate_total_revenue("prop-001", "tenant-a")
            # If we reach here, the function returned silently — that is the bug
            pytest.fail(
                f"calculate_total_revenue returned {result!r} on DB failure instead of "
                "raising HTTPException(503). Mock data must never be silently served."
            )
        except HTTPException as e:
            assert e.status_code == 503
        except Exception as e:
            pytest.fail(
                f"calculate_total_revenue raised {type(e).__name__} instead of HTTPException. "
                "All DB errors must be converted to HTTPException(503)."
            )

    assert call_count[0] >= 1, "DB pool must have been attempted"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_db_error_detail_does_not_expose_internals():
    """
    The 503 detail message must be a safe user-facing string, not a raw
    Python exception message that might contain connection strings or PII.
    """
    @asynccontextmanager
    async def failing_pool(**kwargs):
        raise Exception(
            "FATAL: password authentication failed for user 'postgres' "
            "at postgresql://postgres:SECRET_PASSWORD@db:5432/propertyflow"
        )
        yield

    mock_pool = MagicMock()
    mock_pool.session_factory = True
    mock_pool.get_session = failing_pool

    with patch("app.services.reservations.db_pool", mock_pool):
        from app.services.reservations import calculate_total_revenue

        with pytest.raises(HTTPException) as exc_info:
            await calculate_total_revenue("prop-001", "tenant-a")

    detail = exc_info.value.detail
    assert "SECRET_PASSWORD" not in detail, (
        "Raw exception messages containing credentials must never appear in HTTP responses"
    )
    assert "postgresql://" not in detail, (
        "Connection strings must not be leaked in API error details"
    )
