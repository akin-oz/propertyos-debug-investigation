from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, WithJsonSchema
from pydantic.functional_serializers import PlainSerializer

# ── Type alias ────────────────────────────────────────────────────────────────
#
# MoneyString keeps Decimal precision in Python but serialises to a two-decimal
# JSON string ("1234.56") so that TypeScript clients can represent the value
# without IEEE-754 float drift.
#
# WithJsonSchema overrides the OpenAPI component so the emitted schema reads:
#   { type: string, pattern: "^\d+\.\d{2}$" }
# instead of the Pydantic default of type: number.
MoneyString = Annotated[
    Decimal,
    PlainSerializer(lambda d: str(d.quantize(Decimal("0.01"))), return_type=str, when_used="json"),
    WithJsonSchema(
        {
            "type": "string",
            "pattern": r"^\d+\.\d{2}$",
            "example": "1234.56",
            "description": "Decimal-safe revenue string (2 d.p., no float drift)",
        }
    ),
]


# ── Response models ───────────────────────────────────────────────────────────


class DashboardSummaryResponse(BaseModel):
    property_id: str = Field(description="Property identifier")
    total_revenue: MoneyString = Field(description="Total revenue as decimal string")
    currency: str = Field(
        min_length=3,
        max_length=3,
        pattern="^[A-Z]{3}$",
        description="ISO 4217 currency code",
        json_schema_extra={"example": "USD"},
    )
    reservations_count: int = Field(ge=0, description="Number of reservations included")


class PropertyItem(BaseModel):
    id: str
    name: str
    timezone: str = Field(default="UTC", description="IANA timezone name")


class PropertiesResponse(BaseModel):
    data: list[PropertyItem]
    total: int = Field(ge=0)
