from __future__ import annotations

from datetime import timedelta

from app.core.enums import (
    AccountStatus,
    AuthStatus,
    ComplianceApprovalStatus,
    FreshnessStatus,
    Market,
    MarketCalendarState,
    ProviderStatus,
    ProviderType,
    TradeAction,
    TradingMode,
)
from app.core.time_utils import utc_now
from app.risk.risk_engine import RiskEngine
from app.schemas.fx import FXRateStatus
from app.schemas.provider import ProviderHealth
from app.schemas.risk import ComplianceStatus, MarketCalendarStatus


def test_missing_stop_loss_is_rejected(
    candidate,
    portfolio,
    broker_health,
    provider_health,
    open_india_calendar,
    approved_compliance,
    live_state,
    settings,
) -> None:
    candidate.stop_loss = None

    decision = RiskEngine(settings).evaluate(
        candidate,
        portfolio,
        broker_health,
        provider_health,
        open_india_calendar,
        compliance_status=approved_compliance,
        system_state=live_state,
    )

    assert "stop_loss_required" in decision.rejection_reasons


def test_stale_fx_blocks_us_trade(
    candidate,
    portfolio,
    broker_health,
    provider_health,
    live_state,
    settings,
) -> None:
    candidate.market = Market.US
    broker_health.market = Market.US
    broker_health.broker_name = "ALPACA"
    provider_health.market = Market.US
    provider_health.provider_type = ProviderType.BROKER_DATA
    stale_fx = FXRateStatus(
        rate=83.0,
        freshness_status=FreshnessStatus.STALE,
        last_success_at=utc_now() - timedelta(hours=2),
        source="test",
    )

    decision = RiskEngine(settings).evaluate(
        candidate,
        portfolio,
        broker_health,
        provider_health,
        MarketCalendarStatus(market=Market.US, state=MarketCalendarState.OPEN),
        fx_status=stale_fx,
        system_state=live_state,
    )

    assert "usd_inr_fx_stale" in decision.rejection_reasons


def test_expired_zerodha_session_blocks_india_live_trade(
    candidate,
    portfolio,
    broker_health,
    provider_health,
    open_india_calendar,
    approved_compliance,
    live_state,
    settings,
) -> None:
    broker_health.auth_status = AuthStatus.EXPIRED

    decision = RiskEngine(settings).evaluate(
        candidate,
        portfolio,
        broker_health,
        provider_health,
        open_india_calendar,
        compliance_status=approved_compliance,
        system_state=live_state,
    )

    assert "broker_session_invalid" in decision.rejection_reasons


def test_market_closed_blocks_live_order(
    candidate,
    portfolio,
    broker_health,
    provider_health,
    approved_compliance,
    live_state,
    settings,
) -> None:
    closed = MarketCalendarStatus(market=Market.INDIA, state=MarketCalendarState.CLOSED)

    decision = RiskEngine(settings).evaluate(
        candidate,
        portfolio,
        broker_health,
        provider_health,
        closed,
        compliance_status=approved_compliance,
        system_state=live_state,
    )

    assert "market_closed" in decision.rejection_reasons


def test_missing_broker_credentials_block_live_trading(
    candidate,
    portfolio,
    broker_health,
    provider_health,
    open_india_calendar,
    approved_compliance,
    live_state,
    settings,
) -> None:
    broker_health.auth_status = AuthStatus.MISSING_CREDENTIALS

    decision = RiskEngine(settings).evaluate(
        candidate,
        portfolio,
        broker_health,
        provider_health,
        open_india_calendar,
        compliance_status=approved_compliance,
        system_state=live_state,
    )

    assert "broker_credentials_missing" in decision.rejection_reasons


def test_missing_market_data_provider_blocks_live_trading(
    candidate,
    portfolio,
    broker_health,
    open_india_calendar,
    approved_compliance,
    live_state,
    settings,
) -> None:
    decision = RiskEngine(settings).evaluate(
        candidate,
        portfolio,
        broker_health,
        None,
        open_india_calendar,
        compliance_status=approved_compliance,
        system_state=live_state,
    )

    assert "market_data_provider_missing" in decision.rejection_reasons


def test_market_mismatch_health_inputs_block_live_trading(
    candidate,
    portfolio,
    broker_health,
    provider_health,
    live_state,
    fresh_fx,
    settings,
) -> None:
    candidate.market = Market.US

    decision = RiskEngine(settings).evaluate(
        candidate,
        portfolio,
        broker_health,
        provider_health,
        MarketCalendarStatus(market=Market.INDIA, state=MarketCalendarState.OPEN),
        fx_status=fresh_fx,
        system_state=live_state,
    )

    assert "broker_market_mismatch" in decision.rejection_reasons
    assert "provider_market_mismatch:ZERODHA_KITE" in decision.rejection_reasons
    assert "market_calendar_market_mismatch" in decision.rejection_reasons


