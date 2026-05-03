from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.enums import Market, ProviderType
from app.core.errors import FailClosedError, MissingCredentialsError
from app.data_providers.base import BaseDataProvider


class AlpacaDataProvider(BaseDataProvider):
    provider_name = "ALPACA"
    provider_type = ProviderType.BROKER_DATA
    data_url = "https://data.alpaca.markets"

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = client or httpx.Client(timeout=3)

    def validate_credentials(self) -> bool:
        if not (self.settings.alpaca_api_key and self.settings.alpaca_secret_key):
            raise MissingCredentialsError("alpaca_data_credentials_missing")
        return True

    def _headers(self) -> dict[str, str]:
        self.validate_credentials()
        return {
            "APCA-API-KEY-ID": self.settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": self.settings.alpaca_secret_key,
        }

    def health_check(self, market: Market) -> bool:
        return market == Market.US and self.validate_credentials()

    def latest(self, symbol: str, market: Market) -> dict[str, Any]:
        if market != Market.US:
            raise FailClosedError("alpaca_data_market_mismatch")
        try:
            response = self.client.get(
                f"{self.data_url}/v2/stocks/{symbol}/bars/latest",
                headers=self._headers(),
                params={"feed": self.settings.alpaca_data_feed},
            )
        except httpx.HTTPError as exc:
            raise FailClosedError("alpaca_bar_request_failed") from exc
        if response.status_code != 200:
            raise FailClosedError("alpaca_bar_unavailable")
        payload = dict(response.json())
        bar = payload.get("bar")
        if not isinstance(bar, dict):
            raise FailClosedError("alpaca_bar_missing")
        close_price = bar.get("c")
        if close_price is None:
            raise FailClosedError("alpaca_close_price_missing")
        return {
            "data": {
                f"US:{symbol}": {
                    "last_price": float(close_price),
                    "average_price": float(bar.get("vw") or close_price),
                    "volume": float(bar.get("v") or 0),
                    "ohlc": {
                        "open": float(bar.get("o") or close_price),
                        "high": float(bar.get("h") or close_price),
                        "low": float(bar.get("l") or close_price),
                        "close": float(close_price),
                    },
                    "timestamp": bar.get("t"),
                    "provider_feed": self.settings.alpaca_data_feed,
                }
            },
            "raw": payload,
        }
