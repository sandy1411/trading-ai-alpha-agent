from __future__ import annotations

from app.core.config import Settings
from app.data_providers.fx_provider import FXProvider


class FXClientStub:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        return FXResponseStub()


class FXResponseStub:
    status_code = 200

    def json(self) -> dict:
        return {
            "Realtime Currency Exchange Rate": {
                "5. Exchange Rate": "83.25",
            }
        }


def test_fx_provider_reuses_fresh_usd_inr_rate(monkeypatch) -> None:
    monkeypatch.setattr(FXProvider, "_usd_inr_cache", None)
    client = FXClientStub()
    provider = FXProvider(
        Settings(
            _env_file=None,
            alpha_vantage_api_key="test-key",
            fx_staleness_minutes=60,
        ),
        client=client,
    )

    first = provider.get_usd_inr()
    second = provider.get_usd_inr()

    assert first.rate == 83.25
    assert second.rate == 83.25
    assert client.calls == 1
