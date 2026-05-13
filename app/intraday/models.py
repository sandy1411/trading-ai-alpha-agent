from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from app.core.enums import Market


class Direction(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class MarketRegime(StrEnum):
    STRONG_BULLISH = "STRONG_BULLISH"
    WEAK_BULLISH = "WEAK_BULLISH"
    STRONG_BEARISH = "STRONG_BEARISH"
    WEAK_BEARISH = "WEAK_BEARISH"
    SIDEWAYS = "SIDEWAYS"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_LIQUIDITY = "LOW_LIQUIDITY"
    NO_TRADE = "NO_TRADE"


class SignalDecision(StrEnum):
    VALID = "VALID"
    WATCH_ONLY = "WATCH_ONLY"
    REJECTED = "REJECTED"


class FillStatus(StrEnum):
    FILLED = "FILLED"
    PARTIAL_FILL = "PARTIAL_FILL"
    MISSED = "MISSED"
    REJECTED = "REJECTED"


class VirtualPositionStatus(StrEnum):
    PENDING_ENTRY = "PENDING_ENTRY"
    OPEN = "OPEN"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    EXITED = "EXITED"
    STOPPED_OUT = "STOPPED_OUT"
    TARGET_HIT = "TARGET_HIT"
    FORCE_CLOSED = "FORCE_CLOSED"
    INVALIDATED = "INVALIDATED"


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class MarketDataSnapshot:
    market: Market
    symbol: str
    timestamp: datetime
    last_price: float
    vwap: float | None
    volume: float
    previous_day_high: float | None = None
    previous_day_low: float | None = None
    opening_range_high_15m: float | None = None
    opening_range_low_15m: float | None = None
    opening_range_high_30m: float | None = None
    opening_range_low_30m: float | None = None
    atr: float | None = None
    bid: float | None = None
    ask: float | None = None
    candles_1m: tuple[Candle, ...] = ()
    candles_3m: tuple[Candle, ...] = ()
    candles_5m: tuple[Candle, ...] = ()
    index_trend: float | None = None
    sector_trend: float | None = None
    market_breadth: float | None = None
    gap_pct: float | None = None
    feed_connected: bool = True
    source: str = "UNKNOWN"
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def spread_pct(self) -> float | None:
        if self.bid is None or self.ask is None or self.last_price <= 0:
            return None
        return max(self.ask - self.bid, 0.0) / self.last_price


@dataclass(frozen=True)
class DataQualityReport:
    ok: bool
    reasons: list[str]
    metrics: dict[str, float | int | str | bool | None]


@dataclass(frozen=True)
class Signal:
    signal_id: str
    symbol: str
    market: Market
    direction: Direction
    strategy_name: str
    regime_at_signal: MarketRegime
    entry_price: float
    stop_loss: float
    target_price: float
    risk_reward_ratio: float
    confidence_score: float
    reason_codes: list[str]
    invalidation_rules: list[str]
    timestamp: datetime
    candle_snapshot: dict[str, Any]
    market_snapshot: dict[str, Any]

    @classmethod
    def create(
        cls,
        *,
        symbol: str,
        market: Market,
        direction: Direction,
        strategy_name: str,
        regime_at_signal: MarketRegime,
        entry_price: float,
        stop_loss: float,
        target_price: float,
        confidence_score: float,
        reason_codes: list[str],
        invalidation_rules: list[str],
        candle_snapshot: dict[str, Any],
        market_snapshot: dict[str, Any],
        timestamp: datetime | None = None,
    ) -> "Signal":
        risk = abs(entry_price - stop_loss)
        reward = abs(target_price - entry_price)
        ratio = reward / risk if risk > 0 else 0.0
        return cls(
            signal_id=str(uuid4()),
            symbol=symbol.upper(),
            market=market,
            direction=direction,
            strategy_name=strategy_name,
            regime_at_signal=regime_at_signal,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_price=target_price,
            risk_reward_ratio=ratio,
            confidence_score=confidence_score,
            reason_codes=reason_codes,
            invalidation_rules=invalidation_rules,
            timestamp=timestamp or datetime.now(UTC),
            candle_snapshot=candle_snapshot,
            market_snapshot=market_snapshot,
        )


@dataclass(frozen=True)
class ScoredSignal:
    signal: Signal
    score: int
    decision: SignalDecision
    reasons: list[str]
    component_scores: dict[str, int]


@dataclass(frozen=True)
class RiskApproval:
    approved: bool
    quantity: int = 0
    risk_amount: float = 0.0
    capital_required: float = 0.0
    rejection_reasons: list[str] = field(default_factory=list)
    metrics: dict[str, float | int | str | bool | None] = field(default_factory=dict)


@dataclass(frozen=True)
class ShadowOrder:
    shadow_order_id: str
    signal_id: str
    symbol: str
    direction: Direction
    expected_entry: float
    simulated_fill: float | None
    quantity: int
    slippage: float
    spread: float
    latency_ms: int
    fill_status: FillStatus
    rejection_reason: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class VirtualPosition:
    position_id: str
    symbol: str
    market: Market
    direction: Direction
    strategy: str
    regime_at_entry: MarketRegime
    entry_price: float
    stop_loss: float
    target_price: float
    quantity: int
    risk_amount: float
    status: VirtualPositionStatus
    entry_reason: list[str]
    opened_at: datetime
    current_price: float
    current_pnl: float = 0.0
    gross_pnl: float = 0.0
    net_pnl: float = 0.0
    charges: float = 0.0
    max_favorable_excursion: float = 0.0
    max_adverse_excursion: float = 0.0
    exit_reason: str | None = None
    closed_at: datetime | None = None


@dataclass(frozen=True)
class JournalEntry:
    timestamp: datetime
    event_type: str
    symbol: str
    direction: str = ""
    strategy: str = ""
    regime: str = ""
    signal_score: int | None = None
    reason_codes: list[str] = field(default_factory=list)
    rejection_reason: str | None = None
    entry_price: float | None = None
    stop_loss: float | None = None
    target: float | None = None
    quantity: int | None = None
    risk_amount: float | None = None
    risk_reward: float | None = None
    simulated_fill_price: float | None = None
    exit_price: float | None = None
    gross_pnl: float | None = None
    net_pnl: float | None = None
    charges: float | None = None
    slippage: float | None = None
    max_favorable_excursion: float | None = None
    max_adverse_excursion: float | None = None
    time_in_trade_seconds: float | None = None
    exit_reason: str | None = None
    market_snapshot: dict[str, Any] = field(default_factory=dict)
    candle_snapshot: dict[str, Any] = field(default_factory=dict)

    def model_dump(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat()
        return _json_safe(payload)


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value
