from __future__ import annotations

from typing import Any

import httpx

from app.brokers.base import BaseBroker, BrokerAccount, BrokerOrderResult
from app.core.config import Settings, get_settings
from app.core.enums import BrokerName, OrderSide, OrderStatus, OrderType
from app.core.errors import FailClosedError, MissingCredentialsError
from app.schemas.order import OrderIntent
from app.services.zerodha_token_service import load_access_token


class ZerodhaBroker(BaseBroker):
    broker_name = BrokerName.ZERODHA.value
    base_url = "https://api.kite.trade"

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = client or httpx.Client(timeout=3)

    def _require_credentials(self) -> None:
        if not (
            self.settings.zerodha_api_key
            and self.settings.zerodha_api_secret
            and load_access_token()
        ):
            raise MissingCredentialsError("zerodha_credentials_missing")

    def _headers(self) -> dict[str, str]:
        self._require_credentials()
        access_token = load_access_token()
        return {
            "Authorization": (
                f"token {self.settings.zerodha_api_key}:{access_token}"
            ),
            "X-Kite-Version": "3",
        }

    def validate_credentials(self) -> bool:
        self._require_credentials()
        return True

    def check_session(self) -> bool:
        try:
            response = self.client.get(f"{self.base_url}/user/profile", headers=self._headers())
            return response.status_code == 200
        except httpx.HTTPError as exc:
            raise FailClosedError("zerodha_session_check_failed") from exc

    def get_account(self) -> BrokerAccount:
        try:
            profile_response = self.client.get(f"{self.base_url}/user/profile", headers=self._headers())
            if profile_response.status_code != 200:
                raise FailClosedError("zerodha_account_unavailable")
            margin_response = self.client.get(f"{self.base_url}/user/margins", headers=self._headers())
            if margin_response.status_code != 200:
                raise FailClosedError("zerodha_margins_unavailable")

            data = profile_response.json().get("data", {})
            margins = margin_response.json().get("data", {})
            equity = margins.get("equity", {}) if isinstance(margins, dict) else {}
            available = equity.get("available", {}) if isinstance(equity, dict) else {}
            exchanges = set(data.get("exchanges") or [])
            products = set(data.get("products") or [])
            cash = float(available.get("cash") or 0)
            buying_power = float(equity.get("net") or cash)
            cnc_equity_enabled = bool(equity.get("enabled")) and "NSE" in exchanges and "CNC" in products
            return BrokerAccount(
                account_id=str(data.get("user_id", "")),
                status="ACTIVE" if data and cnc_equity_enabled else "UNKNOWN",
                trading_enabled=cnc_equity_enabled,
                buying_power=buying_power,
                cash=cash,
                raw_response={"profile": data, "margins": margins},
            )
        except httpx.HTTPError as exc:
            raise FailClosedError("zerodha_account_request_failed") from exc

    def get_positions(self) -> list[dict[str, Any]]:
        response = self.client.get(f"{self.base_url}/portfolio/positions", headers=self._headers())
        if response.status_code != 200:
            raise FailClosedError("zerodha_positions_unavailable")
        return list(response.json().get("data", {}).get("net", []))

    def get_orders(self) -> list[dict[str, Any]]:
        response = self.client.get(f"{self.base_url}/orders", headers=self._headers())
        if response.status_code != 200:
            raise FailClosedError("zerodha_orders_unavailable")
        return list(response.json().get("data", []))

    def get_order(self, order_id: str) -> dict[str, Any]:
        orders = self.get_orders()
        for order in orders:
            if str(order.get("order_id")) == order_id:
                return order
        raise FailClosedError("zerodha_order_not_found")

    def place_order(self, order_intent: OrderIntent) -> BrokerOrderResult:
        if order_intent.broker != BrokerName.ZERODHA:
            raise FailClosedError("order_intent_broker_mismatch")
        if order_intent.order_type not in {OrderType.MARKET, OrderType.LIMIT}:
            raise FailClosedError("zerodha_order_type_not_supported")

        payload: dict[str, Any] = {
            "tradingsymbol": order_intent.symbol,
            "exchange": "NSE",
            "transaction_type": "BUY" if order_intent.side == OrderSide.BUY else "SELL",
            "quantity": order_intent.quantity,
            "product": "CNC",
            "order_type": order_intent.order_type.value,
            "validity": "DAY",
            "tag": order_intent.idempotency_key[:20],
        }
        if order_intent.limit_price is not None:
            payload["price"] = order_intent.limit_price

        response = self.client.post(
            f"{self.base_url}/orders/regular", headers=self._headers(), data=payload
        )
        raw = response.json() if response.content else {}
        if response.status_code >= 400:
            return BrokerOrderResult(status=OrderStatus.REJECTED, raw_response=raw)
        broker_order_id = str(raw.get("data", {}).get("order_id", "")) or None
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
            f"{self.base_url}/orders/regular/{order_id}", headers=self._headers()
        )
        raw = response.json() if response.content else {}
        if response.status_code >= 400:
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
        status_text = str(raw.get("status", "")).upper()
        status_map = {
            "COMPLETE": OrderStatus.FILLED,
            "OPEN": OrderStatus.ACCEPTED,
            "CANCELLED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
        }
        return BrokerOrderResult(
            broker_order_id=order_id,
            status=status_map.get(status_text, OrderStatus.UNKNOWN_REQUIRES_RECONCILIATION),
            raw_response=raw,
        )
