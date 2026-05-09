from __future__ import annotations

from app.core.config import Settings
from app.core.enums import TradingMode


def test_default_config_is_shadow_live_disabled_kill_on() -> None:
    settings = Settings(_env_file=None)

    assert settings.trading_mode == TradingMode.SHADOW_LIVE_REAL_DATA
    assert settings.live_trading_enabled is False
    assert settings.kill_switch is True
    assert settings.intraday_min_total_samples == 100_000
    assert settings.intraday_min_samples_per_market == 25_000
    assert settings.intraday_min_stop_loss_coverage == 0.98
    assert settings.intraday_profit_giveback_exit_pct == 0.25
    assert settings.intraday_min_profit_lock_inr == 300
    assert settings.intraday_profit_booking_enabled is True
    assert settings.intraday_profit_booking_target_progress_pct == 0.45
    assert settings.intraday_profit_booking_min_pnl_inr == 250
    assert settings.intraday_profit_booking_min_pnl_pct == 0.003
    assert settings.intraday_shadow_exit_enabled is True
    assert settings.intraday_reentry_cooldown_minutes == 20


def test_live_autonomous_requires_explicit_safety_flags() -> None:
    settings = Settings(_env_file=None, trading_mode=TradingMode.LIVE_AUTONOMOUS)

    errors = settings.live_mode_safety_errors()

    assert "live_trading_enabled_false" in errors
    assert "kill_switch_enabled" in errors
