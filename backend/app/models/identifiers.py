"""
Domain-opaque NewTypes for tenant-scoped identifiers.

mypy --strict refuses to let a raw `str` flow into a function that declares
`TenantId` or `PropertyId`.  At runtime the types are plain strings — zero
overhead.  Construction helpers (`as_tenant_id`, `as_property_id`) are the
only blessed entry-points; call them at the boundary where the value is
first trusted (auth resolution, query-param extraction).
"""

from typing import NewType

# Opaque identifier for a tenant — never a raw str downstream of auth.
TenantId = NewType("TenantId", str)

# Opaque identifier for a property — prevents swapping property_id / tenant_id.
PropertyId = NewType("PropertyId", str)


def as_tenant_id(value: str) -> TenantId:
    """Cast a validated string to TenantId.  Only call after auth resolution."""
    if not value or not value.strip():
        raise ValueError("TenantId must be a non-empty string")
    return TenantId(value)


def as_property_id(value: str) -> PropertyId:
    """Cast a validated string to PropertyId.  Only call at request boundary."""
    if not value or not value.strip():
        raise ValueError("PropertyId must be a non-empty string")
    return PropertyId(value)
