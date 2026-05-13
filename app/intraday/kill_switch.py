from __future__ import annotations

from dataclasses import dataclass, field

from app.intraday.config import IntradayShadowConfig
from app.intraday.models import DataQualityReport
from app.intraday.risk_manager import ShadowRiskState


@dataclass
class ShadowKillSwitchState:
    triggered: bool = False
    reasons: list[str] = field(default_factory=list)
    manual_reset_required: bool = True


class KillSwitchManager:
    def __init__(self, config: IntradayShadowConfig | None = None) -> None:
        self.config = config or IntradayShadowConfig.from_settings()
        self.state = ShadowKillSwitchState()

    def evaluate(
        self,
        *,
        risk_state: ShadowRiskState,
        data_quality: DataQualityReport | None = None,
        rejected_signal_count: int = 0,
        api_latency_ms: float | None = None,
    ) -> ShadowKillSwitchState:
        reasons = list(self.state.reasons)
        if risk_state.daily_realized_pnl <= -self.config.capital * self.config.max_daily_loss_percent:
            reasons.append("daily_loss_limit_hit")
        if risk_state.weekly_realized_pnl <= -self.config.capital * self.config.max_weekly_loss_percent:
            reasons.append("weekly_loss_limit_hit")
        if risk_state.consecutive_losses >= self.config.max_consecutive_losses:
            reasons.append("max_consecutive_losses_hit")
        if data_quality is not None and not data_quality.ok:
            reasons.extend(f"data_quality:{reason}" for reason in data_quality.reasons)
        if rejected_signal_count > 50:
            reasons.append("too_many_rejected_signals")
        if api_latency_ms is not None and api_latency_ms > 2000:
            reasons.append("api_latency_too_high")
        deduped = list(dict.fromkeys(reasons))
        self.state = ShadowKillSwitchState(triggered=bool(deduped), reasons=deduped)
        return self.state

    def reset(self) -> None:
        self.state = ShadowKillSwitchState()

