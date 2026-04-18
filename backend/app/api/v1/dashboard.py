from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.tenant_scope import TenantScope, require_tenant_scope
from app.models.dashboard import DashboardSummaryResponse
from app.models.identifiers import as_property_id
from app.services.cache import get_revenue_summary

router = APIRouter()


@router.get(
    "/dashboard/summary",
    response_model=DashboardSummaryResponse,
    responses={
        401: {"description": "Missing or invalid authentication, or no tenant context"},
        404: {"description": "Property not found or belongs to a different tenant"},
        503: {"description": "Revenue service temporarily unavailable"},
    },
)
async def get_dashboard_summary(
    scope: TenantScope = Depends(require_tenant_scope),
    property_id: str = Query(..., description="Property identifier", min_length=1),
) -> DashboardSummaryResponse:
    pid = as_property_id(property_id)

    revenue_data = await get_revenue_summary(pid, scope.tenant_id)
    total_revenue = Decimal(revenue_data["total"]).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    return DashboardSummaryResponse(
        property_id=revenue_data["property_id"],
        total_revenue=total_revenue,
        currency=revenue_data["currency"],
        reservations_count=revenue_data["count"],
    )
