from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.core.enums import Market, TradingMode
from app.intraday.costs import CostModel
from app.intraday.daily_report import DailyReviewEngine
from app.intraday.exit_manager import ExitManager
from app.intraday.kill_switch import KillSwitchManager
from app.intraday.market_data import DataQualityMonitor
from app.intraday.models import (
    Candle,
    Direction,
    FillStatus,
    JournalEntry,
    MarketDataSnapshot,
    MarketRegime,
    Signal,
    SignalDecision,
    VirtualPositionStatus,
)
from app.intraday.pipeline import IntradayShadowPipeline
from app.intraday.positions import VirtualPositionManager
from app.intraday.readiness import LiveReadinessEvaluator
from app.intraday.regime import MarketRegimeClassifier
from app.intraday.risk_manager import RiskManager, ShadowRiskState
from app.intraday.scoring import SignalScoringEngine
from app.intraday.shadow_execution import ShadowExecutionSimulator
from app.intraday.strategies import OpeningRangeBreakoutStrategy, VWAPTrendLongStrategy, VWAPTrendShortStrategy
from app.intraday.universe import UniverseFilter
from app.services import professional_intraday_shadow_service as professional_service_module
from app.services.professional_intraday_shadow_service import ProfessionalIntradayShadowService


def _candles(*, bearish: bool = False) -> tuple[Candle, ...]:
    start = datetime(2026, 5, 13, 9, 15, tzinfo=UTC)
    prices = [100, 101, 102, 103, 104] if not bearish else [104, 103, 102, 101, 100]
    rows = []
    for index, price in enumerate(prices):
        rows.append(
            Candle(
                timestamp=start + timedelta(minutes=index),
                open=price - 0.3,
                high=price + 0.5,
                low=price - 0.5,
                close=price,
                volume=1000 + index * 200,
            )
        )
    return tuple(rows)


def _snapshot(*, bearish: bool = False, price: float | None = None) -> MarketDataSnapshot:
    candles = _candles(bearish=bearish)
    last = price if price is not None else (100 if bearish else 104)
    return MarketDataSnapshot(
        market=Market.INDIA,
        symbol="RELIANCE",
        timestamp=datetime(2026, 5, 13, 9, 30, tzinfo=UTC),
        last_price=last,
        vwap=103.6 if not bearish else 100.4,
        volume=100000,
        previous_day_high=105,
        previous_day_low=95,
        opening_range_high_15m=103,
        opening_range_low_15m=99,
        opening_range_high_30m=104,
        opening_range_low_30m=98,
        atr=1.0,
        bid=last - 0.02,
        ask=last + 0.02,
        candles_1m=candles,
        candles_3m=candles,
        candles_5m=candles,
        index_trend=-0.004 if bearish else 0.004,
        sector_trend=-0.003 if bearish else 0.003,
        market_breadth=0.7,
        gap_pct=-0.006 if bearish else 0.006,
        source="TEST",
    )


def test_new_default_mode_is_shadow_live_and_live_orders_disabled() -> None:
    settings = Settings(_env_file=None)

    assert settings.trading_mode == TradingMode.SHADOW_LIVE
    assert settings.live_trading_enabled is False
    assert settings.live_orders_enabled is False


def test_market_regime_classification_bullish_and_bearish() -> None:
    classifier = MarketRegimeClassifier()

    assert classifier.classify(_snapshot()).regime == MarketRegime.STRONG_BULLISH
    assert classifier.classify(_snapshot(bearish=True)).regime == MarketRegime.STRONG_BEARISH


def test_data_quality_blocks_stale_or_missing_candles() -> None:
    monitor = DataQualityMonitor()
    stale = MarketDataSnapshot(
        market=Market.INDIA,
        symbol="RELIANCE",
        timestamp=datetime(2026, 5, 13, 9, 0, tzinfo=UTC),
        last_price=100,
        vwap=100,
        volume=100,
    )

    report = monitor.check(stale, now=datetime(2026, 5, 13, 9, 10, tzinfo=UTC))

    assert report.ok is False
    assert "stale_data" in report.reasons
    assert "missing_1m_candles" in report.reasons


def test_universe_filter_rejects_outside_liquid_universe() -> None:
    snapshot = _snapshot()
    outside = MarketDataSnapshot(**{**snapshot.__dict__, "symbol": "TINYCO"})

    decision = UniverseFilter().check(outside, DataQualityMonitor().check(outside))

    assert decision.allowed is False
    assert "symbol_not_in_nifty_liquid_universe" in decision.reasons


def test_vwap_long_signal_generation() -> None:
    snapshot = _snapshot()
    regime = MarketRegimeClassifier().classify(snapshot)

    signal = VWAPTrendLongStrategy().generate(snapshot, regime)

    assert signal is not None
    assert signal.direction == Direction.LONG
    assert signal.strategy_name == "VWAP_TREND_LONG"
    assert signal.stop_loss < signal.entry_price < signal.target_price


