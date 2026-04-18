"""
Regression tests for app.services.cache.

Covers:
  - B-01: get_revenue_summary cache key must include tenant_id
  - Integration: two tenants sharing a property_id receive independent cached values
"""

import json
import pytest
from unittest.mock import AsyncMock, patch


# ---------------------------------------------------------------------------
# B-01 — cache key must be scoped to tenant_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_revenue_summary_cache_key_includes_tenant_id():
    """
    Before the fix, the cache key was `revenue:{property_id}`, omitting tenant_id.
    tenant-a and tenant-b both own prop-001, so they shared a cache slot and
    could read each other's revenue figures.

    The key must be `revenue:{tenant_id}:{property_id}`.
    """
    captured_keys: list[tuple[str, str]] = []

    async def fake_get(key: str):
        captured_keys.append(("get", key))
        return None  # always a cache miss so setex is reached

    async def fake_setex(key: str, ttl: int, value: str):
        captured_keys.append(("setex", key))

    mock_revenue = {
        "property_id": "prop-001",
        "tenant_id": "tenant-a",
        "total": "1000.00",
        "currency": "USD",
        "count": 2,
    }

    with patch("app.services.cache.redis_client") as mock_redis:
        mock_redis.get = fake_get
        mock_redis.setex = fake_setex

        # calculate_total_revenue is imported lazily inside the function, so patch
        # it at its source module, not at app.services.cache.
        with patch("app.services.reservations.calculate_total_revenue", new_callable=AsyncMock, return_value=mock_revenue):
            from app.services.cache import get_revenue_summary

            await get_revenue_summary("prop-001", "tenant-a")

    for op, key in captured_keys:
        assert "tenant-a" in key, f"redis {op} used key without tenant_id: '{key}'"
        assert "prop-001" in key, f"redis {op} used key without property_id: '{key}'"
        assert key.startswith("revenue:tenant-a:"), (
            f"key format must be revenue:{{tenant_id}}:{{property_id}}, got '{key}'"
        )


@pytest.mark.asyncio
async def test_get_revenue_summary_raises_when_tenant_id_missing():
    """Missing tenant_id must raise ValueError, not silently build a bad key."""
    from app.services.cache import get_revenue_summary

    with pytest.raises(ValueError, match="tenant_id"):
        await get_revenue_summary("prop-001", "")


# ---------------------------------------------------------------------------
# Integration — two tenants sharing a property_id get independent cache slots
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_revenue_summary_different_tenants_get_different_values():
    """
    tenant-a and tenant-b both have prop-001 in the seed data.
    After tenant-a populates its slot, a request for tenant-b must get a cache
    miss and calculate fresh revenue — not read tenant-a's cached value.
    """
    store: dict[str, str] = {}

    async def fake_get(key: str):
        return store.get(key)

    async def fake_setex(key: str, ttl: int, value: str):
        store[key] = value

    tenant_a_revenue = {
        "property_id": "prop-001", "tenant_id": "tenant-a",
        "total": "1000.00", "currency": "USD", "count": 2,
    }
    tenant_b_revenue = {
        "property_id": "prop-001", "tenant_id": "tenant-b",
        "total": "2500.00", "currency": "USD", "count": 5,
    }

    with patch("app.services.cache.redis_client") as mock_redis:
        mock_redis.get = fake_get
        mock_redis.setex = fake_setex

        with patch("app.services.reservations.calculate_total_revenue", new_callable=AsyncMock) as mock_calc:
            mock_calc.side_effect = [tenant_a_revenue, tenant_b_revenue]

            from app.services.cache import get_revenue_summary

            result_a = await get_revenue_summary("prop-001", "tenant-a")
            result_b = await get_revenue_summary("prop-001", "tenant-b")

    assert result_a["total"] == "1000.00", "tenant-a must see its own revenue"
    assert result_b["total"] == "2500.00", "tenant-b must see its own revenue"
    assert result_a["tenant_id"] != result_b["tenant_id"]

    # Two distinct cache entries must exist — one per tenant
    assert "revenue:tenant-a:prop-001" in store
    assert "revenue:tenant-b:prop-001" in store
    assert store["revenue:tenant-a:prop-001"] != store["revenue:tenant-b:prop-001"]


@pytest.mark.asyncio
async def test_get_revenue_summary_cache_hit_returns_stored_value():
    """On a cache hit, calculate_total_revenue must NOT be called."""
    cached_value = {
        "property_id": "prop-001", "tenant_id": "tenant-a",
        "total": "1234.56", "currency": "EUR", "count": 1,
    }

    async def fake_get(key: str):
        if key == "revenue:tenant-a:prop-001":
            return json.dumps(cached_value)
        return None

    with patch("app.services.cache.redis_client") as mock_redis:
        mock_redis.get = fake_get

        with patch("app.services.reservations.calculate_total_revenue", new_callable=AsyncMock) as mock_calc:
            from app.services.cache import get_revenue_summary

            result = await get_revenue_summary("prop-001", "tenant-a")

    mock_calc.assert_not_called()
    assert result["total"] == "1234.56"
    assert result["currency"] == "EUR"
