from fastapi import APIRouter, Depends, HTTPException

from ...core.tenant_scope import TenantScope, require_tenant_scope
from ...database import supabase
from ...models.dashboard import PropertiesResponse

router = APIRouter()


@router.get(
    "/properties",
    response_model=PropertiesResponse,
    responses={401: {"description": "Missing or invalid authentication, or no tenant context"}},
)
async def get_properties(
    scope: TenantScope = Depends(require_tenant_scope),
) -> PropertiesResponse:
    try:
        result = (
            supabase.table("properties")
            .select("id, name, timezone")
            .eq("tenant_id", str(scope.tenant_id))
            .execute()
        )
        data = result.data or []
        return PropertiesResponse(data=data, total=len(data))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch properties")
