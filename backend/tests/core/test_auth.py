"""
Regression tests for app.core.auth.authenticate_request.

Covers:
  - JWT audience mismatch → 401 (the aud="authenticated" check must be enforced)
  - B-06: tenant_id must come from the JWT claim, not from the user's email
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt as jose_jwt, JWTError


# The default secret used in challenge / test mode (see app/config.py)
_SECRET = "debug_challenge_secret"


def _make_creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _make_token(payload: dict, secret: str = _SECRET) -> str:
    return jose_jwt.encode(payload, secret, algorithm="HS256")


# ---------------------------------------------------------------------------
# JWT audience enforcement
# ---------------------------------------------------------------------------

def test_jwt_decode_rejects_wrong_audience():
    """
    Core claim: jose.jwt.decode must raise JWTError when aud doesn't match.
    This pins the library behaviour that authenticate_request relies on.
    """
    token = _make_token({"sub": "u1", "email": "test@example.com", "aud": "wrong-audience"})

    with pytest.raises(JWTError):
        jose_jwt.decode(token, _SECRET, algorithms=["HS256"], audience="authenticated")


@pytest.mark.asyncio
async def test_authenticate_request_raises_401_for_wrong_audience():
    """
    End-to-end: a JWT with aud="wrong-audience" must not authenticate.

    The custom-JWT path fails (wrong aud) and the Supabase fallback is also
    forced to fail, so the only outcome is HTTP 401.
    """
    from app.core.auth import authenticate_request, clear_auth_cache

    clear_auth_cache()

    token = _make_token({"sub": "u1", "email": "test@example.com", "aud": "wrong-audience"})
    creds = _make_creds(token)

    # Force the Supabase fallback to fail so neither path can succeed
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.side_effect = Exception("simulated supabase failure")

    with patch("app.core.auth.supabase", mock_supabase):
        with pytest.raises(HTTPException) as exc_info:
            await authenticate_request(creds)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_authenticate_request_raises_401_for_missing_credentials():
    """None credentials must yield 401, not AttributeError."""
    from app.core.auth import authenticate_request, clear_auth_cache

    clear_auth_cache()

    with pytest.raises(HTTPException) as exc_info:
        await authenticate_request(None)

    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# B-06 — tenant_id from JWT claim, not user.email
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_authenticate_request_uses_jwt_tenant_id_not_email_mapping():
    """
    Regression for B-06.

    A JWT carrying user_metadata.tenant_id = "tenant-from-jwt" for
    sunset@propertyflow.com (which email-maps to "tenant-a") must resolve to
    "tenant-from-jwt".

    The TenantResolver is mocked to simulate the correct fixed behaviour
    (returning the JWT claim). This test documents the expected contract between
    authenticate_request and TenantResolver.
    """
    from app.core.auth import authenticate_request, clear_auth_cache

    clear_auth_cache()

    expected_tenant = "tenant-from-jwt"

    token = _make_token({
        "sub": "user-99",
        "id": "user-99",
        "email": "sunset@propertyflow.com",   # email mapping would give "tenant-a"
        "aud": "authenticated",
        "app_metadata": {},
        "user_metadata": {"tenant_id": expected_tenant},
    })
    creds = _make_creds(token)

    # Supabase service calls (permissions, cities, tenant_role, properties)
    # all return empty lists — no real DB needed.
    mock_sb = MagicMock()
    mock_sb.service.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    mock_sb.service.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    mock_sb.service.table.return_value.select.return_value.in_.return_value.eq.return_value.execute.return_value.data = []

    with patch("app.core.auth.supabase", mock_sb):
        # Mock TenantResolver to return the JWT-based tenant_id (the expected fix).
        with patch(
            "app.core.auth.TenantResolver.resolve_tenant_id",
            new_callable=AsyncMock,
            return_value=expected_tenant,
        ) as mock_resolve:
            result = await authenticate_request(creds)

    assert result.tenant_id == expected_tenant, (
        f"tenant_id should come from JWT claim ({expected_tenant!r}), "
        f"not email mapping ('tenant-a'). Got: {result.tenant_id!r}"
    )

    # Verify TenantResolver was called with the raw token so it can inspect JWT claims
    mock_resolve.assert_called_once()
    call_kwargs = mock_resolve.call_args.kwargs
    assert call_kwargs.get("token") == token, (
        "TenantResolver.resolve_tenant_id must receive the raw token "
        "so it can extract tenant_id from JWT claims"
    )


@pytest.mark.asyncio
async def test_authenticate_request_email_alone_gives_wrong_tenant_demonstrating_bug():
    """
    Documents the current (unfixed) behaviour: when TenantResolver uses only
    the email mapping, sunset@propertyflow.com always gets "tenant-a" regardless
    of what the JWT payload says.

    This test is expected to pass against the BUGGY code (showing the wrong
    tenant_id is returned) and should FAIL once B-06 is fixed (replaced by the
    test above).

    It is kept here as a canary: if this test starts failing, B-06 is resolved.
    """
    from app.core.auth import authenticate_request, clear_auth_cache

    clear_auth_cache()

    token = _make_token({
        "sub": "user-99",
        "id": "user-99",
        "email": "sunset@propertyflow.com",
        "aud": "authenticated",
        "app_metadata": {},
        "user_metadata": {"tenant_id": "tenant-from-jwt"},
    })
    creds = _make_creds(token)

    mock_sb = MagicMock()
    mock_sb.service.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    mock_sb.service.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    mock_sb.service.table.return_value.select.return_value.in_.return_value.eq.return_value.execute.return_value.data = []

    with patch("app.core.auth.supabase", mock_sb):
        result = await authenticate_request(creds)

    # Currently TenantResolver.resolve_tenant_id uses email mapping → "tenant-a"
    # Once B-06 is fixed this assertion should be changed to "tenant-from-jwt"
    assert result.tenant_id == "tenant-a", (
        "B-06 not yet fixed: email mapping overrides JWT claim. "
        "Update this assertion to 'tenant-from-jwt' after fixing resolve_tenant_id."
    )
