from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.brokers.alpaca_broker import AlpacaBroker
from app.brokers.broker_health import BrokerHealthChecker
from app.brokers.zerodha_broker import ZerodhaBroker
from app.core.enums import Market
from app.schemas.broker import BrokerHealth


class BrokerService:
    def __init__(self) -> None:
        self.checker = BrokerHealthChecker()
        self.cache_ttl = timedelta(seconds=30)
        self._cache: list[BrokerHealth] | None = None
        self._cache_at: datetime | None = None

    def statuses(self, force_refresh: bool = False) -> list[BrokerHealth]:
        now = datetime.now(UTC)
        if (
            not force_refresh
            and self._cache is not None
            and self._cache_at is not None
            and now - self._cache_at <= self.cache_ttl
        ):
            return self._cache

        self._cache = [
            self.checker.check(ZerodhaBroker(), Market.INDIA),
            self.checker.check(AlpacaBroker(), Market.US),
        ]
        self._cache_at = now
        return self._cache


broker_service = BrokerService()
