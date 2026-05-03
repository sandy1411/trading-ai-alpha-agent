from __future__ import annotations

from typing import Any

import httpx

from app.core.enums import Market, ProviderType
from app.core.errors import FailClosedError
from app.data_providers.base import BaseDataProvider


class YahooResearchProvider(BaseDataProvider):
    provider_name = "YAHOO_RESEARCH"
    provider_type = ProviderType.MARKET_DATA
    base_url = "https://query1.finance.yahoo.com"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(timeout=10)

    def validate_credentials(self) -> bool:
        return True

    def health_check(self, market: Market) -> bool:
        return market in {Market.INDIA, Market.US}

    def latest(self, symbol: str, market: Market) -> dict[str, Any]:
        suffix = ".NS" if market == Market.INDIA and "." not in symbol else ""
        response = self.client.get(f"{self.base_url}/v7/finance/quote", params={"symbols": f"{symbol}{suffix}"})
        if response.status_code != 200:
            raise FailClosedError("yahoo_quote_unavailable")
        return dict(response.json())
