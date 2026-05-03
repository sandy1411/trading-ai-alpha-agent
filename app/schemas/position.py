from __future__ import annotations

from pydantic import Field

from app.core.enums import AssetClass, Market
from app.schemas.common import StrictSchema


class OpenPosition(StrictSchema):
    market: Market
    symbol: str
    asset_class: AssetClass
    quantity: int = Field(ge=0)
    average_price: float = Field(ge=0)
    market_value_inr: float = Field(ge=0)
    sector: str | None = None
