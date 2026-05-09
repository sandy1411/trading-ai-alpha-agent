from __future__ import annotations

from datetime import UTC, datetime

from app.core.enums import Market, OrderSide
from app.paper import CostModel, PaperRiskLimits, PaperTradingEngine
from app.paper.models import PaperBlockReason, PaperExitReason, PaperOrderRequest


def test_paper_engine_applies_slippage_and_costs_on_entry_and_exit() -> None:
    engine = PaperTradingEngine(
        starting_cash=10_000,
        cost_model=CostModel(brokerage_pct=0.01, taxes_pct=0.005, brokerage_flat=2, slippage_bps=100),
    )

    entry = engine.submit_order(
        PaperOrderRequest(
            symbol="ABC",
            market=Market.INDIA,
            side=OrderSide.BUY,
            quantity=10,
            reference_price=100,
            submitted_at=datetime(2026, 5, 4, 4, 0, tzinfo=UTC),
            stop_loss=90,
            take_profit=120,
        )
    )
    exit_result = engine.close_open_position(
        "ABC",
        market=Market.INDIA,
        reference_price=110,
        timestamp=datetime(2026, 5, 4, 5, 0, tzinfo=UTC),
    )

    assert entry.accepted is True
    assert entry.journal_entry.execution_price == 101
    assert entry.journal_entry.costs == 17.15
    assert exit_result.accepted is True
    assert exit_result.journal_entry.execution_price == 108.9
    assert round(exit_result.journal_entry.costs, 2) == 18.34
    assert round(exit_result.journal_entry.realized_pnl, 2) == 43.51
    assert round(engine.total_costs, 2) == 35.48


def test_stop_loss_is_conservative_when_stop_and_target_are_both_inside_bar() -> None:
    engine = PaperTradingEngine(
        starting_cash=10_000,
        cost_model=CostModel(brokerage_pct=0, taxes_pct=0, brokerage_flat=0, slippage_bps=0),
    )
    engine.submit_order(
        PaperOrderRequest(
            symbol="ABC",
            market=Market.INDIA,
            side=OrderSide.BUY,
            quantity=10,
            reference_price=100,
            submitted_at=datetime(2026, 5, 4, 4, 0, tzinfo=UTC),
            stop_loss=95,
            take_profit=110,
        )
    )

    result = engine.evaluate_exit(
        "ABC",
        market=Market.INDIA,
        timestamp=datetime(2026, 5, 4, 4, 5, tzinfo=UTC),
        low=94,
        high=112,
    )

    assert result is not None
    assert result.accepted is True
    assert result.journal_entry.exit_reason == PaperExitReason.STOP_LOSS
    assert result.journal_entry.realized_pnl == -50


def test_daily_loss_limit_blocks_new_paper_entries() -> None:
    engine = PaperTradingEngine(
        starting_cash=10_000,
        cost_model=CostModel(brokerage_pct=0, taxes_pct=0, brokerage_flat=0, slippage_bps=0),
        risk_limits=PaperRiskLimits(max_daily_loss=100, max_trades_per_day=10),
    )
    ts = datetime(2026, 5, 4, 4, 0, tzinfo=UTC)
    engine.submit_order(
        PaperOrderRequest(
            symbol="LOSS",
            market=Market.INDIA,
            side=OrderSide.BUY,
            quantity=10,
            reference_price=100,
            submitted_at=ts,
            stop_loss=80,
        )
    )
    engine.close_open_position(
        "LOSS",
        market=Market.INDIA,
        reference_price=80,
        timestamp=datetime(2026, 5, 4, 4, 10, tzinfo=UTC),
    )

    blocked = engine.submit_order(
        PaperOrderRequest(
            symbol="NEXT",
            market=Market.INDIA,
            side=OrderSide.BUY,
            quantity=1,
            reference_price=100,
            submitted_at=datetime(2026, 5, 4, 4, 20, tzinfo=UTC),
            stop_loss=90,
        )
    )

    assert blocked.accepted is False
    assert blocked.journal_entry.block_reason == PaperBlockReason.DAILY_LOSS_LIMIT


def test_max_trades_per_day_blocks_new_paper_entries() -> None:
    engine = PaperTradingEngine(
        starting_cash=10_000,
        cost_model=CostModel(brokerage_pct=0, taxes_pct=0, brokerage_flat=0, slippage_bps=0),
        risk_limits=PaperRiskLimits(max_trades_per_day=1, max_daily_loss=1_000),
    )
    ts = datetime(2026, 5, 4, 4, 0, tzinfo=UTC)
    engine.submit_order(
        PaperOrderRequest(
            symbol="ONE",
            market=Market.INDIA,
            side=OrderSide.BUY,
            quantity=1,
            reference_price=100,
            submitted_at=ts,
            stop_loss=90,
        )
    )
    engine.close_open_position(
        "ONE",
        market=Market.INDIA,
        reference_price=101,
        timestamp=datetime(2026, 5, 4, 4, 5, tzinfo=UTC),
    )

    blocked = engine.submit_order(
        PaperOrderRequest(
            symbol="TWO",
            market=Market.INDIA,
            side=OrderSide.BUY,
            quantity=1,
            reference_price=100,
            submitted_at=datetime(2026, 5, 4, 4, 10, tzinfo=UTC),
            stop_loss=90,
        )
    )

    assert blocked.accepted is False
    assert blocked.journal_entry.block_reason == PaperBlockReason.MAX_TRADES_PER_DAY
