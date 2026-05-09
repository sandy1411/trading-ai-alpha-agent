from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.backtesting import BacktestConfig, BacktestSignal, Candle, HistoricalBacktestEngine
from app.core.enums import Market
from app.paper import CostModel, PaperRiskLimits
from app.paper.models import PaperExitReason


def _candles() -> list[Candle]:
    start = datetime(2026, 5, 4, 4, 0, tzinfo=UTC)
    return [
        Candle(start, open=100, high=101, low=99, close=100, volume=10_000),
        Candle(start + timedelta(minutes=5), open=101, high=106, low=100, close=105, volume=12_000),
        Candle(start + timedelta(minutes=10), open=106, high=108, low=103, close=104, volume=11_000),
    ]


def test_backtest_enters_on_next_bar_open_and_applies_costs() -> None:
    engine = HistoricalBacktestEngine(
        BacktestConfig(
            starting_cash=10_000,
            cost_model=CostModel(brokerage_pct=0.01, taxes_pct=0, brokerage_flat=0, slippage_bps=100),
            risk_limits=PaperRiskLimits(max_trades_per_day=5, max_daily_loss=5_000),
            close_open_positions_on_end=False,
        )
    )

    def strategy(history: tuple[Candle, ...]) -> BacktestSignal | None:
        if len(history) == 1 and history[-1].close == 100:
            return BacktestSignal("ABC", Market.INDIA, quantity=10, stop_loss=95, take_profit=110)
        return None

    result = engine.run_single_symbol(
        symbol="ABC",
        market=Market.INDIA,
        candles=_candles(),
        strategy=strategy,
    )

    entry = result.trade_journal[0]
    assert entry.requested_price == 101
    assert entry.execution_price == pytest.approx(102.01)
    assert entry.costs == pytest.approx(10.201)
    assert result.metrics["entries"] == 1


def test_backtest_handles_target_exit() -> None:
    engine = HistoricalBacktestEngine(
        BacktestConfig(
            starting_cash=10_000,
            cost_model=CostModel(brokerage_pct=0, taxes_pct=0, brokerage_flat=0, slippage_bps=0),
            risk_limits=PaperRiskLimits(max_trades_per_day=5, max_daily_loss=5_000),
            close_open_positions_on_end=False,
        )
    )

    def strategy(history: tuple[Candle, ...]) -> BacktestSignal | None:
        if len(history) == 1:
            return BacktestSignal("ABC", Market.INDIA, quantity=10, stop_loss=95, take_profit=105)
        return None

    result = engine.run_single_symbol(
        symbol="ABC",
        market=Market.INDIA,
        candles=_candles(),
        strategy=strategy,
    )

    exit_entry = result.trade_journal[-1]
    assert exit_entry.exit_reason == PaperExitReason.PROFIT_TARGET
    assert exit_entry.realized_pnl == 40
    assert result.metrics["closed_trades"] == 1
    assert result.metrics["winning_trades"] == 1


def test_backtest_strategy_receives_only_prior_candles_to_avoid_lookahead() -> None:
    seen_last_timestamps: list[datetime] = []
    candles = _candles()
    engine = HistoricalBacktestEngine(
        BacktestConfig(
            starting_cash=10_000,
            cost_model=CostModel(brokerage_pct=0, taxes_pct=0, brokerage_flat=0, slippage_bps=0),
            close_open_positions_on_end=False,
        )
    )

    def strategy(history: tuple[Candle, ...]) -> BacktestSignal | None:
        seen_last_timestamps.append(history[-1].timestamp)
        assert history[-1].timestamp < candles[len(history)].timestamp
        return None

    engine.run_single_symbol(
        symbol="ABC",
        market=Market.INDIA,
        candles=candles,
        strategy=strategy,
    )

    assert seen_last_timestamps == [candles[0].timestamp, candles[1].timestamp]


def test_unsorted_candles_are_rejected() -> None:
    engine = HistoricalBacktestEngine()
    candles = list(reversed(_candles()))

    with pytest.raises(ValueError, match="candles_must_be_sorted_ascending"):
        engine.run_single_symbol(
            symbol="ABC",
            market=Market.INDIA,
            candles=candles,
            strategy=lambda history: None,
        )
