from __future__ import annotations

from app.brokers.base import BaseBroker
from app.core.config import Settings, get_settings
from app.core.enums import Market, OrderStatus, ReconciliationState
from app.core.errors import RiskRejectedError
from app.execution.idempotency import OrderIdempotencyStore
from app.execution.reconciliation import OrderReconciler
from app.risk.kill_switch import SystemStateSnapshot
from app.schemas.broker import BrokerHealth
from app.schemas.order import OrderIntent, OrderRecord
from app.schemas.risk import ComplianceStatus, RiskDecision


class ExecutionAgent:
    def __init__(
        self,
        settings: Settings | None = None,
        idempotency_store: OrderIdempotencyStore | None = None,
        reconciler: OrderReconciler | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.idempotency_store = idempotency_store or OrderIdempotencyStore()
        self.reconciler = reconciler or OrderReconciler()

    def execute(
        self,
        intent: OrderIntent,
        risk_decision: RiskDecision,
        broker: BaseBroker,
        broker_health: BrokerHealth,
        compliance_status: ComplianceStatus | None,
        system_state: SystemStateSnapshot | None = None,
    ) -> OrderRecord:
        state = system_state or SystemStateSnapshot.from_settings(self.settings)
        self._validate_pre_trade(intent, risk_decision, broker_health, compliance_status, state)

        existing = self.idempotency_store.get(intent.idempotency_key)
        if existing is not None:
            return existing

        record = OrderRecord(intent=intent)
        self.idempotency_store.reserve(intent.idempotency_key, record)

        broker_result = broker.place_order(intent)
        record.status = broker_result.status
        record.broker_order_id = broker_result.broker_order_id
        record.broker_response = broker_result.raw_response

        reconciliation = self.reconciler.reconcile(broker, broker_result.broker_order_id)
        record.status = reconciliation.status
        record.final_reconciliation = reconciliation.raw_response
        record.reconciliation_state = (
            ReconciliationState.BLOCKING_DUPLICATES
            if reconciliation.status == OrderStatus.UNKNOWN_REQUIRES_RECONCILIATION
            else ReconciliationState.RECONCILED
        )
        self.idempotency_store.upsert(intent.idempotency_key, record)
        return record

    def _validate_pre_trade(
        self,
        intent: OrderIntent,
        risk_decision: RiskDecision,
        broker_health: BrokerHealth,
        compliance_status: ComplianceStatus | None,
        state: SystemStateSnapshot,
    ) -> None:
        if not intent.risk_decision_id:
            raise RiskRejectedError("risk_decision_id_required")
        if intent.risk_decision_id != risk_decision.id:
            raise RiskRejectedError("risk_decision_id_mismatch")
        if not risk_decision.is_approved_for_execution:
            raise RiskRejectedError("risk_decision_not_approved")
        if not state.trading_mode.is_live_capable:
            raise RiskRejectedError("trading_mode_not_live_capable")
        if not state.live_trading_enabled:
            raise RiskRejectedError("live_trading_enabled_false")
        if state.kill_switch:
            raise RiskRejectedError("kill_switch_enabled")
        if not broker_health.is_healthy_for_live:
            raise RiskRejectedError("broker_health_not_live_ready")
        if intent.market == Market.INDIA:
            if compliance_status is None or not compliance_status.approved:
                raise RiskRejectedError("india_compliance_not_approved")
        if not intent.idempotency_key:
            raise RiskRejectedError("idempotency_key_required")
