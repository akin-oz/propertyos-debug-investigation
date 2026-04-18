"""
TenantScope — the single mandatory dependency for every endpoint that reads or
writes tenant-scoped data.

Usage:

    @router.get("/dashboard/summary")
    async def get_summary(
        scope: TenantScope = Depends(require_tenant_scope),
        property_id: str = Query(...),
    ):
        pid = as_property_id(property_id)
        revenue = await get_revenue_summary(pid, scope.tenant_id)
        ...

Guarantees at the type level (mypy --strict):
  - scope.tenant_id is TenantId, never a raw str.
  - Passing scope.tenant_id to functions that expect str fails type-check.

Guarantees at runtime:
  - 401 if auth fails.
  - 401 if tenant_id could not be resolved (user has no tenant context).
  - Calling require_tenant_scope is the only way to get a TenantScope.
"""

from dataclasses import dataclass
from typing import List

from fastapi import Depends, HTTPException, status

from ..models.auth import AuthenticatedUser, Permission
from ..models.identifiers import TenantId
from .auth import authenticate_request


@dataclass(frozen=True)
class TenantScope:
    """Immutable proof that: (a) request is authenticated, (b) tenant_id is resolved."""

    user_id: str
    email: str
    tenant_id: TenantId
    is_admin: bool
    permissions: List[Permission]
    cities: List[str]


async def require_tenant_scope(
    user: AuthenticatedUser = Depends(authenticate_request),
) -> TenantScope:
    """
    FastAPI dependency.  Raises 401 when the authenticated user has no resolved
    tenant_id.  Use on every endpoint that touches tenant-scoped tables.
    """
    if not user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No tenant context could be resolved for this user.",
        )
    return TenantScope(
        user_id=user.id,
        email=user.email,
        tenant_id=user.tenant_id,  # already TenantId from AuthenticatedUser
        is_admin=user.is_admin,
        permissions=user.permissions,
        cities=user.cities,
    )
