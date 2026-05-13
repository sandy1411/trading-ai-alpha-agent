from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.core.enums import AuthStatus, Market, ProviderStatus
from app.db.session import SessionLocal
from app.risk.market_calendar import MarketCalendar
from app.services.broker_service import broker_service
from app.services.provider_service import provider_service


class ShadowReadinessService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.calendar = MarketCalendar(self.settings)

    def status(self) -> dict[str, Any]:
        brokers = broker_service.statuses()
        providers = provider_service.statuses()
        checks: list[dict[str, Any]] = []

        checks.append(self._check("shadow_training_enabled", self.settings.shadow_training_enabled))
        checks.append(
            self._check(
                "mode_is_shadow_live",
                self.settings.trading_mode.is_shadow_like,
                self.settings.trading_mode.value,
            )
        )
        checks.append(
            self._check("live_trading_disabled", not self.settings.live_trading_enabled)
        )
        checks.append(self._check("kill_switch_on", self.settings.kill_switch))
        checks.append(self._database_check())
        checks.append(
            self._check(
                "zerodha_credentials_present",
                bool(self.settings.zerodha_api_key and self.settings.zerodha_access_token),
            )
        )

        zerodha = next((broker for broker in brokers if broker.broker_name == "ZERODHA"), None)
        zerodha_data = next(
            (provider for provider in providers if provider.provider_name == "ZERODHA_KITE"),
            None,
        )
        alpaca_data = next((provider for provider in providers if provider.provider_name == "ALPACA"), None)
        fx_provider = next(
            (provider for provider in providers if provider.provider_name == "ALPHA_VANTAGE_FX"),
            None,
        )
        checks.append(
            self._check(
                "zerodha_auth_currently_valid",
                bool(zerodha and zerodha.auth_status == AuthStatus.VALID),
                zerodha.auth_status.value if zerodha else "MISSING",
            )
        )
        checks.append(
            self._check(
                "zerodha_data_fresh_now",
                bool(zerodha_data and zerodha_data.status == ProviderStatus.OK),
                zerodha_data.status.value if zerodha_data else "MISSING",
            )
        )

        tomorrow = self._next_india_business_date()
        tomorrow_open = self._calendar_probe(Market.INDIA, tomorrow)
        checks.append(
            self._check(
                "india_market_expected_open_next_session",
                tomorrow_open["is_open"],
                tomorrow_open["reason"],
            )
        )

        checks.append(
            self._check(
                "alpaca_us_data_credentials_present",
                bool(self.settings.alpaca_api_key and self.settings.alpaca_secret_key),
                "Set ALPACA_API_KEY and ALPACA_SECRET_KEY for US equities/ETFs shadow data.",
                severity="WARN",
            )
        )
        checks.append(
            self._check(
                "alpaca_us_data_available",
                bool(alpaca_data and alpaca_data.status == ProviderStatus.OK),
                alpaca_data.status.value if alpaca_data else "MISSING",
                severity="WARN",
            )
        )
        checks.append(
            self._check(
                "usd_inr_fx_credentials_present",
                bool(self.settings.alpha_vantage_api_key),
                "Set ALPHA_VANTAGE_API_KEY for fresh USD/INR conversion.",
                severity="WARN",
            )
        )
        checks.append(
            self._check(
                "usd_inr_fx_provider_available",
                bool(fx_provider and fx_provider.status == ProviderStatus.OK),
                fx_provider.status.value if fx_provider else "MISSING",
                severity="WARN",
            )
        )
        us_session = self.calendar.status(Market.US)
        us_ready = bool(
            self.settings.alpaca_api_key
            and self.settings.alpaca_secret_key
            and self.settings.alpha_vantage_api_key
            and alpaca_data
            and alpaca_data.status == ProviderStatus.OK
            and fx_provider
            and fx_provider.status == ProviderStatus.OK
            and us_session.is_open
        )
        checks.append(
            self._check(
                "us_shadow_ready_now",
                us_ready,
                f"Ready only during US regular session with Alpaca data and USD/INR FX. Current calendar: {us_session.reason}.",
                severity="WARN",
            )
        )
        checks.append(
            self._check(
                "zerodha_token_refresh_required_tomorrow",
                False,
                "Kite access tokens expire the next day at 6 AM IST; refresh before market open.",
                severity="WARN",
            )
        )

        blocking = [
            check
            for check in checks
            if not check["passed"] and check["severity"] == "BLOCKER"
        ]
        return {
            "ready_for_india_shadow_now": len(blocking) == 0,
            "ready_for_us_shadow_now": us_ready,
            "ready_for_india_shadow_tomorrow_after_token_refresh": all(
                check["passed"] or check["severity"] == "WARN" or check["name"] in {
                    "zerodha_auth_currently_valid",
                    "zerodha_data_fresh_now",
                }
                for check in checks
            ),
            "next_india_session_date": tomorrow.isoformat(),
            "checks": checks,
            "brokers": [broker.model_dump(mode="json") for broker in brokers],
            "providers": [provider.model_dump(mode="json") for provider in providers],
        }

    def _database_check(self) -> dict[str, Any]:
        try:
            with SessionLocal() as session:
                session.execute(text("select 1"))
            return self._check("database_reachable", True)
        except Exception as exc:
            return self._check("database_reachable", False, str(exc))

    def _next_india_business_date(self) -> date:
        india_now = datetime.now(ZoneInfo(self.settings.india_timezone))
        candidate = india_now.date() + timedelta(days=1)
        while True:
            probe = self._calendar_probe(Market.INDIA, candidate)
            if probe["is_open"] or probe["reason"] == "outside_regular_session":
                return candidate
            candidate += timedelta(days=1)

    def _calendar_probe(self, market: Market, local_date: date) -> dict[str, Any]:
        timezone_name = self.settings.india_timezone if market == Market.INDIA else self.settings.us_timezone
        probe_local = datetime.combine(local_date, time(10, 0), tzinfo=ZoneInfo(timezone_name))
        status = self.calendar.status(market, probe_local.astimezone(ZoneInfo("UTC")))
        return {"is_open": status.is_open, "reason": status.reason}

    @staticmethod
    def _check(
        name: str,
        passed: bool,
        detail: str | bool | None = None,
        severity: str = "BLOCKER",
    ) -> dict[str, Any]:
        return {
            "name": name,
            "passed": passed,
            "severity": severity,
            "detail": detail,
        }


shadow_readiness_service = ShadowReadinessService()
