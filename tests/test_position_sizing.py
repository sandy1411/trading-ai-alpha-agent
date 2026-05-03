from __future__ import annotations

from app.core.enums import BrokerName, Market, MarketCalendarState, ProviderType
from app.risk.risk_engine import RiskEngine
from app.schemas.risk import MarketCalendarStatus


def test_position_size_is_capped_by_risk(
    candidate,
    portfolio,
    broker_health,
    provider_health,
    open_india_calendar,
    approved_compliance,
    live_state,
    settings,
) -> None:
    decision = RiskEngine(settings).evaluate(
        candidate,
        portfolio,
        broker_health,
        provider_health,
        open_india_calendar,
        compliance_status=approved_compliance,
        system_state=live_state,
    )

    assert decision.rejection_reasons == []
    assert decision.approved_quantity == 500
    assert decision.risk_metrics["quantity_by_risk"] == 500


def test_us_position_size_converts_usd_prices_to_inr(
    candidate,
    portfolio,
    broker_health,
    provider_health,
    fresh_fx,
    live_state,
    settings,
) -> None:
    candidate.market = Market.US
    candidate.symbol = "AAPL"
    candidate.entry_price = 100
    candidate.stop_loss = 90
    broker_health.market = Market.US
    broker_health.broker_name = BrokerName.ALPACA.value
    provider_health.market = Market.US
    provider_health.provider_type = ProviderType.BROKER_DATA

    decision = RiskEngine(settings).evaluate(
        candidate,
        portfolio,
        broker_health,
        provider_health,
        MarketCalendarStatus(market=Market.US, state=MarketCalendarState.OPEN),
        fx_status=fresh_fx,
        system_state=live_state,
    )

    assert decision.rejection_reasons == []
    assert decision.approved_quantity == 6
    assert decision.risk_metrics["entry_price_inr"] == 8300
    assert decision.risk_metrics["quantity_by_risk"] == 6
