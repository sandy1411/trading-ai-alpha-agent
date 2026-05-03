from __future__ import annotations

from fastapi import APIRouter

from app.db.models.order import Order
from app.db.session import SessionLocal

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("")
def list_orders() -> list[dict]:
    with SessionLocal() as session:
        orders = session.query(Order).order_by(Order.created_at.desc()).limit(100).all()
        return [
            {
                "id": order.id,
                "created_at": order.created_at.isoformat(),
                "broker_order_id": order.broker_order_id,
                "idempotency_key": order.idempotency_key,
                "market": order.market.value,
                "broker": order.broker.value,
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": order.quantity,
                "order_type": order.order_type.value,
                "status": order.status.value,
                "reconciliation_state": order.reconciliation_state.value,
            }
            for order in orders
        ]


@router.post("/reconcile")
def reconcile_orders() -> dict:
    return {"status": "manual_reconciliation_endpoint_ready", "orders_reconciled": 0}
