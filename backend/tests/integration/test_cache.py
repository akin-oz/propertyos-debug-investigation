"""
Integration tests for cache isolation and invalidation.

B-01  tenant-a caches prop-001 revenue → tenant-b queries same ID → sees a different number
B-27  tenant-a inserts a reservation   → summary returns stale cache → bypass reveals new total
"""

import json
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch


# ---------------------------------------------------------------------------
# B-01 — Cross-tenant cache isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_b01_tenant_b_does_not_read_tenant_a_cache(fake_redis):
    """
    Scenario: tenant-a calls get_revenue_summary first (populates cache).
    tenant-b calls next for the same property_id.

    With the old bug (key = revenue:{property_id}), tenant-b would hit
    tenant-a's slot and return tenant-a's revenue figures.
    With the fix  (key = revenue:{tenant_id}:{property_id}), tenant-b gets
    a cache miss and receives its own (different) revenue.
    """
    redis, store = fake_redis

    tenant_a_data = {
        "property_id": "prop-001", "tenant_id": "tenant-a",
        "total": "2250.00", "currency": "USD", "count": 4,
    }
    tenant_b_data = {
        "property_id": "prop-001", "tenant_id": "tenant-b",
        "total": "0.00",    "currency": "USD", "count": 0,
    }

    # calc mock returns different values depending on which tenant_id is passed
    async def fake_calc(property_id, tenant_id):
        return tenant_a_data if tenant_id == "tenant-a" else tenant_b_data

    with patch("app.services.cache.redis_client", redis):
        with patch("app.services.reservations.calculate_total_revenue", side_effect=fake_calc):
            from app.services.cache import get_revenue_summary

            result_a = await get_revenue_summary("prop-001", "tenant-a")
            result_b = await get_revenue_summary("prop-001", "tenant-b")

    # Both must have been stored under distinct keys
    assert "revenue:tenant-a:prop-001" in store, "tenant-a slot missing from cache"
    assert "revenue:tenant-b:prop-001" in store, "tenant-b slot missing from cache"

    # Values must be different — tenant-b must NOT see tenant-a's 2250.00
    assert result_a["total"] == "2250.00"
    assert result_b["total"] == "0.00", (
        f"tenant-b read tenant-a's cached value (B-01): got {result_b['total']!r}"
    )
    assert result_a["tenant_id"] != result_b["tenant_id"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_b01_cached_slot_is_only_read_by_owning_tenant(fake_redis):
    """
    Pre-seed the cache as if tenant-a already called the endpoint.
    tenant-b's call must skip the tenant-a slot (cache miss) and compute fresh.
    """
    redis, store = fake_redis

    # Pre-seed tenant-a's slot
    tenant_a_data = {
        "property_id": "prop-001", "tenant_id": "tenant-a",
        "total": "9999.00", "currency": "USD", "count": 99,
    }
    store["revenue:tenant-a:prop-001"] = json.dumps(tenant_a_data)

    tenant_b_data = {
        "property_id": "prop-001", "tenant_id": "tenant-b",
        "total": "100.00", "currency": "USD", "count": 1,
    }

    calc_called_with = []

    async def fake_calc(property_id, tenant_id):
        calc_called_with.append(tenant_id)
        return tenant_b_data

    with patch("app.services.cache.redis_client", redis):
        with patch("app.services.reservations.calculate_total_revenue", side_effect=fake_calc):
            from app.services.cache import get_revenue_summary

            result_b = await get_revenue_summary("prop-001", "tenant-b")

    # calculate_total_revenue must have been invoked (cache miss for tenant-b)
    assert calc_called_with == ["tenant-b"], (
        "tenant-b must trigger a fresh DB call, not read tenant-a's cache slot"
    )
    assert result_b["total"] == "100.00"
    assert result_b["total"] != "9999.00", (
        "tenant-b must not receive tenant-a's pre-seeded revenue figure"
    )


# ---------------------------------------------------------------------------
# B-27 — Cache staleness after reservation insert
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_b27_stale_cache_hides_new_reservation(fake_redis):
    """
    Documents the current (unfixed) B-27 behaviour: there is no cache
    invalidation on reservation insert, so the 5-minute TTL makes the summary
    stale after a new booking is added.

    Step 1 — summary is cached with old total.
    Step 2 — a new reservation is "inserted" (calc mock returns higher total).
    Step 3 — summary call STILL returns old cached value (demonstrates the gap).
    Step 4 — bypassing the cache (delete key) reveals the correct new total.

    When B-27 is fixed, Step 3 should also return the updated total, making
    the explicit delete in Step 4 unnecessary.
    """
    redis, store = fake_redis

    old_total = {"property_id": "prop-001", "tenant_id": "tenant-a",
                 "total": "2250.00", "currency": "USD", "count": 4}
    new_total = {"property_id": "prop-001", "tenant_id": "tenant-a",
                 "total": "3500.00", "currency": "USD", "count": 5}  # +1 reservation

    call_count = [0]

    async def fake_calc(property_id, tenant_id):
        # Simulates the DB returning the updated total after insert
        call_count[0] += 1
        return new_total if call_count[0] > 1 else old_total

    with patch("app.services.cache.redis_client", redis):
        with patch("app.services.reservations.calculate_total_revenue", side_effect=fake_calc):
            from app.services.cache import get_revenue_summary

            # Step 1: first call populates cache with old total
            result_before = await get_revenue_summary("prop-001", "tenant-a")
            assert result_before["total"] == "2250.00"

            # Step 2: "reservation inserted" — next DB call would return 3500.00
            # Step 3: cache hit returns stale old total (the bug)
            result_stale = await get_revenue_summary("prop-001", "tenant-a")
            assert result_stale["total"] == "2250.00", (
                "B-27: without cache invalidation, the summary remains stale "
                "after a new reservation is inserted"
            )

    # Step 4: explicitly delete the cache key (simulates what B-27 fix should do
    # automatically) and verify the correct new total is returned
    await redis.delete("revenue:tenant-a:prop-001")

    with patch("app.services.cache.redis_client", redis):
        with patch("app.services.reservations.calculate_total_revenue", side_effect=fake_calc):
            result_fresh = await get_revenue_summary("prop-001", "tenant-a")

    assert result_fresh["total"] == "3500.00", (
        "After cache invalidation, the summary must reflect the newly inserted reservation"
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_b27_cache_invalidation_function_removes_correct_key(fake_redis):
    """
    Verifies the contract a B-27 fix must satisfy: deleting
    revenue:{tenant_id}:{property_id} from Redis must cause the next
    get_revenue_summary call to compute a fresh total from the DB.
    """
    redis, store = fake_redis

    # Seed the cache
    cached = {"property_id": "prop-001", "tenant_id": "tenant-a",
              "total": "1000.00", "currency": "USD", "count": 2}
    store["revenue:tenant-a:prop-001"] = json.dumps(cached)

    after_insert = {"property_id": "prop-001", "tenant_id": "tenant-a",
                    "total": "1500.00", "currency": "USD", "count": 3}

    # Simulate what a cache-invalidation call should do
    await redis.delete("revenue:tenant-a:prop-001")
    assert "revenue:tenant-a:prop-001" not in store, "Delete must clear the tenant-scoped key"

    with patch("app.services.cache.redis_client", redis):
        with patch("app.services.reservations.calculate_total_revenue",
                   new_callable=AsyncMock, return_value=after_insert):
            from app.services.cache import get_revenue_summary

            result = await get_revenue_summary("prop-001", "tenant-a")

    assert result["total"] == "1500.00", (
        "After cache invalidation, get_revenue_summary must return the fresh DB total"
    )
