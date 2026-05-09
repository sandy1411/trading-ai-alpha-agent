from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from typing import Any

from pydantic import Field

from app.core.enums import BrokerName, Market, OrderStatus
from app.core.errors import FailClosedError
from app.schemas.common import StrictSchema
from app.schemas.order import OrderIntent

_EXECUTION_CONTEXT_ISSUER_TOKEN = token_urlsafe(32)


def _enum_value(value: str | BrokerName | Market) -> str:
    return value.value if hasattr(value, "value") else str(value)


class BrokerOrderResult(StrictSchema):
    broker_order_id: str | None = None
    status: OrderStatus
    raw_response: dict[str, Any] = Field(default_factory=dict)


class BrokerAccount(StrictSchema):
    account_id: str
    status: str
    trading_enabled: bool
    buying_power: float = 0
    cash: float = 0
    raw_response: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class BrokerExecutionContext:
    """Short-lived order-placement permit minted only after execution guardrails pass."""

    execution_id: str
    idempotency_key: str
    risk_decision_id: str
    broker: BrokerName
    market: Market
    issued_at: datetime
    expires_at: datetime
    _issuer_token: str = field(repr=False, compare=False)

    def validate_for(self, order_intent: OrderIntent, broker_name: str | BrokerName) -> None:
        if self._issuer_token != _EXECUTION_CONTEXT_ISSUER_TOKEN:
            raise FailClosedError("invalid_broker_execution_context")
        if datetime.now(UTC) > self.expires_at:
            raise FailClosedError("broker_execution_context_expired")
        if self.idempotency_key != order_intent.idempotency_key:
            raise FailClosedError("broker_execution_context_idempotency_mismatch")
        if self.risk_decision_id != order_intent.risk_decision_id:
            raise FailClosedError("broker_execution_context_risk_decision_mismatch")
        if _enum_value(self.broker) != _enum_value(order_intent.broker):
            raise FailClosedError("broker_execution_context_broker_mismatch")
        if _enum_value(self.broker) != _enum_value(broker_name):
            raise FailClosedError("broker_execution_context_adapter_mismatch")
        if _enum_value(self.market) != _enum_value(order_intent.market):
            raise FailClosedError("broker_execution_context_market_mismatch")


def _issue_broker_execution_context(
    order_intent: OrderIntent,
    *,
    ttl_seconds: int = 30,
) -> BrokerExecutionContext:
    if not order_intent.risk_decision_id:
        raise FailClosedError("broker_execution_context_requires_risk_decision")
    now = datetime.now(UTC)
    return BrokerExecutionContext(
        execution_id=token_urlsafe(18),
        idempotency_key=order_intent.idempotency_key,
        risk_decision_id=order_intent.risk_decision_id,
        broker=order_intent.broker,
        market=order_intent.market,
        issued_at=now,
        expires_at=now + timedelta(seconds=ttl_seconds),
        _issuer_token=_EXECUTION_CONTEXT_ISSUER_TOKEN,
    )


class BaseBroker(ABC):
    broker_name: str

    def _validate_execution_context(
        self,
        order_intent: OrderIntent,
        execution_context: BrokerExecutionContext | None,
    ) -> None:
        if execution_context is None:
            raise FailClosedError("broker_execution_context_required")
        execution_context.validate_for(order_intent, self.broker_name)

    @abstractmethod
    def validate_credentials(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def check_session(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_account(self) -> BrokerAccount:
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_orders(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_order(self, order_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def place_order(
        self,
        order_intent: OrderIntent,
        *,
        execution_context: BrokerExecutionContext | None = None,
    ) -> BrokerOrderResult:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_id: str) -> BrokerOrderResult:
        raise NotImplementedError

    @abstractmethod
    def reconcile_positions(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def reconcile_order(self, order_id: str) -> BrokerOrderResult:
        raise NotImplementedError
