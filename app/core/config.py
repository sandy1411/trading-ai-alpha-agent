from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.enums import ComplianceApprovalStatus, TradingMode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Sandy-Trading-AI"
    env: str = "local"

    trading_mode: TradingMode = TradingMode.SHADOW_LIVE_REAL_DATA
    live_trading_enabled: bool = False
    kill_switch: bool = True
    api_control_auth_enabled: bool = False
    api_control_token: str = ""

    database_url: str = "postgresql+psycopg://dalalwall:dalalwall@localhost:5432/dalalwall_ai_alpha"
    redis_url: str = "redis://localhost:6379/0"

    openai_api_key: str = ""
    zerodha_api_key: str = ""
    zerodha_api_secret: str = ""
    zerodha_access_token: str = ""
    zerodha_auto_exchange_on_callback: bool = True
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    alpaca_data_feed: str = "iex"
    alpha_vantage_api_key: str = ""
    finnhub_api_key: str = ""
    benzinga_api_key: str = ""

    base_currency: str = "INR"
    starting_capital_inr: float = 500_000

    real_provider_required: bool = True
    broker_reconciliation_required: bool = True
    risk_engine_required: bool = True

    allow_dummy_broker: bool = False
    allow_mock_broker: bool = False
    allow_fake_market_data: bool = False
    allow_fake_order_fills: bool = False

    long_only_mode: bool = True
    allow_margin: bool = False
    allow_short_selling: bool = False
    allow_options: bool = False
    allow_derivatives: bool = False
    allow_crypto: bool = False
    allow_leveraged_etfs: bool = False

    max_risk_per_trade_pct: float = Field(default=0.005, gt=0, le=0.05)
    max_daily_loss_pct: float = Field(default=0.0125, gt=0, le=0.2)
    max_weekly_loss_pct: float = Field(default=0.04, gt=0, le=0.5)
    max_monthly_drawdown_pct: float = Field(default=0.08, gt=0, le=0.7)
    max_total_drawdown_pct: float = Field(default=0.10, gt=0, le=0.8)

    max_single_stock_position_pct: float = Field(default=0.075, gt=0, le=1)
    max_single_etf_position_pct: float = Field(default=0.15, gt=0, le=1)
    max_gold_etf_position_pct: float = Field(default=0.20, gt=0, le=1)
    max_debt_etf_position_pct: float = Field(default=0.30, gt=0, le=1)
    max_sector_exposure_pct: float = Field(default=0.25, gt=0, le=1)
    max_total_equity_exposure_pct: float = Field(default=0.80, gt=0, le=1)
    max_india_exposure_pct: float = Field(default=0.70, gt=0, le=1)
    max_us_exposure_pct: float = Field(default=0.70, gt=0, le=1)

    max_open_positions_total: int = Field(default=15, ge=1)
    max_open_positions_india: int = Field(default=8, ge=1)
    max_open_positions_us: int = Field(default=8, ge=1)

    data_staleness_seconds_intraday: int = Field(default=120, ge=1)
    news_staleness_minutes: int = Field(default=60, ge=1)
    fx_staleness_minutes: int = Field(default=60, ge=1)

    india_timezone: str = "Asia/Kolkata"
    us_timezone: str = "America/New_York"
    market_calendar_fail_closed_after_verified_year: bool = True
    market_calendar_verified_through_year: int = Field(default=2026, ge=2026)
    india_market_holiday_overrides: str = ""
    us_market_holiday_overrides: str = ""
    india_market_special_open_dates: str = ""
    us_market_special_open_dates: str = ""
    india_market_early_close_overrides: str = ""
    us_market_early_close_overrides: str = ""

    live_market_quality_checks_required: bool = True
    micro_live_market_quality_checks_required: bool = False
    min_live_intraday_volume: int = Field(default=50_000, ge=0)
    min_live_average_daily_volume: int = Field(default=100_000, ge=0)
    min_live_average_daily_notional_inr: float = Field(default=25_000_000, ge=0)
    max_live_bid_ask_spread_pct: float = Field(default=0.005, ge=0, le=0.20)
    max_live_estimated_slippage_pct: float = Field(default=0.0025, ge=0, le=0.20)

    india_algo_compliance_required: bool = True
    india_algo_registration_status: ComplianceApprovalStatus = ComplianceApprovalStatus.NOT_APPROVED
    india_broker_approval_status: ComplianceApprovalStatus = ComplianceApprovalStatus.NOT_APPROVED
    india_exchange_algo_identifier: str = ""

    enable_email_summary: bool = False
    email_smtp_host: str = ""
    email_smtp_port: int | None = None
    email_smtp_use_tls: bool = True
    email_smtp_require_auth: bool = True
    email_username: str = ""
    email_password: str = ""
    email_to: str = ""

    shadow_training_enabled: bool = True
    shadow_training_interval_seconds: int = Field(default=60, ge=60)
    shadow_hypothesis_notional_inr: float = Field(default=50_000, gt=0)
    intraday_min_total_samples: int = Field(default=100_000, ge=1)
    intraday_min_samples_per_market: int = Field(default=25_000, ge=0)
    intraday_min_stop_loss_coverage: float = Field(default=0.98, gt=0, le=1)
    intraday_training_max_samples: int = Field(default=150_000, ge=1)
    intraday_exit_profit_lock_pct: float = Field(default=0.70, ge=0, le=1)
    intraday_exit_loss_watch_pct: float = Field(default=0.50, ge=0, le=1)
    intraday_profit_giveback_exit_pct: float = Field(default=0.25, ge=0, le=1)
    intraday_min_profit_lock_inr: float = Field(default=300, ge=0)
    intraday_min_profit_lock_pct: float = Field(default=0.005, ge=0, le=1)
    intraday_profit_booking_enabled: bool = True
    intraday_profit_booking_target_progress_pct: float = Field(default=0.45, ge=0, le=1)
    intraday_profit_booking_min_pnl_inr: float = Field(default=250, ge=0)
    intraday_profit_booking_min_pnl_pct: float = Field(default=0.003, ge=0, le=1)
    intraday_shadow_exit_enabled: bool = True
    intraday_reentry_cooldown_minutes: int = Field(default=20, ge=0)
    intraday_loss_discipline_enabled: bool = True
    intraday_loss_discipline_lookback_minutes: int = Field(default=120, ge=1)
    intraday_symbol_loss_pause_min_samples: int = Field(default=4, ge=1)
    intraday_symbol_loss_pause_loss_rate: float = Field(default=0.60, ge=0, le=1)
    intraday_symbol_loss_pause_inr: float = Field(default=1_000, ge=0)
    intraday_symbol_loss_pause_pct: float = Field(default=0.01, ge=0, le=1)
    intraday_market_loss_pause_min_samples: int = Field(default=20, ge=1)
    intraday_market_loss_pause_win_rate: float = Field(default=0.35, ge=0, le=1)
    intraday_market_loss_pause_inr: float = Field(default=5_000, ge=0)
    intraday_previous_session_loss_pause_enabled: bool = True
    intraday_previous_session_loss_pause_lookback_days: int = Field(default=3, ge=1)
    intraday_previous_session_loss_pause_inr: float = Field(default=750, ge=0)
    intraday_previous_session_loss_pause_pct: float = Field(default=0.0075, ge=0, le=1)
    shadow_india_symbols: str = (
        "RELIANCE,TCS,INFY,HDFCBANK,ICICIBANK,SBIN,LT,AXISBANK,"
        "KOTAKBANK,BAJFINANCE,BHARTIARTL,ITC,HINDUNILVR,SUNPHARMA,"
        "MARUTI,TITAN,ASIANPAINT,ULTRACEMCO,POWERGRID,NTPC"
    )
    shadow_us_symbols: str = (
        "SPY,QQQ,DIA,IWM,AAPL,MSFT,NVDA,AMZN,META,GOOGL,TSLA,AMD,AVGO,JPM,V,UNH"
    )

    @field_validator("email_smtp_port", mode="before")
    @classmethod
    def empty_email_port_is_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @property
    def shadow_india_symbol_list(self) -> list[str]:
        return [symbol.strip().upper() for symbol in self.shadow_india_symbols.split(",") if symbol.strip()]

    @property
    def shadow_us_symbol_list(self) -> list[str]:
        return [symbol.strip().upper() for symbol in self.shadow_us_symbols.split(",") if symbol.strip()]

    def live_mode_safety_errors(self) -> list[str]:
        errors: list[str] = []
        if not self.trading_mode.is_live_capable:
            errors.append("trading_mode_is_not_live_capable")
        if not self.live_trading_enabled:
            errors.append("live_trading_enabled_false")
        if self.kill_switch:
            errors.append("kill_switch_enabled")
        if not self.real_provider_required:
            errors.append("real_provider_required_false")
        if not self.broker_reconciliation_required:
            errors.append("broker_reconciliation_required_false")
        if not self.risk_engine_required:
            errors.append("risk_engine_required_false")
        blocked_flags = {
            "allow_dummy_broker": self.allow_dummy_broker,
            "allow_mock_broker": self.allow_mock_broker,
            "allow_fake_market_data": self.allow_fake_market_data,
            "allow_fake_order_fills": self.allow_fake_order_fills,
            "allow_margin": self.allow_margin,
            "allow_short_selling": self.allow_short_selling,
            "allow_options": self.allow_options,
            "allow_derivatives": self.allow_derivatives,
            "allow_crypto": self.allow_crypto,
            "allow_leveraged_etfs": self.allow_leveraged_etfs,
        }
        errors.extend(f"{name}_true" for name, enabled in blocked_flags.items() if enabled)
        return errors


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
