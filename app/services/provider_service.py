from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.enums import Market
from app.data_providers.alpha_vantage import AlphaVantageProvider
from app.data_providers.alpaca_data import AlpacaDataProvider
from app.data_providers.finnhub import FinnhubProvider
from app.data_providers.fx_provider import FXProvider
from app.data_providers.provider_health import ProviderHealthChecker
from app.data_providers.zerodha_data import ZerodhaDataProvider
from app.schemas.provider import ProviderHealth


class ProviderService:
    def __init__(self) -> None:
        self.checker = ProviderHealthChecker()
        self.cache_ttl = timedelta(seconds=30)
        self._cache: list[ProviderHealth] | None = None
        self._cache_at: datetime | None = None

    def statuses(self, force_refresh: bool = False) -> list[ProviderHealth]:
        now = datetime.now(UTC)
        if (
            not force_refresh
            and self._cache is not None
            and self._cache_at is not None
            and now - self._cache_at <= self.cache_ttl
        ):
            return self._cache

        self._cache = [
            self.checker.check(ZerodhaDataProvider(), Market.INDIA),
            self.checker.check(AlpacaDataProvider(), Market.US),
            self.checker.check(FXProvider(), Market.US),
            self.checker.check(AlphaVantageProvider(), Market.US),
            self.checker.check(FinnhubProvider(), Market.US),
        ]
        self._cache_at = now
        return self._cache


provider_service = ProviderService()
