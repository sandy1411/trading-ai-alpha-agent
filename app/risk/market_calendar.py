from __future__ import annotations

from datetime import date, datetime, time

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

STATIC_TRADING_HOLIDAYS: dict[Market, dict[int, set[str]]] = {
    Market.INDIA: {2026: INDIA_TRADING_HOLIDAYS_2026},
    Market.US: {2026: US_TRADING_HOLIDAYS_2026},
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
        local_day = local.date()
        configured_holidays, holiday_error = self._configured_dates(market, "holiday")
        special_open_dates, special_error = self._configured_dates(market, "special_open")
        early_closes, early_close_error = self._configured_early_closes(market)
        config_error = holiday_error or special_error or early_close_error
        if config_error:
            return MarketCalendarStatus(
                market=market,
                state=MarketCalendarState.UNKNOWN,
                reason=config_error,
            )

        if self._holiday_source_unavailable(market, local_day):
            return MarketCalendarStatus(
                market=market,
                state=MarketCalendarState.UNKNOWN,
                reason="calendar_holiday_source_unavailable",
            )

        is_special_open = local_day in special_open_dates
        if local.weekday() >= 5 and not is_special_open:
            return MarketCalendarStatus(
                market=market,
                state=MarketCalendarState.CLOSED,
                reason="weekend_market_closed",
            )
        local_date = local_day.isoformat()
        if local_day in configured_holidays and not is_special_open:
            return MarketCalendarStatus(
                market=market,
                state=MarketCalendarState.CLOSED,
                reason="configured_exchange_holiday",
            )
        if local_date in self._static_holidays(market, local_day.year) and not is_special_open:
            return MarketCalendarStatus(
                market=market,
                state=MarketCalendarState.CLOSED,
                reason="exchange_holiday",
            )

        if market == Market.INDIA:
            session_open = time(9, 15)
            session_close = time(15, 30)
        else:
            session_open = time(9, 30)
            session_close = time(16, 0)

        session_close = early_closes.get(local_day, session_close)
        if session_close <= session_open:
            return MarketCalendarStatus(
                market=market,
                state=MarketCalendarState.UNKNOWN,
                reason="calendar_early_close_before_open",
            )

        is_open = session_open <= local.time() < session_close
        if is_open:
            reason = "special_session_open" if is_special_open else "regular_session_open"
        elif local_day in early_closes and local.time() >= session_close:
            reason = "after_configured_early_close"
        else:
            reason = "outside_regular_session"

        return MarketCalendarStatus(
            market=market,
            state=MarketCalendarState.OPEN if is_open else MarketCalendarState.CLOSED,
            reason=reason,
        )

    def _static_holidays(self, market: Market, year: int) -> set[str]:
        return STATIC_TRADING_HOLIDAYS.get(market, {}).get(year, set())

    def _holiday_source_unavailable(self, market: Market, local_day: date) -> bool:
        if not self.settings.market_calendar_fail_closed_after_verified_year:
            return False
        if local_day.year <= self.settings.market_calendar_verified_through_year:
            return False
        return local_day.year not in STATIC_TRADING_HOLIDAYS.get(market, {})

    def _configured_dates(self, market: Market, kind: str) -> tuple[set[date], str | None]:
        raw = self._configured_date_source(market, kind)
        parsed: set[date] = set()
        for value in self._csv_items(raw):
            try:
                parsed.add(date.fromisoformat(value))
            except ValueError:
                return set(), f"calendar_invalid_{kind}_date"
        return parsed, None

    def _configured_early_closes(self, market: Market) -> tuple[dict[date, time], str | None]:
        raw = (
            self.settings.india_market_early_close_overrides
            if market == Market.INDIA
            else self.settings.us_market_early_close_overrides
        )
        parsed: dict[date, time] = {}
        for value in self._csv_items(raw):
            if "=" not in value:
                return {}, "calendar_invalid_early_close"
            raw_date, raw_time = [part.strip() for part in value.split("=", 1)]
            try:
                parsed[date.fromisoformat(raw_date)] = time.fromisoformat(raw_time)
            except ValueError:
                return {}, "calendar_invalid_early_close"
        return parsed, None

    def _configured_date_source(self, market: Market, kind: str) -> str:
        if market == Market.INDIA and kind == "holiday":
            return self.settings.india_market_holiday_overrides
        if market == Market.US and kind == "holiday":
            return self.settings.us_market_holiday_overrides
        if market == Market.INDIA and kind == "special_open":
            return self.settings.india_market_special_open_dates
        if market == Market.US and kind == "special_open":
            return self.settings.us_market_special_open_dates
        return ""

    @staticmethod
    def _csv_items(raw: str) -> list[str]:
        return [item.strip() for item in raw.split(",") if item.strip()]
