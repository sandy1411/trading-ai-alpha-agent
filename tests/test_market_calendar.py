from __future__ import annotations

from datetime import UTC, datetime

from app.core.enums import Market, MarketCalendarState
from app.risk.market_calendar import MarketCalendar
from tests.conftest import monday_india_open


def test_india_market_open_during_regular_session(settings) -> None:
    status = MarketCalendar(settings).status(Market.INDIA, monday_india_open())

    assert status.state == MarketCalendarState.OPEN


def test_us_market_closed_on_weekend(settings) -> None:
    sunday = datetime(2026, 5, 3, 14, 0, tzinfo=UTC)

    status = MarketCalendar(settings).status(Market.US, sunday)

    assert status.state == MarketCalendarState.CLOSED


def test_india_market_closed_on_exchange_holiday(settings) -> None:
    may_day = datetime(2026, 5, 1, 4, 30, tzinfo=UTC)

    status = MarketCalendar(settings).status(Market.INDIA, may_day)

    assert status.state == MarketCalendarState.CLOSED
    assert status.reason == "exchange_holiday"


def test_india_market_expected_open_on_april_30_2026(settings) -> None:
    april_30 = datetime(2026, 4, 30, 4, 30, tzinfo=UTC)

    status = MarketCalendar(settings).status(Market.INDIA, april_30)

    assert status.state == MarketCalendarState.OPEN
