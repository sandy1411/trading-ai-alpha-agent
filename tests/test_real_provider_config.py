from __future__ import annotations

from pathlib import Path

from app.brokers.broker_health import BrokerHealthChecker
from app.core.config import Settings
from app.core.enums import Market, ProviderStatus, ProviderType
from app.data_providers.provider_health import ProviderHealthChecker


def test_real_provider_config_requires_real_provider_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.real_provider_required is True
    assert settings.allow_fake_market_data is False


def test_no_production_class_or_file_contains_disallowed_provider_or_broker_names() -> None:
    root = Path(__file__).resolve().parents[1] / "app"
    forbidden = [
        "DummyBroker",
        "MockBroker",
        "FakeBroker",
        "DummyProvider",
        "MockProvider",
        "FakeProvider",
        "fake fill",
        "simulated fill",
    ]

    for path in root.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        for term in forbidden:
            assert term not in content, f"{term} found in {path}"


def test_env_file_is_ignored_by_git() -> None:
    gitignore = Path(__file__).resolve().parents[1] / ".gitignore"

    assert ".env" in gitignore.read_text(encoding="utf-8").splitlines()


def test_provider_health_exceptions_fail_closed() -> None:
    class ProviderStub:
        provider_name = "REAL_PROVIDER"
        provider_type = ProviderType.BROKER_DATA

        def validate_credentials(self) -> bool:
            return True

        def health_check(self, market: Market) -> bool:
            raise TimeoutError("network_timeout")

    health = ProviderHealthChecker().check(ProviderStub(), Market.INDIA)

    assert health.status == ProviderStatus.DOWN
    assert health.last_error == "provider_health_exception:TimeoutError"


def test_broker_health_exceptions_fail_closed() -> None:
    class BrokerStub:
        broker_name = "REAL_BROKER"

        def validate_credentials(self) -> bool:
            return True

        def check_session(self) -> bool:
            raise TimeoutError("network_timeout")

    health = BrokerHealthChecker().check(BrokerStub(), Market.INDIA)

    assert health.trading_enabled is False
    assert health.rejection_reasons == ["broker_health_exception:TimeoutError"]
