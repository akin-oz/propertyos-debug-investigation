"""
Canonical cache-key builders for every Redis key used in this application.

Rules (enforced by tests/test_conventions.py):
  - ALL cache keys must be constructed here — nowhere else.
  - Functions accept typed NewType arguments so mypy catches argument swaps.
  - No caller may write f"revenue:..." (or any other key prefix) inline.

Adding a new cached resource:  add a function here, add a pattern to the
test, done.  Renaming a key: change it here; the compiler finds every caller.
"""

from ..models.identifiers import TenantId, PropertyId

# ── Key constants (prefixes only — never use these directly outside helpers) ──

_REVENUE_PREFIX = "revenue"
_AUTH_PREFIX = "auth"


# ── Public key builders ───────────────────────────────────────────────────────


def revenue_cache_key(tenant_id: TenantId, property_id: PropertyId) -> str:
    """
    Revenue summary cache key.

    Format: revenue:{tenant_id}:{property_id}
    TTL owner: services/cache.py (300 s)
    """
    if not tenant_id:
        raise ValueError("tenant_id must not be empty — cache key would be invalid")
    return f"{_REVENUE_PREFIX}:{tenant_id}:{property_id}"


def auth_cache_key(token_hash: str) -> str:
    """
    Auth result cache key (in-process dict, not Redis).

    Format: auth:{token_hash}
    This function exists so the pattern is grep-able; the hash is already
    computed in core/auth.py before the key is written.
    """
    return f"{_AUTH_PREFIX}:{token_hash}"
