from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import Field

from app.core.enums import OrderStatus
from app.schemas.common import StrictSchema
from app.schemas.order import OrderIntent


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


class BaseBroker(ABC):
    broker_name: str

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
    def place_order(self, order_intent: OrderIntent) -> BrokerOrderResult:
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