def test_vwap_short_signal_generation() -> None:
    snapshot = _snapshot(bearish=True)
    regime = MarketRegimeClassifier().classify(snapshot)

    signal = VWAPTrendShortStrategy().generate(snapshot, regime)

    assert signal is not None
    assert signal.direction == Direction.SHORT
    assert signal.target_price < signal.entry_price < signal.stop_loss


def test_opening_range_breakout_and_breakdown() -> None:
    bullish = _snapshot(price=104.5)
    bearish = _snapshot(bearish=True, price=98.5)

    long_signal = OpeningRangeBreakoutStrategy().generate(
        bullish, MarketRegimeClassifier().classify(bullish)
    )
    short_signal = OpeningRangeBreakoutStrategy().generate(
        bearish, MarketRegimeClassifier().classify(bearish)
    )

    assert long_signal is not None
    assert long_signal.direction == Direction.LONG
    assert short_signal is not None
    assert short_signal.direction == Direction.SHORT


def test_signal_scoring_valid_watch_and_reject() -> None:
    snapshot = _snapshot()
    signal = VWAPTrendLongStrategy().generate(snapshot, MarketRegimeClassifier().classify(snapshot))
    assert signal is not None

    scored = SignalScoringEngine().score(signal)
    weak = SignalScoringEngine().score(
        Signal.create(
            symbol="RELIANCE",
            market=Market.INDIA,
            direction=Direction.LONG,
            strategy_name="WEAK",
            regime_at_signal=MarketRegime.SIDEWAYS,
            entry_price=100,
            stop_loss=99,
            target_price=101,
            confidence_score=0.1,
            reason_codes=[],
            invalidation_rules=[],
            candle_snapshot={},
            market_snapshot={},
        )
    )

    assert scored.decision == SignalDecision.VALID
    assert weak.decision == SignalDecision.REJECTED


def test_risk_manager_quantity_and_reward_rejection() -> None:
    snapshot = _snapshot()
    signal = VWAPTrendLongStrategy().generate(snapshot, MarketRegimeClassifier().classify(snapshot))
    assert signal is not None
    scored = SignalScoringEngine().score(signal)
    quality = DataQualityMonitor().check(snapshot)

    approved = RiskManager().approve(scored, data_quality=quality)
    bad_signal = Signal.create(
        symbol="RELIANCE",
        market=Market.INDIA,
        direction=Direction.LONG,
        strategy_name="BAD_RR",
        regime_at_signal=MarketRegime.STRONG_BULLISH,
        entry_price=100,
        stop_loss=99,
        target_price=100.5,
        confidence_score=0.5,
        reason_codes=["price_above_vwap"],
        invalidation_rules=[],
        candle_snapshot={},
        market_snapshot={"spread_pct": 0.0},
    )
    rejected = RiskManager().approve(
        SignalScoringEngine().score(bad_signal),
        data_quality=quality,
    )

    assert approved.approved is True
    assert approved.quantity > 0
    assert rejected.approved is False
    assert "reward_risk_below_threshold" in rejected.rejection_reasons


def test_risk_manager_rejects_shorts_by_default() -> None:
    snapshot = _snapshot(bearish=True)
    signal = VWAPTrendShortStrategy().generate(snapshot, MarketRegimeClassifier().classify(snapshot))
    assert signal is not None

    rejected = RiskManager().approve(
        SignalScoringEngine().score(signal),
        data_quality=DataQualityMonitor().check(snapshot),
    )

    assert rejected.approved is False
    assert "shorts_disabled" in rejected.rejection_reasons


def test_kill_switch_daily_loss_and_consecutive_losses() -> None:
    manager = KillSwitchManager()
    state = ShadowRiskState(daily_realized_pnl=-6000, consecutive_losses=3)

    result = manager.evaluate(risk_state=state)

    assert result.triggered is True
    assert "daily_loss_limit_hit" in result.reasons
    assert "max_consecutive_losses_hit" in result.reasons


def test_shadow_execution_simulates_fill_and_missed_entry() -> None:
    snapshot = _snapshot()
    signal = VWAPTrendLongStrategy().generate(snapshot, MarketRegimeClassifier().classify(snapshot))
    assert signal is not None
    approval = RiskManager().approve(
        SignalScoringEngine().score(signal),
        data_quality=DataQualityMonitor().check(snapshot),
    )

    filled = ShadowExecutionSimulator().simulate(signal, approval, snapshot)
    moved = ShadowExecutionSimulator().simulate(
        signal,
        approval,
        MarketDataSnapshot(**{**snapshot.__dict__, "last_price": 110}),
    )

    assert filled.fill_status == FillStatus.FILLED
    assert filled.simulated_fill is not None
    assert filled.simulated_fill > signal.entry_price
    assert moved.fill_status == FillStatus.MISSED


def test_cost_calculation_includes_charges() -> None:
    costs = CostModel().calculate(buy_value=100000, sell_value=101000)

    assert costs.total > 0
    assert costs.stt > 0
    assert costs.gst > 0


