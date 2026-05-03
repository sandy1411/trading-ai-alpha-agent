from __future__ import annotations

import httpx
import pytest

from app.brokers.zerodha_broker import ZerodhaBroker
from app.core.config import Settings
from app.core.errors import FailClosedError


def test_zerodha_account_health_requires_margins_and_cnc_equity() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user/profile":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "user_id": "USER1",
                        "exchanges": ["NSE"],
                        "products": ["CNC"],
                    }
                },
            )
        if request.url.path == "/user/margins":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "equity": {
                            "enabled": True,
                            "net": 125000.0,
                            "available": {"cash": 100000.0},
                        }
                    }
                },
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    broker = ZerodhaBroker(settings=_zerodha_settings(), client=client)

    account = broker.get_account()

    assert account.status == "ACTIVE"
    assert account.trading_enabled is True
    assert account.cash == 100000
    assert account.buying_power == 125000


def test_zerodha_profile_without_margins_fails_closed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user/profile":
            return httpx.Response(200, json={"data": {"user_id": "USER1"}})
        if request.url.path == "/user/margins":
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    broker = ZerodhaBroker(settings=_zerodha_settings(), client=client)

    with pytest.raises(FailClosedError, match="zerodha_margins_unavailable"):
        broker.get_account()


def _zerodha_settings() -> Settings:
    return Settings(
        _env_file=None,
        zerodha_api_key="test-key",
        zerodha_api_secret="test-secret",
        zerodha_access_token="test-token",
    )
