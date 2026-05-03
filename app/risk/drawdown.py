from __future__ import annotations

from app.schemas.portfolio import PortfolioSnapshot
from app.schemas.risk import RiskConfig


def drawdown_reasons(portfolio: PortfolioSnapshot, risk_config: RiskConfig) -> list[str]:
    reasons: list[str] = []
    daily_loss_pct = abs(min(portfolio.daily_pnl_inr, 0)) / portfolio.total_value_inr
    weekly_loss_pct = abs(min(portfolio.weekly_pnl_inr, 0)) / portfolio.total_value_inr
    if daily_loss_pct > risk_config.max_daily_loss_pct:
        reasons.append("daily_loss_limit_exceeded")
    if weekly_loss_pct > risk_config.max_weekly_loss_pct:
        reasons.append("weekly_loss_limit_exceeded")
    if portfolio.monthly_drawdown_pct > risk_config.max_monthly_drawdown_pct:
        reasons.append("monthly_drawdown_limit_exceeded")
    if portfolio.total_drawdown_pct > risk_config.max_total_drawdown_pct:
        reasons.append("total_drawdown_limit_exceeded")
    return reasons
