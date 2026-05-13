from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable

from app.intraday.config import IntradayShadowConfig
from app.intraday.daily_report import DailyReviewEngine
from app.intraday.journal import TradeJournal
from app.intraday.kill_switch import KillSwitchManager
from app.intraday.market_data import DataQualityMonitor
from app.intraday.models import FillStatus, JournalEntry, MarketDataSnapshot, SignalDecision
from app.intraday.positions import VirtualPositionManager
from app.intraday.readiness import LiveReadinessEvaluator
from app.intraday.regime import MarketRegimeClassifier
from app.intraday.risk_manager import RiskManager, ShadowRiskState
from app.intraday.scoring import SignalScoringEngine
from app.intraday.shadow_execution import ShadowExecutionSimulator
from app.intraday.strategies import (
    IntradayStrategy,
    OpeningRangeBreakoutStrategy,
    VWAPTrendLongStrategy,
    VWAPTrendShortStrategy,
)
from app.intraday.universe import UniverseFilter


class IntradayShadowPipeline:
    """Shadow-only professional intraday decision pipeline."""

    can_place_live_orders = False

    def __init__(
        self,
        *,
        config: IntradayShadowConfig | None = None,
        strategies: Iterable[IntradayStrategy] | None = None,
        journal: TradeJournal | None = None,
    ) -> None:
        self.config = config or IntradayShadowConfig.from_settings()
        self.quality = DataQualityMonitor(self.config)
        self.regime = MarketRegimeClassifier(self.config)
        self.universe = UniverseFilter(self.config)
        self.scoring = SignalScoringEngine(self.config)
        self.risk = RiskManager(self.config)
        self.execution = ShadowExecutionSimulator(self.config)
        self.positions = VirtualPositionManager()
        self.kill_switch = KillSwitchManager(self.config)
        self.daily_review = DailyReviewEngine()
        self.readiness = LiveReadinessEvaluator(self.config)
        self.journal = journal or TradeJournal()
        self.strategies = list(
            strategies
            or [VWAPTrendLongStrategy(), VWAPTrendShortStrategy(), OpeningRangeBreakoutStrategy()]
        )

    def process_snapshot(
        self,
        snapshot: MarketDataSnapshot,
        *,
        risk_state: ShadowRiskState | None = None,
    ) -> dict[str, object]:
        state = risk_state or ShadowRiskState(open_positions=list(self.positions.positions.values()))
        quality = self.quality.check(snapshot)
        regime = self.regime.classify(snapshot)
        kill = self.kill_switch.evaluate(risk_state=state, data_quality=quality)
        universe = self.universe.check(snapshot, quality)
        result: dict[str, object] = {
            "symbol": snapshot.symbol,
            "quality": {"ok": quality.ok, "reasons": quality.reasons, "metrics": quality.metrics},
            "regime": regime.regime.value,
            "regime_reasons": regime.reasons,
            "universe_allowed": universe.allowed,
            "universe_reasons": universe.reasons,
            "kill_switch": {"triggered": kill.triggered, "reasons": kill.reasons},
            "signals": [],
            "orders": [],
            "positions": [],
            "orders_placed": 0,
            "shadow_only": True,
        }
        if kill.triggered or not universe.allowed:
            self._journal(
                JournalEntry(
                    timestamp=snapshot.timestamp,
                    event_type="DATA_OR_UNIVERSE_BLOCK",
                    symbol=snapshot.symbol,
                    rejection_reason=";".join([*kill.reasons, *universe.reasons]),
                    market_snapshot={"regime": regime.regime.value, **quality.metrics},
                )
            )
            return result

        for strategy in self.strategies:
            signal = strategy.generate(snapshot, regime)
            if signal is None:
                continue
            scored = self.scoring.score(signal)
            result["signals"].append(
                {
                    "signal_id": signal.signal_id,
                    "strategy": signal.strategy_name,
                    "direction": signal.direction.value,
                    "score": scored.score,
                    "decision": scored.decision.value,
                    "reasons": scored.reasons,
                }
            )
            if scored.decision != SignalDecision.VALID:
                self._journal(
                    JournalEntry(
                        timestamp=signal.timestamp,
                        event_type="SIGNAL_REJECTED",
                        symbol=signal.symbol,
                        direction=signal.direction.value,
                        strategy=signal.strategy_name,
                        regime=signal.regime_at_signal.value,
                        signal_score=scored.score,
                        reason_codes=scored.reasons,
                        rejection_reason=scored.decision.value,
                        entry_price=signal.entry_price,
                        stop_loss=signal.stop_loss,
                        target=signal.target_price,
                        risk_reward=signal.risk_reward_ratio,
                        market_snapshot=signal.market_snapshot,
                        candle_snapshot=signal.candle_snapshot,
                    )
                )
                continue
            approval = self.risk.approve(scored, data_quality=quality, state=state, current_regime=regime.regime)
            if not approval.approved:
                self._journal(
                    JournalEntry(
                        timestamp=signal.timestamp,
                        event_type="SIGNAL_REJECTED",
                        symbol=signal.symbol,
                        direction=signal.direction.value,
                        strategy=signal.strategy_name,
                        regime=signal.regime_at_signal.value,
                        signal_score=scored.score,
                        reason_codes=scored.reasons,
                        rejection_reason=";".join(approval.rejection_reasons),
                        entry_price=signal.entry_price,
                        stop_loss=signal.stop_loss,
                        target=signal.target_price,
                        risk_amount=approval.risk_amount,
                        risk_reward=signal.risk_reward_ratio,
                        market_snapshot=signal.market_snapshot,
                        candle_snapshot=signal.candle_snapshot,
                    )
                )
                continue
            self._journal(
                JournalEntry(
                    timestamp=signal.timestamp,
                    event_type="SIGNAL_ACCEPTED",
                    symbol=signal.symbol,
                    direction=signal.direction.value,
                    strategy=signal.strategy_name,
                    regime=signal.regime_at_signal.value,
                    signal_score=scored.score,
                    reason_codes=scored.reasons,
                    entry_price=signal.entry_price,
                    stop_loss=signal.stop_loss,
                    target=signal.target_price,
                    quantity=approval.quantity,
                    risk_amount=approval.risk_amount,
                    risk_reward=signal.risk_reward_ratio,
                    market_snapshot=signal.market_snapshot,
                    candle_snapshot=signal.candle_snapshot,
                )
            )
            order = self.execution.simulate(signal, approval, snapshot)
            result["orders"].append(
                {
                    "shadow_order_id": order.shadow_order_id,
                    "fill_status": order.fill_status.value,
                    "simulated_fill": order.simulated_fill,
                    "rejection_reason": order.rejection_reason,
                }
            )
            self._journal(
                JournalEntry(
                    timestamp=order.timestamp,
                    event_type="SHADOW_ORDER_FILLED" if order.fill_status == FillStatus.FILLED else "SHADOW_ORDER_REJECTED",
                    symbol=order.symbol,
                    direction=order.direction.value,
                    strategy=signal.strategy_name,
                    regime=signal.regime_at_signal.value,
                    signal_score=scored.score,
                    reason_codes=scored.reasons,
                    rejection_reason=order.rejection_reason,
                    entry_price=signal.entry_price,
                    stop_loss=signal.stop_loss,
                    target=signal.target_price,
                    quantity=order.quantity,
                    risk_amount=approval.risk_amount,
                    risk_reward=signal.risk_reward_ratio,
                    simulated_fill_price=order.simulated_fill,
                    slippage=order.slippage,
                    market_snapshot=signal.market_snapshot,
                    candle_snapshot=signal.candle_snapshot,
                )
            )
            position = self.positions.open_position(signal, order)
            if position is not None:
                result["positions"].append({"position_id": position.position_id, "symbol": position.symbol})
        return result

    def today_report(self) -> dict:
        rows = self.journal.read_day()
        report = self.daily_review.generate(rows)
        readiness = self.readiness.evaluate(
            shadow_sessions=0,
            valid_trades=report["trades_taken"],
            expectancy=report["expectancy"],
            profit_factor=report["profit_factor"],
            max_drawdown_pct=0.0,
        )
        return {**report, "live_readiness": readiness, "journal_rows": len(rows)}

    def _journal(self, entry: JournalEntry) -> None:
        self.journal.append(entry)


def empty_professional_shadow_status() -> dict[str, object]:
    config = IntradayShadowConfig.from_settings()
    readiness = LiveReadinessEvaluator(config).evaluate(
        shadow_sessions=0,
        valid_trades=0,
        expectancy=0,
        profit_factor=0,
        max_drawdown_pct=0,
    )
    return {
        "mode": "PROFESSIONAL_INTRADAY_SHADOW",
        "shadow_only": True,
        "orders_placed": 0,
        "live_readiness": readiness,
        "generated_at": datetime.now(UTC).isoformat(),
    }