def test_virtual_position_lifecycle_and_exit_rules() -> None:
    snapshot = _snapshot()
    signal = VWAPTrendLongStrategy().generate(snapshot, MarketRegimeClassifier().classify(snapshot))
    assert signal is not None
    approval = RiskManager().approve(
        SignalScoringEngine().score(signal),
        data_quality=DataQualityMonitor().check(snapshot),
    )
    order = ShadowExecutionSimulator().simulate(signal, approval, snapshot)
    manager = VirtualPositionManager()
    position = manager.open_position(signal, order)
    assert position is not None

    stop_snapshot = MarketDataSnapshot(**{**snapshot.__dict__, "last_price": signal.stop_loss})
    exit_decision = ExitManager().evaluate(
        position,
        stop_snapshot,
        current_regime=MarketRegime.STRONG_BULLISH,
    )
    closed = manager.close_position(
        position.position_id,
        exit_price=exit_decision.exit_price or signal.stop_loss,
        exit_reason=exit_decision.reason,
    )

    assert exit_decision.should_exit is True
    assert closed.status == VirtualPositionStatus.STOPPED_OUT
    assert closed.net_pnl < 0


def test_daily_report_expectancy_and_profit_factor() -> None:
    rows = [
        JournalEntry(
            timestamp=datetime(2026, 5, 13, 10, tzinfo=UTC),
            event_type="POSITION_EXITED",
            symbol="RELIANCE",
            direction="LONG",
            strategy="VWAP_TREND_LONG",
            regime="STRONG_BULLISH",
            gross_pnl=1200,
            net_pnl=1000,
            charges=200,
        ).model_dump(),
        JournalEntry(
            timestamp=datetime(2026, 5, 13, 11, tzinfo=UTC),
            event_type="POSITION_EXITED",
            symbol="TCS",
            direction="LONG",
            strategy="VWAP_TREND_LONG",
            regime="WEAK_BULLISH",
            gross_pnl=-500,
            net_pnl=-600,
            charges=100,
        ).model_dump(),
    ]

    report = DailyReviewEngine().generate(rows)

    assert report["trades_taken"] == 2
    assert report["profit_factor"] > 1
    assert report["expectancy"] == 200


def test_live_readiness_remains_blocked() -> None:
    result = LiveReadinessEvaluator().evaluate(
        shadow_sessions=29,
        valid_trades=99,
        expectancy=10,
        profit_factor=1.4,
        max_drawdown_pct=0.02,
        overfitting_warning=False,
        manual_approval=False,
    )

    assert result["live_readiness_status"] == "BLOCKED"
    assert "minimum_30_shadow_sessions_not_met" in result["reasons"]
    assert result["live_orders_enabled"] is False


def test_pipeline_is_shadow_only_and_never_places_broker_orders(tmp_path) -> None:
    pipeline = IntradayShadowPipeline(journal=None)
    pipeline.journal.root = tmp_path
    snapshot = _snapshot()

    result = pipeline.process_snapshot(snapshot)
    report = pipeline.today_report()

    assert result["orders_placed"] == 0
    assert result["shadow_only"] is True
    assert pipeline.can_place_live_orders is False
    assert report["live_readiness"]["live_readiness_status"] == "BLOCKED"


def test_professional_india_once_consumes_zerodha_quotes_without_live_orders(monkeypatch, tmp_path) -> None:
    class ZerodhaProviderStub:
        def __init__(self, settings: Settings) -> None:
            self.settings = settings

        def latest(self, symbol: str, market: Market) -> dict:
            return {
                "data": {
                    f"NSE:{symbol}": {
                        "instrument_token": 12345,
                        "last_price": 100.0,
                        "average_price": 99.8,
                        "volume": 100000,
                        "ohlc": {"open": 100.0, "high": 102.0, "low": 98.0, "close": 99.0},
                    }
                }
            }

        def historical_candles(
            self,
            *,
            instrument_token: int | str,
            interval: str,
            from_date: datetime,
            to_date: datetime,
        ) -> dict:
            return {
                "data": {
                    "candles": [
                        ["2026-05-13T09:15:00+0530", 99, 100, 98, 99.5, 1000],
                        ["2026-05-13T09:16:00+0530", 99.5, 100.5, 99, 100, 1200],
                        ["2026-05-13T09:17:00+0530", 100, 101, 99.5, 100.5, 1400],
                        ["2026-05-13T09:18:00+0530", 100.5, 101.5, 100, 101, 1800],
                    ]
                }
            }

    monkeypatch.setattr(professional_service_module, "ZerodhaDataProvider", ZerodhaProviderStub)
    service = ProfessionalIntradayShadowService(
        Settings(_env_file=None, shadow_india_symbols="reliance,RELIANCE,tcs")
    )
    service.pipeline.journal.root = tmp_path

    result = service.run_india_once()

    assert result["shadow_only"] is True
    assert result["orders_placed"] == 0
    assert result["symbols_requested"] == ["RELIANCE", "TCS"]
    assert result["symbols_processed"] == 2
    assert result["blocked"] == []
    assert all(row["orders_placed"] == 0 for row in result["results"])
