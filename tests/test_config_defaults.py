from __future__ import annotations

from app.core.config import Settings
from app.core.enums import TradingMode


def test_default_config_is_shadow_live_disabled_kill_on() -> None:
    settings = Settings(_env_file=None)

    assert settings.trading_mode == TradingMode.SHADOW_LIVE_REAL_DATA
    assert settings.live_trading_enabled is False
    assert settings.kill_switch is True


def test_live_autonomous_requires_explicit_safety_flags() -> None:
    settings = Settings(_env_file=None, trading_mode=TradingMode.LIVE_AUTONOMOUS)

    errors = settings.live_mode_safety_errors()

    assert "live_trading_enabled_false" in errors
    assert "kill_switch_enabled" in errors
