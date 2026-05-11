from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.enums import Market, ProviderType
from app.core.errors import FailClosedError, MissingCredentialsError
from app.data_providers.base import BaseDataProvider


class AlphaVantageProvider(BaseDataProvider):
    provider_name = "ALPHA_VANTAGE"
    provider_type = ProviderType.MARKET_DATA
    base_url = "https://www.alphavantage.co/query"

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = client or httpx.Client(timeout=3)

    def validate_credentials(self) -> bool:
        if not self.settings.alpha_vantage_api_key:
            raise MissingCredentialsError("alpha_vantage_api_key_missing")
        return True

    def health_check(self, market: Market) -> bool:
        return market in {Market.INDIA, Market.US} and self.validate_credentials()

    def latest(self, symbol: str, market: Market) -> dict[str, Any]:
        self.validate_credentials()
        response = self.client.get(
            self.base_url,
            params={
                "function": "GLOBAL_QUOTE",
                "symbol": symbol,
                "apikey": self.settings.alpha_vantage_api_key,
            },
        )
        if response.status_code != 200:
            raise FailClosedError("alpha_vantage_quote_unavailable")
        return dict(response.json())

    def news_sentiment(
        self,
        *,
        tickers: list[str] | None = None,
        topics: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        self.validate_credentials()
        params: dict[str, str] = {
            "function": "NEWS_SENTIMENT",
            "apikey": self.settings.alpha_vantage_api_key,
            "sort": "LATEST",
            "limit": "50",
        }
        if tickers:
            params["tickers"] = ",".join(tickers)
        if topics:
            params["topics"] = ",".join(topics)
        response = self.client.get(self.base_url, params=params)
        if response.status_code != 200:
            raise FailClosedError("alpha_vantage_news_unavailable")
        payload = response.json()
        feed = payload.get("feed", [])
        if not isinstance(feed, list):
            raise FailClosedError("alpha_vantage_news_payload_invalid")
        return [item for item in feed if isinstance(item, dict)]

    @staticmethod
    def parse_news_time(value: str | None) -> datetime:
        if not value:
            return datetime.now(UTC)
        try:
            return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
        except ValueError:
            return datetime.now(UTC)
