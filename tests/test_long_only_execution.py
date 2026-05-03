from __future__ import annotations

import pytest

from app.core.enums import RiskDecisionType
from app.core.errors import RiskRejectedError
from app.execution.order_manager import ExecutionAgent
from app.core.enums import TradeAction
from app.risk.risk_engine import RiskEngine
from app.schemas.risk import RiskDecision
from tests.conftest import approved_risk_decision, order_intent
from tests.test_order_idempotency import BrokerStub


def test_sell_cannot_create_short_position(
    candidate,
    portfolio,
    broker_health,
    provider_health,
    open_india_calendar,
    approved_compliance,
    live_state,
    settings,
) -> None:
    candidate.action = TradeAction.SELL
    candidate.stop_loss = 110

    decision = RiskEngine(settings).evaluate(
        candidate,
        portfolio,
        broker_health,
        provider_health,
        open_india_calendar,
        compliance_status=approved_compliance,
        system_state=live_state,
    )

    assert "sell_without_existing_long_position" in decision.rejection_reasons


def test_execution_agent_refuses_order_without_risk_decision_id(
    broker_health,
    approved_compliance,
    live_state,
    settings,
) -> None:
    agent = ExecutionAgent(settings=settings)

    with pytest.raises(RiskRejectedError, match="risk_decision_id_required"):
        agent.execute(
            order_intent(risk_decision_id=None),
            approved_risk_decision(),
            BrokerStub(),
            broker_health,
            approved_compliance,
            live_state,
        )


def test_execution_agent_refuses_rejected_risk_decision(
    broker_health,
    approved_compliance,
    live_state,
    settings,
) -> None:
    agent = ExecutionAgent(settings=settings)
    rejected = RiskDecision(
        id="risk-1",
        decision=RiskDecisionType.REJECTED,
        rejection_reasons=["test_rejection"],
    )

    with pytest.raises(RiskRejectedError, match="risk_decision_not_approved"):
        agent.execute(
            order_intent(),
            rejected,
            BrokerStub(),
            broker_health,
            approved_compliance,
            live_state,
        )
