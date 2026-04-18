"""
Unit tests for TenantResolver.resolve_tenant_from_token.

The function reads tenant_id from three possible JWT payload locations:
  1. token_payload['user_metadata']['tenant_id']   (highest priority)
  2. token_payload['app_metadata']['tenant_id']
  3. token_payload['tenant_id']                    (root level)

Nothing calls resolve_tenant_from_token in the current auth flow — this
regression suite pins the extraction logic so that wiring it in is safe.
"""

import pytest
from app.core.tenant_resolver import TenantResolver


# ---------------------------------------------------------------------------
# All three claim locations
# ---------------------------------------------------------------------------

def test_resolve_from_user_metadata():
    payload = {"user_metadata": {"tenant_id": "tenant-from-user-meta"}}
    assert TenantResolver.resolve_tenant_from_token(payload) == "tenant-from-user-meta"


def test_resolve_from_app_metadata():
    payload = {"app_metadata": {"tenant_id": "tenant-from-app-meta"}}
    assert TenantResolver.resolve_tenant_from_token(payload) == "tenant-from-app-meta"


def test_resolve_from_root_level():
    payload = {"tenant_id": "tenant-from-root"}
    assert TenantResolver.resolve_tenant_from_token(payload) == "tenant-from-root"


# ---------------------------------------------------------------------------
# Priority: user_metadata wins over app_metadata and root
# ---------------------------------------------------------------------------

def test_user_metadata_takes_priority_over_app_metadata():
    payload = {
        "user_metadata": {"tenant_id": "from-user-meta"},
        "app_metadata": {"tenant_id": "from-app-meta"},
    }
    assert TenantResolver.resolve_tenant_from_token(payload) == "from-user-meta"


def test_user_metadata_takes_priority_over_root():
    payload = {
        "user_metadata": {"tenant_id": "from-user-meta"},
        "tenant_id": "from-root",
    }
    assert TenantResolver.resolve_tenant_from_token(payload) == "from-user-meta"


def test_app_metadata_takes_priority_over_root():
    payload = {
        "app_metadata": {"tenant_id": "from-app-meta"},
        "tenant_id": "from-root",
    }
    assert TenantResolver.resolve_tenant_from_token(payload) == "from-app-meta"


def test_all_three_locations_user_metadata_wins():
    payload = {
        "user_metadata": {"tenant_id": "from-user-meta"},
        "app_metadata": {"tenant_id": "from-app-meta"},
        "tenant_id": "from-root",
    }
    assert TenantResolver.resolve_tenant_from_token(payload) == "from-user-meta"


# ---------------------------------------------------------------------------
# Returns None when no tenant_id is present
# ---------------------------------------------------------------------------

def test_returns_none_when_no_tenant_id():
    payload = {"sub": "user-1", "email": "x@example.com", "aud": "authenticated"}
    assert TenantResolver.resolve_tenant_from_token(payload) is None


def test_returns_none_for_empty_payload():
    assert TenantResolver.resolve_tenant_from_token({}) is None


def test_returns_none_when_metadata_present_but_no_tenant_id():
    payload = {
        "user_metadata": {"name": "Alice"},
        "app_metadata": {"role": "user"},
    }
    assert TenantResolver.resolve_tenant_from_token(payload) is None


def test_ignores_empty_string_tenant_id_in_user_metadata():
    """Empty string is falsy — should fall through to the next location."""
    payload = {
        "user_metadata": {"tenant_id": ""},
        "app_metadata": {"tenant_id": "from-app-meta"},
    }
    # "" is falsy so resolve_tenant_from_token should skip it and check app_metadata
    result = TenantResolver.resolve_tenant_from_token(payload)
    assert result == "from-app-meta"
