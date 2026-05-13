from __future__ import annotations

from dataclasses import dataclass, field

from app.intraday.config import IntradayShadowConfig
from app.intraday.models import (
    DataQualityReport,
    Direction,
    MarketRegime,
    RiskApproval,
    ScoredSignal,
    SignalDecision,
    VirtualPosition,
    VirtualPositionStatus,
)


@dataclass
class ShadowRiskState:
    daily_realized_pnl: float = 0.0
    weekly_realized_pnl: float = 0.0
    trades_today: int = 0
    consecutive_losses: int = 0
    open_positions: list[VirtualPosition] = field(default_factory=list)


class RiskManager:
    def __init__(self, config: IntradayShadowConfig | None = None) -> None:
        self.config = config or IntradayShadowConfig.from_settings()

    def approve(
        self,
        scored: ScoredSignal,
        *,
        data_quality: DataQualityReport,
        state: ShadowRiskState | None = None,
        current_regime: MarketRegime | None = None,
    ) -> RiskApproval:
        risk_state = state or ShadowRiskState()
        signal = scored.signal
        reasons: list[str] = []
        if scored.decision != SignalDecision.VALID:
            reasons.append(f"signal_not_valid:{scored.decision.value}")
        if not data_quality.ok:
            reasons.extend(f"data_quality:{reason}" for reason in data_quality.reasons)
        if signal.stop_loss <= 0:
            reasons.append("stop_loss_missing")
        stop_distance = abs(signal.entry_price - signal.stop_loss)
        if stop_distance <= 0:
            reasons.append("stop_distance_invalid")
        reward_risk = signal.risk_reward_ratio
        if reward_risk < self.config.min_reward_to_risk:
            reasons.append("reward_risk_below_threshold")
        spread = signal.market_snapshot.get("spread_pct")
        if spread is not None and float(spread) > self.config.max_spread_pct:
            reasons.append("spread_too_wide")
        if risk_state.daily_realized_pnl <= -self.config.capital * self.config.max_daily_loss_percent:
            reasons.append("daily_loss_limit_reached")
        if risk_state.weekly_realized_pnl <= -self.config.capital * self.config.max_weekly_loss_percent:
            reasons.append("weekly_loss_limit_reached")
        if risk_state.trades_today >= self.config.max_trades_per_day:
            reasons.append("max_trades_per_day_reached")
        if risk_state.consecutive_losses >= self.config.max_consecutive_losses:
            reasons.append("max_consecutive_losses_reached")
        open_count = len([pos for pos in risk_state.open_positions if pos.status == VirtualPositionStatus.OPEN])
        if open_count >= self.config.max_open_positions:
            reasons.append("max_open_positions_reached")
        if signal.direction == Direction.SHORT and not self.config.allow_shorts:
            reasons.append("shorts_disabled")
        if current_regime is not None and current_regime != signal.regime_at_signal:
            reasons.append("market_regime_changed")
        if signal.regime_at_signal == MarketRegime.SIDEWAYS and not self.config.allow_sideways_trades:
            reasons.append("sideways_regime_blocked")
        if signal.regime_at_signal == MarketRegime.HIGH_VOLATILITY and not self.config.allow_high_volatility_trades:
            reasons.append("high_volatility_blocked")

        allowed_risk = self.config.capital * self.config.risk_per_trade_percent
        quantity = int(allowed_risk // stop_distance) if stop_distance > 0 else 0
        if quantity <= 0:
            reasons.append("quantity_zero")
        capital_required = quantity * signal.entry_price
        metrics = {
            "allowed_risk_amount": allowed_risk,
            "stop_distance": stop_distance,
            "reward_risk": reward_risk,
            "quantity_by_risk": quantity,
            "capital_required": capital_required,
            "daily_realized_pnl": risk_state.daily_realized_pnl,
            "trades_today": risk_state.trades_today,
            "consecutive_losses": risk_state.consecutive_losses,
        }
        deduped = list(dict.fromkeys(reasons))
        if deduped:
            return RiskApproval(False, rejection_reasons=deduped, metrics=metrics)
        return RiskApproval(
            True,
            quantity=quantity,
            risk_amount=quantity * stop_distance,
            capital_required=capital_required,
            metrics=metrics,
        )