def test_india_live_order_blocked_if_compliance_not_approved(
    candidate,
    portfolio,
    broker_health,
    provider_health,
    open_india_calendar,
    live_state,
    settings,
) -> None:
    compliance = ComplianceStatus(
        market=Market.INDIA,
        broker="ZERODHA",
        strategy_registration_status=ComplianceApprovalStatus.NOT_APPROVED,
        broker_approval_status=ComplianceApprovalStatus.NOT_APPROVED,
        can_place_live_orders=False,
    )

    decision = RiskEngine(settings).evaluate(
        candidate,
        portfolio,
        broker_health,
        provider_health,
        open_india_calendar,
        compliance_status=compliance,
        system_state=live_state,
    )

    assert "india_compliance_not_approved" in decision.rejection_reasons


def test_unhealthy_provider_blocks_live_trading(
    candidate,
    portfolio,
    broker_health,
    open_india_calendar,
    approved_compliance,
    live_state,
    settings,
) -> None:
    provider = ProviderHealth(
        provider_name="ZERODHA_KITE",
        provider_type=ProviderType.BROKER_DATA,
        market=Market.INDIA,
        status=ProviderStatus.DOWN,
        freshness_status=FreshnessStatus.MISSING,
    )

    decision = RiskEngine(settings).evaluate(
        candidate,
        portfolio,
        broker_health,
        provider,
        open_india_calendar,
        compliance_status=approved_compliance,
        system_state=live_state,
    )

    assert "provider_unhealthy:ZERODHA_KITE" in decision.rejection_reasons


def test_broker_account_status_blocks_live_trading(
    candidate,
    portfolio,
    broker_health,
    provider_health,
    open_india_calendar,
    approved_compliance,
    live_state,
    settings,
) -> None:
    broker_health.account_status = AccountStatus.BLOCKED

    decision = RiskEngine(settings).evaluate(
        candidate,
        portfolio,
        broker_health,
        provider_health,
        open_india_calendar,
        compliance_status=approved_compliance,
        system_state=live_state,
    )

    assert "broker_account_not_active" in decision.rejection_reasons


def test_no_trade_is_valid_decision(candidate, portfolio, settings) -> None:
    candidate.action = TradeAction.NO_TRADE

    decision = RiskEngine(settings).evaluate(candidate, portfolio, None, None, None)

    assert decision.decision == "NO_TRADE"


def test_live_autonomous_missing_quote_metrics_fails_closed(
    candidate,
    portfolio,
    broker_health,
    provider_health,
    open_india_calendar,
    approved_compliance,
    live_state,
    settings,
) -> None:
    live_state.trading_mode = TradingMode.LIVE_AUTONOMOUS

    decision = RiskEngine(settings).evaluate(
        candidate,
        portfolio,
        broker_health,
        provider_health,
        open_india_calendar,
        compliance_status=approved_compliance,
        system_state=live_state,
    )

    assert "liquidity_metrics_missing" in decision.rejection_reasons
    assert "slippage_metrics_missing" in decision.rejection_reasons


def test_bad_liquidity_and_wide_spread_reject_trade(
    candidate,
    portfolio,
    broker_health,
    provider_health,
    open_india_calendar,
    approved_compliance,
    live_state,
    settings,
) -> None:
    quote_metrics = {
        "bid": 99.0,
        "ask": 101.0,
        "volume": 10_000,
        "average_daily_volume": 50_000,
        "average_daily_notional_inr": 5_000_000,
    }

    decision = RiskEngine(settings).evaluate(
        candidate,
        portfolio,
        broker_health,
        provider_health,
        open_india_calendar,
        compliance_status=approved_compliance,
        system_state=live_state,
        quote_metrics=quote_metrics,
    )

    assert "intraday_volume_too_low" in decision.rejection_reasons
    assert "bid_ask_spread_too_wide" in decision.rejection_reasons


def test_good_live_autonomous_quote_metrics_allow_risk_sizing(
    candidate,
    portfolio,
    broker_health,
    provider_health,
    open_india_calendar,
    approved_compliance,
    live_state,
    settings,
) -> None:
    live_state.trading_mode = TradingMode.LIVE_AUTONOMOUS
    quote_metrics = {
        "bid": 99.95,
        "ask": 100.0,
        "volume": 200_000,
        "average_daily_volume": 1_000_000,
        "average_daily_notional_inr": 100_000_000,
        "estimated_slippage_pct": 0.0005,
    }

    decision = RiskEngine(settings).evaluate(
        candidate,
        portfolio,
        broker_health,
        provider_health,
        open_india_calendar,
        compliance_status=approved_compliance,
        system_state=live_state,
        quote_metrics=quote_metrics,
    )

    assert decision.rejection_reasons == []
    assert decision.approved_quantity == 500
