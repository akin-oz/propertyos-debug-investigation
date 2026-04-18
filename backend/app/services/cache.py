import json
from typing import Any, Dict

import redis.asyncio as redis
import os

from ..models.identifiers import TenantId, PropertyId
from ..core.cache_keys import revenue_cache_key

_redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(_redis_url, decode_responses=True)


async def get_revenue_summary(property_id: PropertyId, tenant_id: TenantId) -> Dict[str, Any]:
    """
    Fetch revenue summary, with Redis caching.

    Cache key is built by cache_keys.revenue_cache_key — never inline.
    tenant_id is typed TenantId; mypy rejects passing a raw str here.
    """
    cache_key = revenue_cache_key(tenant_id, property_id)

    cached = await redis_client.get(cache_key)
    if cached:
        result_cached: Dict[str, Any] = json.loads(cached)
        return result_cached

    from .reservations import calculate_total_revenue

    result = await calculate_total_revenue(property_id, tenant_id)

    await redis_client.setex(cache_key, 300, json.dumps(result))

    return result
