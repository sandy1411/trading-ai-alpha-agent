from __future__ import annotations

from app.brokers.alpaca_broker import AlpacaBroker
from app.brokers.base import BaseBroker
from app.brokers.zerodha_broker import ZerodhaBroker
from app.core.enums import BrokerName
from app.core.errors import FailClosedError


class OrderRouter:
    def __init__(
        self,
        zerodha: ZerodhaBroker | None = None,
        alpaca: AlpacaBroker | None = None,
    ) -> None:
        self._brokers: dict[BrokerName, BaseBroker] = {
            BrokerName.ZERODHA: zerodha or ZerodhaBroker(),
            BrokerName.ALPACA: alpaca or AlpacaBroker(),
        }

    def broker_for(self, broker_name: BrokerName) -> BaseBroker:
        broker = self._brokers.get(broker_name)
        if broker is None:
            raise FailClosedError("broker_not_configured")
        return broker
