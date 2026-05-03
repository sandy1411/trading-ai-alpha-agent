from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.core.enums import FreshnessStatus
from app.core.time_utils import utc_now
from app.schemas.common import StrictSchema


class FXRateStatus(StrictSchema):
    base_currency: str = "USD"
    quote_currency: str = "INR"
    rate: float | None = Field(default=None, gt=0)
    freshness_status: FreshnessStatus = FreshnessStatus.MISSING
    last_success_at: datetime | None = None
    source: str = ""
    stale_after_minutes: int = Field(default=60, ge=1)

    @property
    def is_fresh(self) -> bool:
        if self.freshness_status != FreshnessStatus.FRESH or self.rate is None or self.last_success_at is None:
            return False
        age_seconds = (utc_now() - self.last_success_at).total_seconds()
        return age_seconds <= self.stale_after_minutes * 60
