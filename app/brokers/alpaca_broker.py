from __future__ import annotations

from typing import Any

import httpx

from app.brokers.base import BaseBroker, BrokerAccount, BrokerExecutionContext, BrokerOrderResult
from app.core.config import Settings, get_settings
from app.core.enums import BrokerName, Market, OrderSide, OrderStatus, OrderType
from app.core.errors import FailClosedError, MissingCredentialsError
from app.schemas.order import OrderIntent


class AlpacaBroker(BaseBroker):
    broker_name = BrokerName.ALPACA.value

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = client or httpx.Client(timeout=3)

    def _require_credentials(self) -> None:
        if not (self.settings.alpaca_api_key and self.settings.alpaca_secret_key):
            raise MissingCredentialsError("alpaca_credentials_missing")

    def _headers(self) -> dict[str, str]:
        self._require_credentials()
        return {
            "APCA-API-KEY-ID": self.settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": self.settings.alpaca_secret_key,
        }

    def validate_credentials(self) -> bool:
        self._require_credentials()
        return True

    def check_session(self) -> bool:
        account = self.get_account()
        return account.status.lower() == "active" and account.trading_enabled

    def get_account(self) -> BrokerAccount:
        try:
            response = self.client.get(
                f"{self.settings.alpaca_base_url}/v2/account", headers=self._headers()
            )
            if response.status_code != 200:
                raise FailClosedError("alpaca_account_unavailable")
            data = response.json()
            return BrokerAccount(
                account_id=str(data.get("id", "")),
                status=str(data.get("status", "UNKNOWN")),
                trading_enabled=bool(data.get("trading_blocked") is False),
                buying_power=float(data.get("buying_power") or 0),
                cash=float(data.get("cash") or 0),
                raw_response=data,
            )
        except httpx.HTTPError as exc:
            raise FailClosedError("alpaca_account_request_failed") from exc

    def get_positions(self) -> list[dict[str, Any]]:
        response = self.client.get(
            f"{self.settings.alpaca_base_url}/v2/positions", headers=self._headers()
        )
        if response.status_code != 200:
            raise FailClosedError("alpaca_positions_unavailable")
        return list(response.json())

    def get_orders(self) -> list[dict[str, Any]]:
        response = self.client.get(
            f"{self.settings.alpaca_base_url}/v2/orders", headers=self._headers()
        )
        if response.status_code != 200:
            raise FailClosedError("alpaca_orders_unavailable")
        return list(response.json())

    def get_order(self, order_id: str) -> dict[str, Any]:
        response = self.client.get(
            f"{self.settings.alpaca_base_url}/v2/orders/{order_id}", headers=self._headers()
        )
        if response.status_code != 200:
            raise FailClosedError("alpaca_order_unavailable")
        return dict(response.json())

    def place_order(
        self,
        order_intent: OrderIntent,
        *,
        execution_context: BrokerExecutionContext | None = None,
    ) -> BrokerOrderResult:
        self._validate_execution_context(order_intent, execution_context)
        if order_intent.broker != BrokerName.ALPACA:
            raise FailClosedError("order_intent_broker_mismatch")
        if order_intent.market != Market.US:
            raise FailClosedError("alpaca_market_not_supported")
        if order_intent.order_type not in {OrderType.MARKET, OrderType.LIMIT}:
            raise FailClosedError("alpaca_order_type_not_supported")

        payload: dict[str, Any] = {
            "symbol": order_intent.symbol,
            "qty": str(order_intent.quantity),
            "side": "buy" if order_intent.side == OrderSide.BUY else "sell",
            "type": order_intent.order_type.value.lower(),
            "time_in_force": "day",
            "client_order_id": order_intent.idempotency_key[:48],
        }
        if order_intent.limit_price is not None:
            payload["limit_price"] = str(order_intent.limit_price)

        response = self.client.post(
            f"{self.settings.alpaca_base_url}/v2/orders", headers=self._headers(), json=payload
        )
        raw = response.json() if response.content else {}
        if response.status_code >= 400:
            return BrokerOrderResult(status=OrderStatus.REJECTED, raw_response=raw)
        broker_order_id = str(raw.get("id", "")) or None
        if not broker_order_id:
            return BrokerOrderResult(
                status=OrderStatus.UNKNOWN_REQUIRES_RECONCILIATION, raw_response=raw
            )
        return BrokerOrderResult(
            broker_order_id=broker_order_id,
            status=OrderStatus.SUBMITTED,
            raw_response=raw,
        )

    def cancel_order(self, order_id: str) -> BrokerOrderResult:
        response = self.client.delete(
            f"{self.settings.alpaca_base_url}/v2/orders/{order_id}", headers=self._headers()
        )
        raw = response.json() if response.content else {}
        if response.status_code not in {200, 204}:
            return BrokerOrderResult(
                broker_order_id=order_id,
                status=OrderStatus.UNKNOWN_REQUIRES_RECONCILIATION,
                raw_response=raw,
            )
        return BrokerOrderResult(broker_order_id=order_id, status=OrderStatus.CANCELLED, raw_response=raw)

    def reconcile_positions(self) -> bool:
        self.get_positions()
        return True

    def reconcile_order(self, order_id: str) -> BrokerOrderResult:
        raw = self.get_order(order_id)
        status_text = str(raw.get("status", "")).lower()
        status_map = {
            "accepted": OrderStatus.ACCEPTED,
            "new": OrderStatus.ACCEPTED,
            "partially_filled": OrderStatus.PARTIALLY_FILLED,
            "filled": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "cancelled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
        }
        return BrokerOrderResult(
            broker_order_id=order_id,
            status=status_map.get(status_text, OrderStatus.UNKNOWN_REQUIRES_RECONCILIATION),
            raw_response=raw,
        )
