from __future__ import annotations

from math import floor

from app.core.enums import AssetClass, Market, TradeAction
from app.schemas.portfolio import PortfolioSnapshot
from app.schemas.risk import RiskConfig
from app.schemas.signal import TradeCandidate


def calculate_quantity_by_risk(
    portfolio_value_inr: float,
    entry_price: float,
    stop_loss: float,
    max_risk_per_trade_pct: float,
) -> int:
    per_unit_risk = abs(entry_price - stop_loss)
    if per_unit_risk <= 0:
        return 0
    risk_amount = portfolio_value_inr * max_risk_per_trade_pct
    return max(floor(risk_amount / per_unit_risk), 0)


def cap_quantity(
    candidate: TradeCandidate,
    portfolio: PortfolioSnapshot,
    risk_config: RiskConfig,
    quantity_by_risk: int,
    entry_price_inr: float | None = None,
) -> tuple[int, dict[str, float | int]]:
    price_inr = entry_price_inr or candidate.entry_price
    max_position_pct = (
        risk_config.max_single_etf_position_pct
        if candidate.asset_class == AssetClass.ETF
        else risk_config.max_single_stock_position_pct
    )
    max_position_value = portfolio.total_value_inr * max_position_pct
    quantity_by_position_cap = floor(max_position_value / price_inr)
    quantity_by_cash = (
        floor(portfolio.cash_inr / price_inr)
        if candidate.action == TradeAction.BUY
        else quantity_by_risk
    )
    if candidate.market == Market.INDIA:
        available_market_exposure = max(
            portfolio.total_value_inr * risk_config.max_india_exposure_pct
            - portfolio.india_exposure_inr,
            0,
        )
    else:
        available_market_exposure = max(
            portfolio.total_value_inr * risk_config.max_us_exposure_pct - portfolio.us_exposure_inr,
            0,
        )
    quantity_by_market_exposure = floor(available_market_exposure / price_inr)

    capped = min(
        quantity_by_risk,
        quantity_by_position_cap,
        quantity_by_cash,
        quantity_by_market_exposure,
    )
    return max(capped, 0), {
        "quantity_by_risk": quantity_by_risk,
        "quantity_by_position_cap": quantity_by_position_cap,
        "quantity_by_cash": quantity_by_cash,
        "quantity_by_market_exposure": quantity_by_market_exposure,
        "entry_price_inr": price_inr,
    }
