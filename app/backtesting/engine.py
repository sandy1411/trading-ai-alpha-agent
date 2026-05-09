from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from app.core.enums import Market, OrderSide
from app.paper import CostModel, PaperRiskLimits, PaperTradingEngine
from app.paper.models import (
    PaperExitReason,
    PaperOrderRequest,
    PaperTradeJournalEntry,
    PaperTradeStatus,
)


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int | float = 0


@dataclass(frozen=True)
class BacktestSignal:
    symbol: str
    market: Market
    quantity: int
    stop_loss: float
    take_profit: float | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BacktestConfig:
    starting_cash: float = 100_000.0
    cost_model: CostModel = field(default_factory=CostModel)
    risk_limits: PaperRiskLimits = field(default_factory=PaperRiskLimits)
    close_open_positions_on_end: bool = True


@dataclass(frozen=True)
class EquityCurvePoint:
    timestamp: datetime
    equity: float
    cash: float
    realized_pnl: float
    unrealized_pnl: float


@dataclass(frozen=True)
class BacktestResult:
    trade_journal: tuple[PaperTradeJournalEntry, ...]
    equity_curve: tuple[EquityCurvePoint, ...]
    metrics: dict[str, float | int]


StrategyCallback = Callable[[Sequence[Candle]], BacktestSignal | None]


class HistoricalBacktestEngine:
    """Minimal research backtester that feeds strategies only prior candles."""

    def __init__(self, config: BacktestConfig | None = None) -> None:
        self.config = config or BacktestConfig()

    def run_single_symbol(
        self,
        *,
        symbol: str,
        market: Market,
        candles: Sequence[Candle],
        strategy: StrategyCallback,
    ) -> BacktestResult:
        clean_symbol = symbol.upper().strip()
        ordered_candles = self._validated_candles(candles)
        engine = PaperTradingEngine(
            starting_cash=self.config.starting_cash,
            cost_model=self.config.cost_model,
            risk_limits=self.config.risk_limits,
        )
        equity_curve: list[EquityCurvePoint] = []

        for index, candle in enumerate(ordered_candles):
            if index > 0 and clean_symbol not in engine.positions:
                history = tuple(ordered_candles[:index])
                signal = strategy(history)
                if signal is not None:
                    self._submit_signal(engine, signal, clean_symbol, market, candle)

            engine.evaluate_exit(
                clean_symbol,
                market=market,
                timestamp=candle.timestamp,
                low=candle.low,
                high=candle.high,
            )
            equity_curve.append(self._equity_point(engine, clean_symbol, candle))

        if (
            self.config.close_open_positions_on_end
            and ordered_candles
            and clean_symbol in engine.positions
        ):
            final_candle = ordered_candles[-1]
            engine.close_open_position(
                clean_symbol,
                market=market,
                reference_price=final_candle.close,
                timestamp=final_candle.timestamp,
                exit_reason=PaperExitReason.END_OF_BACKTEST,
            )
            equity_curve.append(self._equity_point(engine, clean_symbol, final_candle))

        return BacktestResult(
            trade_journal=engine.trade_journal(),
            equity_curve=tuple(equity_curve),
            metrics=self._metrics(engine.trade_journal(), equity_curve, self.config.starting_cash),
        )

    def _submit_signal(
        self,
        engine: PaperTradingEngine,
        signal: BacktestSignal,
        expected_symbol: str,
        expected_market: Market,
        candle: Candle,
    ) -> None:
        if signal.symbol.upper().strip() != expected_symbol or signal.market != expected_market:
            return
        engine.submit_order(
            PaperOrderRequest(
                symbol=expected_symbol,
                market=expected_market,
                side=OrderSide.BUY,
                quantity=signal.quantity,
                reference_price=candle.open,
                submitted_at=candle.timestamp,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                metadata=dict(signal.metadata),
            )
        )

    def _equity_point(
        self,
        engine: PaperTradingEngine,
        symbol: str,
        candle: Candle,
    ) -> EquityCurvePoint:
        snapshot = engine.snapshot(candle.timestamp, marks={symbol: candle.close})
        return EquityCurvePoint(
            timestamp=candle.timestamp,
            equity=snapshot.equity,
            cash=snapshot.cash,
            realized_pnl=snapshot.realized_pnl,
            unrealized_pnl=snapshot.unrealized_pnl,
        )

    def _metrics(
        self,
        journal: Sequence[PaperTradeJournalEntry],
        equity_curve: Sequence[EquityCurvePoint],
        starting_cash: float,
    ) -> dict[str, float | int]:
        closing_trades = [
            entry
            for entry in journal
            if entry.side == OrderSide.SELL and entry.status == PaperTradeStatus.CLOSED
        ]
        costs = sum(entry.costs for entry in journal)
        net_pnl = sum(entry.realized_pnl for entry in closing_trades)
        winning = sum(1 for entry in closing_trades if entry.realized_pnl > 0)
        losing = sum(1 for entry in closing_trades if entry.realized_pnl < 0)
        final_equity = equity_curve[-1].equity if equity_curve else starting_cash
        max_drawdown_pct = self._max_drawdown_pct(equity_curve)
        return {
            "entries": sum(
                1
                for entry in journal
                if entry.side == OrderSide.BUY and entry.status == PaperTradeStatus.OPENED
            ),
            "closed_trades": len(closing_trades),
            "blocked_entries": sum(
                1 for entry in journal if entry.status == PaperTradeStatus.BLOCKED
            ),
            "winning_trades": winning,
            "losing_trades": losing,
            "win_rate": winning / len(closing_trades) if closing_trades else 0.0,
            "net_pnl": net_pnl,
            "total_costs": costs,
            "final_equity": final_equity,
            "total_return_pct": (final_equity - starting_cash) / starting_cash,
            "max_drawdown_pct": max_drawdown_pct,
        }

    def _max_drawdown_pct(self, equity_curve: Sequence[EquityCurvePoint]) -> float:
        peak = None
        max_drawdown = 0.0
        for point in equity_curve:
            peak = point.equity if peak is None else max(peak, point.equity)
            if peak > 0:
                max_drawdown = min(max_drawdown, (point.equity - peak) / peak)
        return abs(max_drawdown)

    def _validated_candles(self, candles: Sequence[Candle]) -> list[Candle]:
        ordered = list(candles)
        if not ordered:
            return []
        for candle in ordered:
            if min(candle.open, candle.high, candle.low, candle.close) <= 0:
                raise ValueError("candle_prices_must_be_positive")
            if candle.high < max(candle.open, candle.close) or candle.low > min(
                candle.open, candle.close
            ):
                raise ValueError("candle_high_low_inconsistent")
        if ordered != sorted(ordered, key=lambda candle: candle.timestamp):
            raise ValueError("candles_must_be_sorted_ascending")
        timestamps = [candle.timestamp for candle in ordered]
        if len(timestamps) != len(set(timestamps)):
            raise ValueError("duplicate_candle_timestamps_not_allowed")
        return ordered
