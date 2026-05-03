from __future__ import annotations

from app.core.enums import Market
from app.schemas.portfolio import PortfolioSnapshot
from app.schemas.risk import RiskConfig


def exposure_reasons(
    market: Market,
    portfolio: PortfolioSnapshot,
    risk_config: RiskConfig,
    order_value_inr: float,
    sector: str | None = None,
) -> list[str]:
    reasons: list[str] = []
    total_equity_after = portfolio.equity_exposure_inr + order_value_inr
    if total_equity_after > portfolio.total_value_inr * risk_config.max_total_equity_exposure_pct:
        reasons.append("total_equity_exposure_limit_exceeded")
    if market == Market.INDIA:
        if portfolio.india_exposure_inr + order_value_inr > portfolio.total_value_inr * risk_config.max_india_exposure_pct:
            reasons.append("india_exposure_limit_exceeded")
    else:
        if portfolio.us_exposure_inr + order_value_inr > portfolio.total_value_inr * risk_config.max_us_exposure_pct:
            reasons.append("us_exposure_limit_exceeded")
    if sector:
        current_sector = portfolio.exposures_by_sector.get(sector, 0)
        if current_sector + order_value_inr > portfolio.total_value_inr * risk_config.max_sector_exposure_pct:
            reasons.append("sector_exposure_limit_exceeded")
    return reasons
