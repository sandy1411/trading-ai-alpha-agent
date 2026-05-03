from __future__ import annotations

from app.core.enums import TradingMode
from app.risk.kill_switch import SystemStateSnapshot
from app.risk.risk_engine import RiskEngine


def test_kill_switch_blocks_live_trade(
    candidate,
    portfolio,
    broker_health,
    provider_health,
    open_india_calendar,
    approved_compliance,
    settings,
) -> None:
    state = SystemStateSnapshot(
        trading_mode=TradingMode.MICRO_LIVE_AUTONOMOUS,
        live_trading_enabled=True,
        kill_switch=True,
    )

    decision = RiskEngine(settings).evaluate(
        candidate=candidate,
        portfolio=portfolio,
        broker_health=broker_health,
        provider_health=provider_health,
        market_calendar=open_india_calendar,
        compliance_status=approved_compliance,
        system_state=state,
    )

    assert decision.decision == "REJECTED"
    assert "kill_switch_enabled" in decision.rejection_reasons
