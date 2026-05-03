from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.config import Settings
from app.core.enums import (
    AccountStatus,
    AssetClass,
    AuthStatus,
    BrokerName,
    ComplianceApprovalStatus,
    FreshnessStatus,
    Market,
    MarketCalendarState,
    OrderSide,
    OrderType,
    ProviderStatus,
    ProviderType,
    RiskDecisionType,
    TradeAction,
    TradingMode,
)
from app.core.time_utils import utc_now
from app.risk.kill_switch import SystemStateSnapshot
from app.schemas.broker import BrokerHealth
from app.schemas.fx import FXRateStatus
from app.schemas.order import OrderIntent
from app.schemas.portfolio import PortfolioSnapshot
from app.schemas.provider import ProviderHealth
from app.schemas.risk import ComplianceStatus, MarketCalendarStatus, RiskDecision
from app.schemas.signal import TradeCandidate


@pytest.fixture()
def settings() -> Settings:
    return Settings(_env_file=None)


@pytest.fixture()
def live_state() -> SystemStateSnapshot:
    return SystemStateSnapshot(
        trading_mode=TradingMode.MICRO_LIVE_AUTONOMOUS,
        live_trading_enabled=True,
        kill_switch=False,
    )


@pytest.fixture()
def shadow_state() -> SystemStateSnapshot:
    return SystemStateSnapshot(
        trading_mode=TradingMode.SHADOW_LIVE_REAL_DATA,
        live_trading_enabled=False,
        kill_switch=False,
    )


@pytest.fixture()
def broker_health() -> BrokerHealth:
    return BrokerHealth(
        broker_name=BrokerName.ZERODHA.value,
        market=Market.INDIA,
        auth_status=AuthStatus.VALID,
        account_status=AccountStatus.ACTIVE,
        trading_enabled=True,
        buying_power=1_000_000,
        cash=1_000_000,
        positions_reconciled=True,
        last_checked_at=utc_now(),
    )


@pytest.fixture()
def provider_health() -> ProviderHealth:
    return ProviderHealth(
        provider_name="ZERODHA_KITE",
        provider_type=ProviderType.BROKER_DATA,
        market=Market.INDIA,
        status=ProviderStatus.OK,
        last_success_at=utc_now(),
        freshness_status=FreshnessStatus.FRESH,
    )


@pytest.fixture()
def open_india_calendar() -> MarketCalendarStatus:
    return MarketCalendarStatus(
        market=Market.INDIA,
        state=MarketCalendarState.OPEN,
        reason="regular_session_open",
    )


@pytest.fixture()
def approved_compliance() -> ComplianceStatus:
    return ComplianceStatus(
        market=Market.INDIA,
        broker=BrokerName.ZERODHA.value,
        algo_compliance_required=True,
        algo_id="USER-LOCAL-ALGO",
        strategy_registration_status=ComplianceApprovalStatus.APPROVED,
        broker_approval_status=ComplianceApprovalStatus.APPROVED,
        exchange_algo_identifier="EXCHANGE-ALGO-ID",
        order_tag="DWALL",
        unique_order_identifier="DWALL-001",
        can_place_live_orders=True,
    )


@pytest.fixture()
def candidate() -> TradeCandidate:
    return TradeCandidate(
        market=Market.INDIA,
        symbol="RELIANCE",
        instrument_id="instrument-1",
        asset_class=AssetClass.EQUITY,
        action=TradeAction.BUY,
        strategy_name="test_strategy",
        confidence=0.7,
        entry_price=100,
        stop_loss=90,
        take_profit=125,
        expected_risk=10,
        expected_reward=25,
        reward_risk_ratio=2.5,
        reasons=["test"],
        risk_flags=[],
        data_sources=["ZERODHA_KITE"],
    )


@pytest.fixture()
def portfolio() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        total_value_inr=1_000_000,
        cash_inr=1_000_000,
        equity_exposure_inr=0,
        india_exposure_inr=0,
        us_exposure_inr=0,
        positions=[],
    )


@pytest.fixture()
def fresh_fx() -> FXRateStatus:
    return FXRateStatus(
        rate=83.0,
        freshness_status=FreshnessStatus.FRESH,
        last_success_at=utc_now(),
        source="test",
    )


def approved_risk_decision() -> RiskDecision:
    return RiskDecision(
        id="risk-1",
        signal_id="signal-1",
        decision=RiskDecisionType.APPROVED,
        approved_quantity=10,
        approved_capital=1_000,
        approved_risk=100,
    )


def order_intent(risk_decision_id: str | None = "risk-1") -> OrderIntent:
    return OrderIntent(
        market=Market.INDIA,
        broker=BrokerName.ZERODHA,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        quantity=10,
        order_type=OrderType.LIMIT,
        limit_price=100,
        stop_loss=90,
        strategy_id="strategy-1",
        signal_id="signal-1",
        risk_decision_id=risk_decision_id,
        idempotency_key="idem-1",
    )


def monday_india_open() -> datetime:
    return datetime(2026, 4, 27, 4, 0, tzinfo=UTC)
