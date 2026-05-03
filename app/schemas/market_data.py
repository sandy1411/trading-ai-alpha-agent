from __future__ import annotations

from datetime import datetime

from app.core.enums import FreshnessStatus, Market
from app.schemas.common import StrictSchema


class MarketDataStatus(StrictSchema):
    market: Market
    provider_name: str
    symbol: str | None = None
    freshness_status: FreshnessStatus
    last_success_at: datetime | None = None
    last_error: str = ""
