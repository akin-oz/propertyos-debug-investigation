from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional
import logging
from zoneinfo import ZoneInfo
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.core.database_pool import db_pool
from app.models.identifiers import TenantId, PropertyId

logger = logging.getLogger(__name__)


async def calculate_monthly_revenue(
    property_id: PropertyId,
    tenant_id: TenantId,
    month: int,
    year: int,
    timezone: str = "UTC",
    db_session: Optional[AsyncSession] = None,
) -> Decimal:
    """
    Revenue for a specific month in the property's local timezone.

    Month boundaries are derived in the property timezone so that a reservation
    at 2024-02-29 23:30 UTC is correctly attributed to March when the property
    is in UTC+1, instead of being counted as February.
    """
    tz = ZoneInfo(timezone)
    start_local = datetime(year, month, 1, tzinfo=tz)
    if month < 12:
        end_local = datetime(year, month + 1, 1, tzinfo=tz)
    else:
        end_local = datetime(year + 1, 1, 1, tzinfo=tz)

    start_utc = start_local.astimezone(ZoneInfo("UTC"))
    end_utc = end_local.astimezone(ZoneInfo("UTC"))

    query = text("""
        SELECT SUM(total_amount) AS total
        FROM reservations
        WHERE property_id = :property_id
          AND tenant_id   = :tenant_id
          AND check_in_date >= :start
          AND check_in_date  < :end
    """)

    if db_session:
        result = await db_session.execute(
            query,
            {
                "property_id": str(property_id),
                "tenant_id": str(tenant_id),
                "start": start_utc,
                "end": end_utc,
            },
        )
        row = result.fetchone()
        return Decimal(str(row[0])) if row and row[0] is not None else Decimal("0")

    return Decimal("0")


async def calculate_total_revenue(
    property_id: PropertyId,
    tenant_id: TenantId,
) -> Dict[str, Any]:
    """
    All-time revenue for a property, filtered to the given tenant.

    The DB session is opened with the tenant_id so PostgreSQL RLS policies
    (migration 001_rls_policies.sql) apply as a second line of defence —
    even if the WHERE clause were somehow removed, the DB returns only rows
    owned by this tenant.
    """
    try:
        if not db_pool.session_factory:
            await db_pool.initialize()

        async with db_pool.get_session(tenant_id=tenant_id) as session:
            query = text("""
                SELECT
                    property_id,
                    currency,
                    SUM(total_amount)  AS total_revenue,
                    COUNT(*)           AS reservation_count
                FROM reservations
                WHERE property_id = :property_id
                  AND tenant_id   = :tenant_id
                GROUP BY property_id, currency
            """)

            result = await session.execute(
                query,
                {"property_id": str(property_id), "tenant_id": str(tenant_id)},
            )
            row = result.fetchone()

            if row:
                total_revenue = Decimal(str(row.total_revenue))
                return {
                    "property_id": str(property_id),
                    "tenant_id": str(tenant_id),
                    "total": str(total_revenue),
                    "currency": row.currency or "USD",
                    "count": row.reservation_count,
                }
            return {
                "property_id": str(property_id),
                "tenant_id": str(tenant_id),
                "total": "0.00",
                "currency": "USD",
                "count": 0,
            }

    except Exception as e:
        logger.error("Database error for %s (tenant: %s): %s", property_id, tenant_id, e)
        raise HTTPException(status_code=503, detail="Revenue data temporarily unavailable")
