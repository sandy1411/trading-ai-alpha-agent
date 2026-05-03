from __future__ import annotations

from typing import ClassVar

import httpx

from app.core.config import Settings, get_settings
from app.core.enums import FreshnessStatus, Market, ProviderType
from app.core.errors import FailClosedError, MissingCredentialsError
from app.core.time_utils import utc_now
from app.data_providers.base import BaseDataProvider
from app.schemas.fx import FXRateStatus


class FXProvider(BaseDataProvider):
    provider_name = "ALPHA_VANTAGE_FX"
    provider_type = ProviderType.FX
    base_url = "https://www.alphavantage.co/query"
    _usd_inr_cache: ClassVar[FXRateStatus | None] = None

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = client or httpx.Client(timeout=3)

    def validate_credentials(self) -> bool:
        if not self.settings.alpha_vantage_api_key:
            raise MissingCredentialsError("fx_provider_api_key_missing")
        return True

    def health_check(self, market: Market) -> bool:
        return market in {Market.INDIA, Market.US} and self.validate_credentials()

    def latest(self, symbol: str, market: Market) -> dict:
        return self.get_usd_inr().model_dump()

    def get_usd_inr(self) -> FXRateStatus:
        self.validate_credentials()
        if self._usd_inr_cache is not None and self._usd_inr_cache.is_fresh:
            return self._usd_inr_cache
        response = self.client.get(
            self.base_url,
            params={
                "function": "CURRENCY_EXCHANGE_RATE",
                "from_currency": "USD",
                "to_currency": "INR",
                "apikey": self.settings.alpha_vantage_api_key,
            },
        )
        if response.status_code != 200:
            raise FailClosedError("usd_inr_unavailable")
        payload = response.json().get("Realtime Currency Exchange Rate", {})
        rate_text = payload.get("5. Exchange Rate")
        if not rate_text:
            raise FailClosedError("usd_inr_rate_missing")
        self.__class__._usd_inr_cache = FXRateStatus(
            rate=float(rate_text),
            freshness_status=FreshnessStatus.FRESH,
            last_success_at=utc_now(),
            source=self.provider_name,
            stale_after_minutes=self.settings.fx_staleness_minutes,
        )
        return self._usd_inr_cache
