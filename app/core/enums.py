from __future__ import annotations

from enum import StrEnum


class TradingMode(StrEnum):
    BACKTEST = "BACKTEST"
    MARKET_REPLAY = "MARKET_REPLAY"
    SHADOW_LIVE = "SHADOW_LIVE"
    PAPER_TRADING = "PAPER_TRADING"
    LIVE_DISABLED = "LIVE_DISABLED"
    BACKTEST_REAL_HISTORICAL_DATA = "BACKTEST_REAL_HISTORICAL_DATA"
    SHADOW_LIVE_REAL_DATA = "SHADOW_LIVE_REAL_DATA"
    MICRO_LIVE_AUTONOMOUS = "MICRO_LIVE_AUTONOMOUS"
    LIVE_AUTONOMOUS = "LIVE_AUTONOMOUS"

    @property
    def is_live_capable(self) -> bool:
        return self in {self.MICRO_LIVE_AUTONOMOUS, self.LIVE_AUTONOMOUS}

    @property
    def is_shadow_like(self) -> bool:
        return self in {
            self.SHADOW_LIVE,
            self.SHADOW_LIVE_REAL_DATA,
            self.PAPER_TRADING,
            self.BACKTEST,
            self.BACKTEST_REAL_HISTORICAL_DATA,
            self.MARKET_REPLAY,
            self.LIVE_DISABLED,
        }


class Market(StrEnum):
    INDIA = "INDIA"
    US = "US"


class AssetClass(StrEnum):
    EQUITY = "EQUITY"
    ETF = "ETF"
    CASH = "CASH"


class TradeAction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NO_TRADE = "NO_TRADE"


class RiskDecisionType(StrEnum):
    APPROVED = "APPROVED"
    REDUCE_SIZE = "REDUCE_SIZE"
    REJECTED = "REJECTED"
    NO_TRADE = "NO_TRADE"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class BrokerName(StrEnum):
    ZERODHA = "ZERODHA"
    ALPACA = "ALPACA"


class ProviderStatus(StrEnum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"
    MISSING_CREDENTIALS = "MISSING_CREDENTIALS"


class AuthStatus(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"
    MISSING_CREDENTIALS = "MISSING_CREDENTIALS"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class AccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    DISABLED = "DISABLED"
    UNKNOWN = "UNKNOWN"


class FreshnessStatus(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    MISSING = "MISSING"


class MarketCalendarState(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN_REQUIRES_RECONCILIATION = "UNKNOWN_REQUIRES_RECONCILIATION"


class ReconciliationState(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    REQUIRED = "REQUIRED"
    RECONCILED = "RECONCILED"
    BLOCKING_DUPLICATES = "BLOCKING_DUPLICATES"


class ComplianceApprovalStatus(StrEnum):
    APPROVED = "APPROVED"
    NOT_APPROVED = "NOT_APPROVED"
    PENDING = "PENDING"
    NOT_REQUIRED = "NOT_REQUIRED"


class ProviderType(StrEnum):
    MARKET_DATA = "MARKET_DATA"
    NEWS = "NEWS"
    FX = "FX"
    BROKER_DATA = "BROKER_DATA"
