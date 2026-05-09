from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import OrderIdempotencyError
from app.db.models.order import Order, OrderIdempotencyRecord
from app.db.session import SessionLocal
from app.schemas.order import OrderRecord


class OrderIdempotencyStore:
    """Durable idempotency store backed by PostgreSQL in production."""

    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        self.session_factory = session_factory or SessionLocal

    def exists(self, idempotency_key: str) -> bool:
        return self.get(idempotency_key) is not None

    def get(self, idempotency_key: str) -> OrderRecord | None:
        with self.session_factory() as session:
            record = self._get_record(session, idempotency_key)
            if record is None:
                return None
            return self._payload_to_order_record(record.payload)

    def reserve(self, idempotency_key: str, record: OrderRecord) -> None:
        with self.session_factory() as session:
            try:
                with session.begin():
                    session.add(self._order_from_record(record))
                    session.add(
                        OrderIdempotencyRecord(
                            idempotency_key=idempotency_key,
                            order_record_id=record.id,
                            broker_order_id=record.broker_order_id,
                            status=record.status,
                            reconciliation_state=record.reconciliation_state,
                            blocks_duplicates=True,
                            payload=record.model_dump(mode="json"),
                        )
                    )
            except IntegrityError as exc:
                session.rollback()
                raise OrderIdempotencyError("order_idempotency_key_already_exists") from exc

    def upsert(self, idempotency_key: str, record: OrderRecord) -> None:
        with self.session_factory() as session:
            try:
                with session.begin():
                    db_order = session.get(Order, record.id)
                    if db_order is None:
                        db_order = self._order_from_record(record)
                        session.add(db_order)
                    else:
                        self._apply_order_record(db_order, record)

                    db_record = self._get_record(session, idempotency_key)
                    if db_record is None:
                        db_record = OrderIdempotencyRecord(idempotency_key=idempotency_key)
                        session.add(db_record)
                    db_record.order_record_id = record.id
                    db_record.broker_order_id = record.broker_order_id
                    db_record.status = record.status
                    db_record.reconciliation_state = record.reconciliation_state
                    db_record.blocks_duplicates = True
                    db_record.payload = record.model_dump(mode="json")
            except IntegrityError as exc:
                session.rollback()
                raise OrderIdempotencyError("order_idempotency_key_already_exists") from exc

    @staticmethod
    def _get_record(session: Session, idempotency_key: str) -> OrderIdempotencyRecord | None:
        return session.scalar(
            select(OrderIdempotencyRecord).where(
                OrderIdempotencyRecord.idempotency_key == idempotency_key
            )
        )

    @staticmethod
    def _payload_to_order_record(payload: dict) -> OrderRecord | None:
        if not payload:
            return None
        return OrderRecord.model_validate(payload)

    @staticmethod
    def _order_from_record(record: OrderRecord) -> Order:
        order = Order(
            id=record.id,
            idempotency_key=record.intent.idempotency_key,
            market=record.intent.market,
            broker=record.intent.broker,
            symbol=record.intent.symbol,
            side=record.intent.side,
            quantity=record.intent.quantity,
            order_type=record.intent.order_type,
            limit_price=record.intent.limit_price,
            stop_loss=record.intent.stop_loss,
            strategy_id=record.intent.strategy_id,
            signal_id=record.intent.signal_id,
            risk_decision_id=record.intent.risk_decision_id,
        )
        OrderIdempotencyStore._apply_order_record(order, record)
        return order

    @staticmethod
    def _apply_order_record(order: Order, record: OrderRecord) -> None:
        order.broker_order_id = record.broker_order_id
        order.status = record.status
        order.reconciliation_state = record.reconciliation_state
        order.broker_response = record.broker_response
        order.final_reconciliation = record.final_reconciliation


class InMemoryOrderIdempotencyStore:
    """Small test helper; production execution uses OrderIdempotencyStore."""

    def __init__(self) -> None:
        self._records: dict[str, OrderRecord] = {}

    def exists(self, idempotency_key: str) -> bool:
        return idempotency_key in self._records

    def get(self, idempotency_key: str) -> OrderRecord | None:
        return self._records.get(idempotency_key)

    def reserve(self, idempotency_key: str, record: OrderRecord) -> None:
        if idempotency_key in self._records:
            raise OrderIdempotencyError("order_idempotency_key_already_exists")
        self._records[idempotency_key] = record

    def upsert(self, idempotency_key: str, record: OrderRecord) -> None:
        self._records[idempotency_key] = record
