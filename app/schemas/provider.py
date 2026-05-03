from __future__ import annotations

from datetime import datetime

from app.core.enums import FreshnessStatus, Market, ProviderStatus, ProviderType
from app.schemas.common import StrictSchema


class ProviderHealth(StrictSchema):
    provider_name: str
    provider_type: ProviderType
    market: Market
    status: ProviderStatus
    last_success_at: datetime | None = None
    last_error: str = ""
    freshness_status: FreshnessStatus = FreshnessStatus.MISSING

    @property
    def is_healthy_for_live(self) -> bool:
        return self.status == ProviderStatus.OK and self.freshness_status == FreshnessStatus.FRESH
