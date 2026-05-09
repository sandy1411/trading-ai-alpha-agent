from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from app.core.enums import Market, OrderSide
from app.paper.models import (
    CostModel,
    PaperAccountSnapshot,
    PaperBlockReason,
    PaperExecutionResult,
    PaperExitReason,
    PaperOrderRequest,
    PaperPosition,
    PaperRiskLimits,
    PaperTradeJournalEntry,
    PaperTradeStatus,
    new_journal_id,
    normalize_timestamp,
)


RESEARCH_ONLY_ENGINE = True
LIVE_BROKER_ADAPTER = False


class PaperTradingEngine:
    """Research-only accounting engine; it is not a broker adapter and cannot place orders."""

    is_broker_adapter = False
    can_place_live_orders = False

    def __init__(
        self,
        starting_cash: float,
        cost_model: CostModel | None = None,
        risk_limits: PaperRiskLimits | None = None,
        allow_short_selling: bool = False,
    ) -> None:
        if starting_cash <= 0:
            raise ValueError("starting_cash_must_be_positive")
        self.starting_cash = float(starting_cash)
        self.cash = float(starting_cash)
        self.cost_model = cost_model or CostModel()
        self.risk_limits = risk_limits or PaperRiskLimits()
        self.allow_short_selling = allow_short_selling
        self.positions: dict[str, PaperPosition] = {}
        self.journal: list[PaperTradeJournalEntry] = []
        self.realized_pnl = 0.0
        self.total_costs = 0.0
        self._daily_entry_count: defaultdict[date, int] = defaultdict(int)
        self._daily_realized_pnl: defaultdict[date, float] = defaultdict(float)

    def submit_order(
        self,
        request: PaperOrderRequest,
        exit_reason: PaperExitReason = PaperExitReason.NONE,
    ) -> PaperExecutionResult:
        submitted_at = normalize_timestamp(request.submitted_at)
        normalized = PaperOrderRequest(
            symbol=request.symbol.upper().strip(),
            market=request.market,
            side=request.side,
            quantity=request.quantity,
            reference_price=request.reference_price,
            submitted_at=submitted_at,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            metadata=dict(request.metadata),
        )
        if normalized.side == OrderSide.BUY:
            return self._open_position(normalized)
        return self._close_position(normalized, exit_reason)

    def evaluate_exit(
        self,
        symbol: str,
        *,
        market: Market,
        timestamp: datetime,
        low: float,
        high: float,
    ) -> PaperExecutionResult | None:
        position = self.positions.get(symbol.upper().strip())
        if position is None or position.market != market:
            return None
        if low <= position.stop_loss:
            return self.submit_order(
                PaperOrderRequest(
                    symbol=position.symbol,
                    market=position.market,
                    side=OrderSide.SELL,
                    quantity=position.quantity,
                    reference_price=position.stop_loss,
                    submitted_at=timestamp,
                    metadata={"exit_check": "stop_loss"},
                ),
                exit_reason=PaperExitReason.STOP_LOSS,
            )
        if position.take_profit is not None and high >= position.take_profit:
            return self.submit_order(
                PaperOrderRequest(
                    symbol=position.symbol,
                    market=position.market,
                    side=OrderSide.SELL,
                    quantity=position.quantity,
                    reference_price=position.take_profit,
                    submitted_at=timestamp,
                    metadata={"exit_check": "profit_target"},
                ),
                exit_reason=PaperExitReason.PROFIT_TARGET,
            )
        return None

    def close_open_position(
        self,
        symbol: str,
        *,
        market: Market,
        reference_price: float,
        timestamp: datetime,
        exit_reason: PaperExitReason = PaperExitReason.MANUAL_RESEARCH_EXIT,
    ) -> PaperExecutionResult:
        position = self.positions.get(symbol.upper().strip())
        quantity = position.quantity if position is not None else 0
        return self.submit_order(
            PaperOrderRequest(
                symbol=symbol,
                market=market,
                side=OrderSide.SELL,
                quantity=quantity,
                reference_price=reference_price,
                submitted_at=timestamp,
            ),
            exit_reason=exit_reason,
        )

    def snapshot(
        self,
        timestamp: datetime,
        marks: dict[str, float] | None = None,
    ) -> PaperAccountSnapshot:
        normalized_timestamp = normalize_timestamp(timestamp)
        marks = {key.upper(): value for key, value in (marks or {}).items()}
        liquidation_value = 0.0
        entry_basis = 0.0
        for symbol, position in self.positions.items():
            mark = marks.get(symbol, position.average_entry_price)
            sell_price = self.cost_model.execution_price(OrderSide.SELL, mark)
            gross = sell_price * position.quantity
            liquidation_value += gross - self.cost_model.transaction_cost(gross)
            entry_basis += position.entry_basis
        unrealized = liquidation_value - entry_basis
        return PaperAccountSnapshot(
            timestamp=normalized_timestamp,
            cash=self.cash,
            equity=self.cash + liquidation_value,
            realized_pnl=self.realized_pnl,
            unrealized_pnl=unrealized,
            total_costs=self.total_costs,
            open_positions=tuple(self.positions.values()),
        )

    def trade_journal(self) -> tuple[PaperTradeJournalEntry, ...]:
        return tuple(self.journal)

    def _open_position(self, request: PaperOrderRequest) -> PaperExecutionResult:
        block = self._entry_block_reason(request)
        if block is not None:
            return self._blocked(request, block)

        execution_price = self.cost_model.execution_price(OrderSide.BUY, request.reference_price)
        gross = execution_price * request.quantity
        costs = self.cost_model.transaction_cost(gross)
        cash_needed = gross + costs
        if self.cash - cash_needed < self.risk_limits.min_cash_buffer:
            return self._blocked(request, PaperBlockReason.INSUFFICIENT_CASH)

        self.cash -= cash_needed
        self.total_costs += costs
        position = PaperPosition(
            symbol=request.symbol,
            market=request.market,
            quantity=request.quantity,
            average_entry_price=execution_price,
            entry_cost_per_unit=costs / request.quantity,
            stop_loss=float(request.stop_loss),
            take_profit=request.take_profit,
            opened_at=request.submitted_at,
            metadata=dict(request.metadata),
        )
        self.positions[request.symbol] = position
        self._daily_entry_count[request.submitted_at.date()] += 1
        journal_entry = PaperTradeJournalEntry(
            id=new_journal_id(),
            timestamp=request.submitted_at,
            symbol=request.symbol,
            market=request.market,
            side=OrderSide.BUY,
            quantity=request.quantity,
            requested_price=request.reference_price,
            execution_price=execution_price,
            gross_value=gross,
            costs=costs,
            cash_change=-cash_needed,
            status=PaperTradeStatus.OPENED,
            message="research_entry_opened",
            metadata=dict(request.metadata),
        )
        self.journal.append(journal_entry)
        return PaperExecutionResult(accepted=True, journal_entry=journal_entry, position=position)

    def _close_position(
        self,
        request: PaperOrderRequest,
        exit_reason: PaperExitReason,
    ) -> PaperExecutionResult:
        position = self.positions.get(request.symbol)
        if position is None:
            return self._blocked(request, PaperBlockReason.INVALID_REQUEST, "position_not_open")
        if position.market != request.market:
            return self._blocked(request, PaperBlockReason.INVALID_REQUEST, "market_mismatch")
        if request.quantity <= 0:
            return self._blocked(request, PaperBlockReason.INVALID_REQUEST, "quantity_must_be_positive")
        if request.quantity > position.quantity:
            return self._blocked(request, PaperBlockReason.SHORT_SELLING_DISABLED)

        execution_price = self.cost_model.execution_price(OrderSide.SELL, request.reference_price)
        gross = execution_price * request.quantity
        costs = self.cost_model.transaction_cost(gross)
        entry_basis = (position.average_entry_price + position.entry_cost_per_unit) * request.quantity
        realized_pnl = gross - costs - entry_basis
        self.cash += gross - costs
        self.realized_pnl += realized_pnl
        self.total_costs += costs
        self._daily_realized_pnl[request.submitted_at.date()] += realized_pnl

        remaining_quantity = position.quantity - request.quantity
        if remaining_quantity <= 0:
            self.positions.pop(request.symbol, None)
            updated_position = None
        else:
            position.quantity = remaining_quantity
            updated_position = position

        journal_entry = PaperTradeJournalEntry(
            id=new_journal_id(),
            timestamp=request.submitted_at,
            symbol=request.symbol,
            market=request.market,
            side=OrderSide.SELL,
            quantity=request.quantity,
            requested_price=request.reference_price,
            execution_price=execution_price,
            gross_value=gross,
            costs=costs,
            cash_change=gross - costs,
            status=PaperTradeStatus.CLOSED,
            realized_pnl=realized_pnl,
            exit_reason=exit_reason,
            message="research_position_closed",
            metadata=dict(request.metadata),
        )
        self.journal.append(journal_entry)
        return PaperExecutionResult(
            accepted=True,
            journal_entry=journal_entry,
            position=updated_position,
        )

    def _entry_block_reason(self, request: PaperOrderRequest) -> PaperBlockReason | None:
        if request.quantity <= 0 or request.reference_price <= 0:
            return PaperBlockReason.INVALID_REQUEST
        if request.stop_loss is None:
            return PaperBlockReason.INVALID_REQUEST
        if request.stop_loss >= request.reference_price:
            return PaperBlockReason.INVALID_REQUEST
        if request.symbol in self.positions:
            return PaperBlockReason.POSITION_ALREADY_OPEN
        trading_day = request.submitted_at.date()
        if self._daily_entry_count[trading_day] >= self.risk_limits.max_trades_per_day:
            return PaperBlockReason.MAX_TRADES_PER_DAY
        if self._daily_realized_pnl[trading_day] <= -self.risk_limits.max_daily_loss:
            return PaperBlockReason.DAILY_LOSS_LIMIT
        return None

    def _blocked(
        self,
        request: PaperOrderRequest,
        reason: PaperBlockReason,
        message: str | None = None,
    ) -> PaperExecutionResult:
        journal_entry = PaperTradeJournalEntry(
            id=new_journal_id(),
            timestamp=request.submitted_at,
            symbol=request.symbol,
            market=request.market,
            side=request.side,
            quantity=max(request.quantity, 0),
            requested_price=max(request.reference_price, 0),
            execution_price=0.0,
            gross_value=0.0,
            costs=0.0,
            cash_change=0.0,
            status=PaperTradeStatus.BLOCKED,
            block_reason=reason,
            message=message or reason.value.lower(),
            metadata=dict(request.metadata),
        )
        self.journal.append(journal_entry)
        return PaperExecutionResult(accepted=False, journal_entry=journal_entry)
