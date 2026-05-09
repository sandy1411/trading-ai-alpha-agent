from __future__ import annotations

from datetime import UTC, datetime

from app.core.config import Settings
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


def test_configured_india_holiday_override_closes_market() -> None:
    settings = Settings(_env_file=None, india_market_holiday_overrides="2026-04-30")
    april_30 = datetime(2026, 4, 30, 4, 30, tzinfo=UTC)

    status = MarketCalendar(settings).status(Market.INDIA, april_30)

    assert status.state == MarketCalendarState.CLOSED
    assert status.reason == "configured_exchange_holiday"


def test_configured_special_open_can_override_static_holiday() -> None:
    settings = Settings(_env_file=None, india_market_special_open_dates="2026-05-01")
    may_day = datetime(2026, 5, 1, 4, 30, tzinfo=UTC)

    status = MarketCalendar(settings).status(Market.INDIA, may_day)

    assert status.state == MarketCalendarState.OPEN
    assert status.reason == "special_session_open"


def test_configured_early_close_blocks_after_session_end() -> None:
    settings = Settings(_env_file=None, india_market_early_close_overrides="2026-04-30=12:00")
    after_early_close = datetime(2026, 4, 30, 7, 0, tzinfo=UTC)

    status = MarketCalendar(settings).status(Market.INDIA, after_early_close)

    assert status.state == MarketCalendarState.CLOSED
    assert status.reason == "after_configured_early_close"


def test_calendar_fails_closed_after_verified_year() -> None:
    settings = Settings(_env_file=None, market_calendar_verified_through_year=2026)
    future_open_time = datetime(2027, 4, 30, 4, 30, tzinfo=UTC)

    status = MarketCalendar(settings).status(Market.INDIA, future_open_time)

    assert status.state == MarketCalendarState.UNKNOWN
    assert status.reason == "calendar_holiday_source_unavailable"


def test_invalid_calendar_override_fails_closed() -> None:
    settings = Settings(_env_file=None, india_market_holiday_overrides="not-a-date")
    april_30 = datetime(2026, 4, 30, 4, 30, tzinfo=UTC)

    status = MarketCalendar(settings).status(Market.INDIA, april_30)

    assert status.state == MarketCalendarState.UNKNOWN
    assert status.reason == "calendar_invalid_holiday_date"
