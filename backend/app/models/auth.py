from pydantic import BaseModel, EmailStr
from typing import Any, List, Optional

from .identifiers import TenantId


class User(BaseModel):
    id: str
    email: EmailStr
    permissions: List[dict[str, Any]]
    cities: List[str]
    is_admin: bool


class Permission(BaseModel):
    section: str
    action: str


class AuthenticatedUser(BaseModel):
    id: str
    email: str
    permissions: List[Permission]
    cities: List[str]
    is_admin: bool
    # Optional at model level — require_tenant_scope raises 401 when None.
    tenant_id: Optional[TenantId] = None
