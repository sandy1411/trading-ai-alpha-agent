from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.enums import OrderStatus, ReconciliationState
from app.db.base import Base
from app.db.models.order import Order, OrderIdempotencyRecord
from app.execution.idempotency import InMemoryOrderIdempotencyStore, OrderIdempotencyStore
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


def test_execution_agent_persists_order_and_unknown_reconciliation_state(
    broker_health,
    approved_compliance,
    live_state,
    settings,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    broker = BrokerStub(reconcile_status=OrderStatus.UNKNOWN_REQUIRES_RECONCILIATION)
    agent = ExecutionAgent(
        settings=settings,
        idempotency_store=OrderIdempotencyStore(session_factory=session_factory),
    )

    first = agent.execute(
        order_intent().model_copy(update={"idempotency_key": "durable-unknown-1"}),
        approved_risk_decision(),
        broker,
        broker_health,
        approved_compliance,
        live_state,
    )
    second = agent.execute(
        order_intent().model_copy(update={"idempotency_key": "durable-unknown-1"}),
        approved_risk_decision(),
        broker,
        broker_health,
        approved_compliance,
        live_state,
    )

    with session_factory() as session:
        order_row = session.scalar(select(Order).where(Order.id == first.id))
        idempotency_row = session.scalar(
            select(OrderIdempotencyRecord).where(
                OrderIdempotencyRecord.idempotency_key == "durable-unknown-1"
            )
        )

    assert second.id == first.id
    assert broker.place_count == 1
    assert order_row is not None
    assert order_row.status == OrderStatus.UNKNOWN_REQUIRES_RECONCILIATION
    assert order_row.reconciliation_state == ReconciliationState.BLOCKING_DUPLICATES
    assert idempotency_row is not None
    assert idempotency_row.blocks_duplicates is True
