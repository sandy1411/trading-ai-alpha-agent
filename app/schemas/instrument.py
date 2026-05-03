from __future__ import annotations

from app.core.enums import AssetClass, Market
from app.schemas.common import StrictSchema


class InstrumentRead(StrictSchema):
    id: str
    market: Market
    symbol: str
    name: str
    asset_class: AssetClass
    currency: str
    exchange: str = ""
    sector: str | None = None
    is_active: bool = True
