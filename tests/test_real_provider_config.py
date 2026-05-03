from __future__ import annotations

from pathlib import Path

from app.core.config import Settings


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
