from __future__ import annotations

from datetime import datetime, time

from app.core.config import Settings, get_settings
from app.core.enums import Market, MarketCalendarState
from app.core.time_utils import as_timezone, utc_now
from app.schemas.risk import MarketCalendarStatus

INDIA_TRADING_HOLIDAYS_2026 = {
    "2026-01-26",
    "2026-03-03",
    "2026-03-26",
    "2026-03-31",
    "2026-04-03",
    "2026-04-14",
    "2026-05-01",
    "2026-05-28",
    "2026-06-26",
    "2026-09-14",
    "2026-10-02",
    "2026-10-20",
    "2026-11-10",
    "2026-11-24",
    "2026-12-25",
}

US_TRADING_HOLIDAYS_2026 = {
    "2026-01-01",
    "2026-01-19",
    "2026-02-16",
    "2026-04-03",
    "2026-05-25",
    "2026-06-19",
    "2026-07-03",
    "2026-09-07",
    "2026-11-26",
    "2026-12-25",
}


class MarketCalendar:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def status(self, market: Market, now: datetime | None = None) -> MarketCalendarStatus:
        instant = now or utc_now()
        timezone_name = (
            self.settings.india_timezone if market == Market.INDIA else self.settings.us_timezone
        )
        local = as_timezone(instant, timezone_name)
        if local.weekday() >= 5:
            return MarketCalendarStatus(
                market=market,
                state=MarketCalendarState.CLOSED,
                reason="weekend_market_closed",
            )
        local_date = local.date().isoformat()
        if market == Market.INDIA and local_date in INDIA_TRADING_HOLIDAYS_2026:
            return MarketCalendarStatus(
                market=market,
                state=MarketCalendarState.CLOSED,
                reason="exchange_holiday",
            )
        if market == Market.US and local_date in US_TRADING_HOLIDAYS_2026:
            return MarketCalendarStatus(
                market=market,
                state=MarketCalendarState.CLOSED,
                reason="exchange_holiday",
            )

        if market == Market.INDIA:
            is_open = time(9, 15) <= local.time() < time(15, 30)
        else:
            is_open = time(9, 30) <= local.time() < time(16, 0)

        return MarketCalendarStatus(
            market=market,
            state=MarketCalendarState.OPEN if is_open else MarketCalendarState.CLOSED,
            reason="regular_session_open" if is_open else "outside_regular_session",
        )
