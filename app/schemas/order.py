from __future__ import annotations

from pydantic import Field

from app.core.enums import BrokerName, Market, OrderSide, OrderStatus, OrderType, ReconciliationState
from app.schemas.common import StrictSchema, new_id


class OrderIntent(StrictSchema):
    market: Market
    broker: BrokerName
    symbol: str
    side: OrderSide
    quantity: int = Field(gt=0)
    order_type: OrderType
    limit_price: float | None = Field(default=None, gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    strategy_id: str | None = None
    signal_id: str | None = None
    risk_decision_id: str | None = None
    idempotency_key: str


class OrderRecord(StrictSchema):
    id: str = Field(default_factory=new_id)
    intent: OrderIntent
    status: OrderStatus = OrderStatus.CREATED
    reconciliation_state: ReconciliationState = ReconciliationState.REQUIRED
    broker_order_id: str | None = None
    broker_response: dict = Field(default_factory=dict)
    final_reconciliation: dict = Field(default_factory=dict)
