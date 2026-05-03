from __future__ import annotations

from app.brokers.base import BaseBroker, BrokerOrderResult
from app.core.enums import OrderStatus


class OrderReconciler:
    def reconcile(self, broker: BaseBroker, broker_order_id: str | None) -> BrokerOrderResult:
        if not broker_order_id:
            return BrokerOrderResult(status=OrderStatus.UNKNOWN_REQUIRES_RECONCILIATION)
        return broker.reconcile_order(broker_order_id)
