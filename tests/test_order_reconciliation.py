from __future__ import annotations

from app.core.enums import OrderStatus, ReconciliationState
from app.execution.idempotency import InMemoryOrderIdempotencyStore
from app.execution.order_manager import ExecutionAgent
from tests.conftest import approved_risk_decision, order_intent
from tests.test_order_idempotency import BrokerStub


def test_unknown_broker_order_status_blocks_duplicate_placement(
    broker_health,
    approved_compliance,
    live_state,
    settings,
) -> None:
    broker = BrokerStub(reconcile_status=OrderStatus.UNKNOWN_REQUIRES_RECONCILIATION)
    agent = ExecutionAgent(settings=settings, idempotency_store=InMemoryOrderIdempotencyStore())

    first = agent.execute(
        order_intent(),
        approved_risk_decision(),
        broker,
        broker_health,
        approved_compliance,
        live_state,
    )
    second = agent.execute(
        order_intent(),
        approved_risk_decision(),
        broker,
        broker_health,
        approved_compliance,
        live_state,
    )

    assert first.status == OrderStatus.UNKNOWN_REQUIRES_RECONCILIATION
    assert first.reconciliation_state == ReconciliationState.BLOCKING_DUPLICATES
    assert second.id == first.id
    assert broker.place_count == 1
