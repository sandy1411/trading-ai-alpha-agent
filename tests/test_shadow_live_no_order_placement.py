from __future__ import annotations

import pytest

from app.core.enums import Market
from app.core.errors import RiskRejectedError
from app.execution.order_manager import ExecutionAgent
from tests.conftest import approved_risk_decision, order_intent
from tests.test_order_idempotency import BrokerStub


def test_shadow_live_mode_cannot_place_orders(
    broker_health,
    approved_compliance,
    shadow_state,
    settings,
) -> None:
    agent = ExecutionAgent(settings=settings)

    with pytest.raises(RiskRejectedError, match="trading_mode_not_live_capable"):
        agent.execute(
            order_intent(),
            approved_risk_decision(),
            BrokerStub(),
            broker_health,
            approved_compliance,
            shadow_state,
        )


def test_execution_rejects_broker_market_mismatch(
    broker_health,
    approved_compliance,
    live_state,
    settings,
) -> None:
    agent = ExecutionAgent(settings=settings)
    intent = order_intent().model_copy(update={"market": Market.US})

    with pytest.raises(RiskRejectedError, match="broker_market_mismatch"):
        agent.execute(
            intent,
            approved_risk_decision(),
            BrokerStub(),
            broker_health,
            approved_compliance,
            live_state,
        )
