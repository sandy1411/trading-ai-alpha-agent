from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from app.core.enums import Market, OrderSide


class PaperTradeStatus(StrEnum):
    OPENED = "OPENED"
    CLOSED = "CLOSED"
    BLOCKED = "BLOCKED"


class PaperExitReason(StrEnum):
    NONE = "NONE"
    STOP_LOSS = "STOP_LOSS"
    PROFIT_TARGET = "PROFIT_TARGET"
    MANUAL_RESEARCH_EXIT = "MANUAL_RESEARCH_EXIT"
    END_OF_BACKTEST = "END_OF_BACKTEST"


class PaperBlockReason(StrEnum):
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
    INVALID_REQUEST = "INVALID_REQUEST"
    MAX_TRADES_PER_DAY = "MAX_TRADES_PER_DAY"
    POSITION_ALREADY_OPEN = "POSITION_ALREADY_OPEN"
    SHORT_SELLING_DISABLED = "SHORT_SELLING_DISABLED"


@dataclass(frozen=True)
class CostModel:
    brokerage_pct: float = 0.0003
    brokerage_flat: float = 0.0
    taxes_pct: float = 0.0002
    slippage_bps: float = 5.0

    def __post_init__(self) -> None:
        for name, value in (
            ("brokerage_pct", self.brokerage_pct),
            ("brokerage_flat", self.brokerage_flat),
            ("taxes_pct", self.taxes_pct),
            ("slippage_bps", self.slippage_bps),
        ):
            if value < 0:
                raise ValueError(f"{name}_must_be_non_negative")

    def execution_price(self, side: OrderSide, reference_price: float) -> float:
        if reference_price <= 0:
            raise ValueError("reference_price_must_be_positive")
        slippage_multiplier = self.slippage_bps / 10_000
        if side == OrderSide.BUY:
            return reference_price * (1 + slippage_multiplier)
        return reference_price * (1 - slippage_multiplier)

    def transaction_cost(self, gross_value: float) -> float:
        if gross_value < 0:
            raise ValueError("gross_value_must_be_non_negative")
        return gross_value * (self.brokerage_pct + self.taxes_pct) + self.brokerage_flat


@dataclass(frozen=True)
class PaperRiskLimits:
    max_trades_per_day: int = 5
    max_daily_loss: float = 5_000.0
    min_cash_buffer: float = 0.0

    def __post_init__(self) -> None:
        if self.max_trades_per_day <= 0:
            raise ValueError("max_trades_per_day_must_be_positive")
        if self.max_daily_loss <= 0:
            raise ValueError("max_daily_loss_must_be_positive")
        if self.min_cash_buffer < 0:
            raise ValueError("min_cash_buffer_must_be_non_negative")


@dataclass(frozen=True)
class PaperOrderRequest:
    symbol: str
    market: Market
    side: OrderSide
    quantity: int
    reference_price: float
    submitted_at: datetime
    stop_loss: float | None = None
    take_profit: float | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class PaperPosition:
    symbol: str
    market: Market
    quantity: int
    average_entry_price: float
    entry_cost_per_unit: float
    stop_loss: float
    take_profit: float | None
    opened_at: datetime
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def entry_basis(self) -> float:
        return (self.average_entry_price + self.entry_cost_per_unit) * self.quantity


@dataclass(frozen=True)
class PaperTradeJournalEntry:
    id: str
    timestamp: datetime
    symbol: str
    market: Market
    side: OrderSide
    quantity: int
    requested_price: float
    execution_price: float
    gross_value: float
    costs: float
    cash_change: float
    status: PaperTradeStatus
    realized_pnl: float = 0.0
    exit_reason: PaperExitReason = PaperExitReason.NONE
    block_reason: PaperBlockReason | None = None
    message: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PaperExecutionResult:
    accepted: bool
    journal_entry: PaperTradeJournalEntry
    position: PaperPosition | None = None


@dataclass(frozen=True)
class PaperAccountSnapshot:
    timestamp: datetime
    cash: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    total_costs: float
    open_positions: tuple[PaperPosition, ...]


def new_journal_id() -> str:
    return str(uuid4())


def normalize_timestamp(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
