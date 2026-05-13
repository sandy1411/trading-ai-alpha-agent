from __future__ import annotations

from app.intraday.config import IntradayShadowConfig


class LiveReadinessEvaluator:
    def __init__(self, config: IntradayShadowConfig | None = None) -> None:
        self.config = config or IntradayShadowConfig.from_settings()

    def evaluate(
        self,
        *,
        shadow_sessions: int,
        valid_trades: int,
        expectancy: float,
        profit_factor: float,
        max_drawdown_pct: float,
        unresolved_execution_bugs: int = 0,
        data_quality_issues: int = 0,
        overfitting_warning: bool = True,
        manual_approval: bool = False,
    ) -> dict[str, object]:
        reasons: list[str] = []
        if shadow_sessions < self.config.readiness_min_sessions:
            reasons.append("minimum_30_shadow_sessions_not_met")
        if valid_trades < self.config.readiness_min_trades:
            reasons.append("minimum_100_valid_shadow_trades_not_met")
        if expectancy <= 0:
            reasons.append("net_expectancy_not_positive_after_costs")
        if profit_factor < self.config.readiness_profit_factor:
            reasons.append("profit_factor_below_threshold")
        if max_drawdown_pct > self.config.readiness_max_drawdown_pct:
            reasons.append("drawdown_above_threshold")
        if unresolved_execution_bugs:
            reasons.append("unresolved_execution_simulation_bugs")
        if data_quality_issues:
            reasons.append("unresolved_data_quality_issues")
        if overfitting_warning:
            reasons.append("overfitting_warning_active")
        if not manual_approval:
            reasons.append("manual_approval_missing")
        return {
            "live_readiness_status": "BLOCKED" if reasons else "ALLOWED",
            "reasons": reasons,
            "shadow_sessions": shadow_sessions,
            "valid_trades": valid_trades,
            "expectancy": expectancy,
            "profit_factor": profit_factor,
            "max_drawdown_pct": max_drawdown_pct,
            "manual_approval": manual_approval,
            "live_orders_enabled": False,
        }

