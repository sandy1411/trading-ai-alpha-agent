from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.enums import Market, ProviderType
from app.core.errors import FailClosedError, MissingCredentialsError
from app.data_providers.base import BaseDataProvider
from app.services.zerodha_token_service import load_access_token


class ZerodhaDataProvider(BaseDataProvider):
    provider_name = "ZERODHA_KITE"
    provider_type = ProviderType.BROKER_DATA
    base_url = "https://api.kite.trade"

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = client or httpx.Client(timeout=10)

    def validate_credentials(self) -> bool:
        if not (self.settings.zerodha_api_key and load_access_token()):
            raise MissingCredentialsError("zerodha_data_credentials_missing")
        return True

    def _headers(self) -> dict[str, str]:
        self.validate_credentials()
        access_token = load_access_token()
        return {
            "Authorization": (
                f"token {self.settings.zerodha_api_key}:{access_token}"
            ),
            "X-Kite-Version": "3",
        }

    def health_check(self, market: Market) -> bool:
        if market != Market.INDIA:
            return False
        response = self.client.get(f"{self.base_url}/user/profile", headers=self._headers())
        return response.status_code == 200

    def latest(self, symbol: str, market: Market) -> dict[str, Any]:
        if market != Market.INDIA:
            raise FailClosedError("zerodha_data_market_mismatch")
        response = self.client.get(
            f"{self.base_url}/quote", headers=self._headers(), params={"i": f"NSE:{symbol}"}
        )
        if response.status_code != 200:
            raise FailClosedError("zerodha_quote_unavailable")
        return dict(response.json())

    def historical_candles(
        self,
        *,
        instrument_token: int | str,
        interval: str,
        from_date: datetime,
        to_date: datetime,
    ) -> dict[str, Any]:
        if interval not in {"minute", "3minute", "5minute"}:
            raise FailClosedError("zerodha_historical_interval_not_allowed")
        response = self.client.get(
            f"{self.base_url}/instruments/historical/{instrument_token}/{interval}",
            headers=self._headers(),
            params={
                "from": from_date.strftime("%Y-%m-%d %H:%M:%S"),
                "to": to_date.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
        if response.status_code != 200:
            raise FailClosedError("zerodha_historical_candles_unavailable")
        return dict(response.json())
