from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.brokers.base import BaseBroker, BrokerAccount, BrokerOrderResult
from app.core.enums import OrderStatus
from app.db.base import Base
from app.execution.idempotency import InMemoryOrderIdempotencyStore, OrderIdempotencyStore
from app.execution.order_manager import ExecutionAgent
from app.schemas.order import OrderRecord
from tests.conftest import approved_risk_decision, order_intent


class BrokerStub(BaseBroker):
    broker_name = "ZERODHA"

    def __init__(self, reconcile_status: OrderStatus = OrderStatus.FILLED) -> None:
        self.place_count = 0
        self.reconcile_status = reconcile_status

    def validate_credentials(self) -> bool:
        return True

    def check_session(self) -> bool:
        return True

    def get_account(self) -> BrokerAccount:
        return BrokerAccount(account_id="acct", status="ACTIVE", trading_enabled=True)

    def get_positions(self) -> list[dict[str, Any]]:
        return []

    def get_orders(self) -> list[dict[str, Any]]:
        return []

    def get_order(self, order_id: str) -> dict[str, Any]:
        return {"id": order_id}

    def place_order(self, order_intent):
        self.place_count += 1
        return BrokerOrderResult(
            broker_order_id="broker-order-1",
            status=OrderStatus.SUBMITTED,
            raw_response={"id": "broker-order-1"},
        )

    def cancel_order(self, order_id: str) -> BrokerOrderResult:
        return BrokerOrderResult(broker_order_id=order_id, status=OrderStatus.CANCELLED)

    def reconcile_positions(self) -> bool:
        return True

    def reconcile_order(self, order_id: str) -> BrokerOrderResult:
        return BrokerOrderResult(
            broker_order_id=order_id,
            status=self.reconcile_status,
            raw_response={"id": order_id, "status": self.reconcile_status.value},
        )


def test_idempotency_prevents_duplicate_order(
    broker_health,
    approved_compliance,
    live_state,
    settings,
) -> None:
    broker = BrokerStub()
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

    assert first.id == second.id
    assert broker.place_count == 1


def test_durable_idempotency_store_persists_reserved_key() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    store = OrderIdempotencyStore(session_factory=session_factory)
    intent = order_intent().model_copy(update={"idempotency_key": "durable-idem-1"})
    record = OrderRecord(intent=intent)

    store.reserve(record.intent.idempotency_key, record)
    reloaded = store.get(record.intent.idempotency_key)

    assert reloaded is not None
    assert reloaded.id == record.id
    assert reloaded.intent.idempotency_key == "durable-idem-1"
