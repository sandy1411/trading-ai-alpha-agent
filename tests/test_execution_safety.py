from __future__ import annotations

import httpx
import pytest

from app.brokers.alpaca_broker import AlpacaBroker
from app.brokers.base import _issue_broker_execution_context
from app.brokers.zerodha_broker import ZerodhaBroker
from app.core.config import Settings
from app.core.enums import BrokerName, Market
from app.core.errors import FailClosedError
from tests.conftest import order_intent


def test_zerodha_place_order_requires_execution_agent_context() -> None:
    broker = ZerodhaBroker(
        settings=Settings(_env_file=None),
        client=httpx.Client(transport=httpx.MockTransport(_no_network_handler)),
    )

    with pytest.raises(FailClosedError, match="broker_execution_context_required"):
        broker.place_order(order_intent())


def test_alpaca_place_order_requires_execution_agent_context() -> None:
    broker = AlpacaBroker(
        settings=Settings(_env_file=None),
        client=httpx.Client(transport=httpx.MockTransport(_no_network_handler)),
    )
    intent = order_intent().model_copy(update={"market": Market.US, "broker": BrokerName.ALPACA})

    with pytest.raises(FailClosedError, match="broker_execution_context_required"):
        broker.place_order(intent)


def test_broker_context_rejects_market_mismatch() -> None:
    intent = order_intent()
    context = _issue_broker_execution_context(intent)
    mismatched = intent.model_copy(update={"market": Market.US})

    broker = ZerodhaBroker(
        settings=Settings(_env_file=None),
        client=httpx.Client(transport=httpx.MockTransport(_no_network_handler)),
    )

    with pytest.raises(FailClosedError, match="broker_execution_context_market_mismatch"):
        broker.place_order(mismatched, execution_context=context)


def _no_network_handler(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"unexpected broker network call: {request.method} {request.url}")
