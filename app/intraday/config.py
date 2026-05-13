from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class IntradayShadowConfig:
    capital: float
    risk_per_trade_percent: float
    max_daily_loss_percent: float
    max_weekly_loss_percent: float
    max_open_positions: int
    max_trades_per_day: int
    max_consecutive_losses: int
    min_reward_to_risk: float
    allow_averaging_down: bool
    allow_martingale: bool
    allow_shorts: bool
    allow_sideways_trades: bool
    allow_high_volatility_trades: bool
    min_signal_score: int
    watch_score: int
    max_spread_pct: float
    max_data_age_seconds: int
    max_entry_move_pct: float
    slippage_bps: float
    latency_ms: int
    no_new_trade_after: str
    force_close_time: str
    readiness_min_sessions: int
    readiness_min_trades: int
    readiness_profit_factor: float
    readiness_max_drawdown_pct: float

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "IntradayShadowConfig":
        resolved = settings or get_settings()
        return cls(
            capital=resolved.intraday_shadow_capital_inr,
            risk_per_trade_percent=resolved.intraday_shadow_risk_per_trade_pct,
            max_daily_loss_percent=resolved.intraday_shadow_max_daily_loss_pct,
            max_weekly_loss_percent=resolved.intraday_shadow_max_weekly_loss_pct,
            max_open_positions=resolved.intraday_shadow_max_open_positions,
            max_trades_per_day=resolved.intraday_shadow_max_trades_per_day,
            max_consecutive_losses=resolved.intraday_shadow_max_consecutive_losses,
            min_reward_to_risk=resolved.intraday_shadow_min_reward_risk,
            allow_averaging_down=False,
            allow_martingale=False,
            allow_shorts=resolved.intraday_shadow_allow_shorts,
            allow_sideways_trades=resolved.intraday_shadow_allow_sideways_trades,
            allow_high_volatility_trades=resolved.intraday_shadow_allow_high_volatility_trades,
            min_signal_score=resolved.intraday_shadow_min_signal_score,
            watch_score=resolved.intraday_shadow_watch_score,
            max_spread_pct=resolved.intraday_shadow_max_spread_pct,
            max_data_age_seconds=resolved.intraday_shadow_max_data_age_seconds,
            max_entry_move_pct=resolved.intraday_shadow_max_entry_move_pct,
            slippage_bps=resolved.intraday_shadow_slippage_bps,
            latency_ms=resolved.intraday_shadow_latency_ms,
            no_new_trade_after=resolved.intraday_shadow_no_new_trade_after,
            force_close_time=resolved.intraday_shadow_force_close_time,
            readiness_min_sessions=resolved.intraday_shadow_live_readiness_min_sessions,
            readiness_min_trades=resolved.intraday_shadow_live_readiness_min_trades,
            readiness_profit_factor=resolved.intraday_shadow_live_readiness_profit_factor,
            readiness_max_drawdown_pct=resolved.intraday_shadow_live_readiness_max_drawdown_pct,
        )

