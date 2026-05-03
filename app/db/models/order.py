from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import BrokerName, Market, OrderSide, OrderStatus, OrderType, ReconciliationState
from app.db.base import Base, JSONBType, TimestampMixin


class Order(Base, TimestampMixin):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_orders_idempotency_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    broker_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    market: Mapped[Market] = mapped_column(SAEnum(Market, name="order_market"))
    broker: Mapped[BrokerName] = mapped_column(SAEnum(BrokerName, name="broker_name"))
    symbol: Mapped[str] = mapped_column(String(64), index=True)
    side: Mapped[OrderSide] = mapped_column(SAEnum(OrderSide, name="order_side"))
    quantity: Mapped[int] = mapped_column(default=0)
    order_type: Mapped[OrderType] = mapped_column(SAEnum(OrderType, name="order_type"))
    limit_price: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    strategy_id: Mapped[str | None] = mapped_column(ForeignKey("strategies.id"), nullable=True)
    signal_id: Mapped[str | None] = mapped_column(ForeignKey("agent_signals.id"), nullable=True)
    risk_decision_id: Mapped[str] = mapped_column(ForeignKey("risk_decisions.id"))
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, name="order_status"), default=OrderStatus.CREATED, index=True
    )
    reconciliation_state: Mapped[ReconciliationState] = mapped_column(
        SAEnum(ReconciliationState, name="reconciliation_state"),
        default=ReconciliationState.REQUIRED,
    )
    broker_response: Mapped[dict] = mapped_column(JSONBType, default=dict)
    final_reconciliation: Mapped[dict] = mapped_column(JSONBType, default=dict)


class OrderIdempotencyRecord(Base, TimestampMixin):
    __tablename__ = "order_idempotency_keys"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_order_idempotency_keys_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    order_record_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, name="idempotency_order_status"),
        default=OrderStatus.CREATED,
        index=True,
    )
    reconciliation_state: Mapped[ReconciliationState] = mapped_column(
        SAEnum(ReconciliationState, name="idempotency_reconciliation_state"),
        default=ReconciliationState.REQUIRED,
    )
    blocks_duplicates: Mapped[bool] = mapped_column(Boolean, default=True)
    payload: Mapped[dict] = mapped_column(JSONBType, default=dict)
