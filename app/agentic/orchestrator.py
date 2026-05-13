from __future__ import annotations

from app.agentic.agents import (
    BacktestValidationAgent,
    ComplianceSafetyAgent,
    DailyReportAgent,
    DriftDetectionAgent,
    ExecutionSimulationAgent,
    MarketContextAgent,
    PostTradeReviewAgent,
    RegimeReviewAgent,
    RiskAuditorAgent,
    SignalCriticAgent,
    StrategyImprovementAgent,
)
from app.agentic.config import AgenticConfig
from app.agentic.journal import AgentDecisionJournal, HumanApprovalQueue
from app.agentic.models import (
    AgentDecisionStatus,
    AgentRecommendation,
    AgentSeverity,
    AgenticReviewResult,
    ExecutionSimulationInput,
    GenericReviewInput,
    HumanApprovalRecord,
    MarketContextInput,
    RegimeReviewInput,
    RiskAuditorInput,
    SignalCriticInput,
)
from app.core.config import Settings, get_settings
from app.intraday.config import IntradayShadowConfig
from app.intraday.models import MarketDataSnapshot, RiskApproval, ScoredSignal, ShadowOrder
from app.intraday.regime import RegimeResult
from app.intraday.risk_manager import ShadowRiskState


class AgenticOrchestrator:
    """Coordinates review agents without giving them trading authority."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        config: AgenticConfig | None = None,
        journal: AgentDecisionJournal | None = None,
        approval_queue: HumanApprovalQueue | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.config = config or AgenticConfig.from_settings(self.settings)
        self.journal = journal or AgentDecisionJournal()
        self.approval_queue = approval_queue or HumanApprovalQueue()
        self.market_context = MarketContextAgent(config=self.config, journal=self.journal)
        self.regime_review = RegimeReviewAgent(config=self.config, journal=self.journal)
        self.signal_critic = SignalCriticAgent(config=self.config, journal=self.journal)
        self.risk_auditor = RiskAuditorAgent(config=self.config, journal=self.journal)
        self.execution_review = ExecutionSimulationAgent(config=self.config, journal=self.journal)
        self.post_trade = PostTradeReviewAgent(config=self.config, journal=self.journal)
        self.backtest_validation = BacktestValidationAgent(config=self.config, journal=self.journal)
        self.drift_detection = DriftDetectionAgent(config=self.config, journal=self.journal)
        self.strategy_improvement = StrategyImprovementAgent(config=self.config, journal=self.journal)
        self.compliance_safety = ComplianceSafetyAgent(config=self.config, journal=self.journal)
        self.daily_report = DailyReportAgent(config=self.config, journal=self.journal)

    def pre_market_review(self) -> AgenticReviewResult:
        if not self.config.enabled:
            return AgenticReviewResult()
        result = AgenticReviewResult()
        compliance_output, compliance_record = self.compliance_safety.review(
            GenericReviewInput(
                payload={
                    "trading_mode": self.settings.trading_mode.value,
                    "live_trading_enabled": self.settings.live_trading_enabled,
                    "live_orders_enabled": self.settings.live_orders_enabled,
                    "kill_switch": self.settings.kill_switch,
                }
            )
        )
        result.records.append(compliance_record)
        if _record_blocks(compliance_record):
            result.block = True
            result.allowed = False
            result.warnings.extend(compliance_record.parsed_output.get("reasonCodes", ["compliance_block"]))
        market_output, market_record = self.market_context.review(MarketContextInput())
        result.records.append(market_record)
        if market_output is not None and str(market_output.severity) == AgentSeverity.HIGH.value:
            result.block = True
            result.allowed = False
            result.warnings.extend(market_output.reason_codes)
        drift_output, drift_record = self.drift_detection.review(GenericReviewInput(payload={}))
        result.records.append(drift_record)
        if drift_output is not None and drift_output.drift_detected:
            result.confidence_multiplier = min(result.confidence_multiplier, 0.8)
            result.warnings.extend(drift_output.reason_codes)
        return result

    def review_regime(
        self,
        snapshot: MarketDataSnapshot,
        regime: RegimeResult,
    ) -> AgenticReviewResult:
        if not self.config.enabled:
            return AgenticReviewResult()
        output, record = self.regime_review.review(
            RegimeReviewInput(
                deterministicRegime=regime.regime.value,
                marketSnapshot=snapshot.raw or {
                    "last_price": snapshot.last_price,
                    "vwap": snapshot.vwap,
                    "volume": snapshot.volume,
                },
                sectorStrength=snapshot.sector_trend,
                breadth=snapshot.market_breadth,
                volatility=snapshot.atr,
            )
        )
        result = _result_from_record(record)
        if output is not None and not output.agrees_with_regime:
            result.confidence_multiplier = min(result.confidence_multiplier, 0.8)
        return result

    def review_signal(
        self,
        scored: ScoredSignal,
        *,
        state: ShadowRiskState,
    ) -> AgenticReviewResult:
        if not self.config.enabled:
            return AgenticReviewResult()
        signal = scored.signal
        output, record = self.signal_critic.review(
            SignalCriticInput(
                signalId=signal.signal_id,
                symbol=signal.symbol,
                direction=signal.direction.value,
                strategyName=signal.strategy_name,
                marketRegime=signal.regime_at_signal.value,
                entryPrice=signal.entry_price,
                stopLoss=signal.stop_loss,
                targetPrice=signal.target_price,
                riskRewardRatio=signal.risk_reward_ratio,
                confidenceScore=signal.confidence_score,
                reasonCodes=signal.reason_codes,
                candleSnapshot=signal.candle_snapshot,
                marketSnapshot=signal.market_snapshot,
                sectorSnapshot={},
                currentOpenPositions=len(state.open_positions),
                dailyPnl=state.daily_realized_pnl,
                tradesTakenToday=state.trades_today,
            )
        )
        result = _result_from_record(record)
        if output is not None:
            result.risk_multiplier = min(result.risk_multiplier, output.risk_multiplier_suggestion)
        return result

    def review_risk(
        self,
        scored: ScoredSignal,
        approval: RiskApproval,
        *,
        state: ShadowRiskState,
        intraday_config: IntradayShadowConfig,
    ) -> AgenticReviewResult:
        if not self.config.enabled:
            return AgenticReviewResult()
        signal = scored.signal
        stop_distance = abs(signal.entry_price - signal.stop_loss)
        output, record = self.risk_auditor.review(
            RiskAuditorInput(
                signalId=signal.signal_id,
                symbol=signal.symbol,
                strategyName=signal.strategy_name,
                capital=intraday_config.capital,
                quantity=approval.quantity,
                entryPrice=signal.entry_price,
                stopLoss=signal.stop_loss,
                targetPrice=signal.target_price,
                stopDistance=stop_distance,
                riskAmount=approval.risk_amount,
                riskRewardRatio=signal.risk_reward_ratio,
                dailyPnl=state.daily_realized_pnl,
                weeklyPnl=state.weekly_realized_pnl,
                openPositions=len(state.open_positions),
                consecutiveLosses=state.consecutive_losses,
                maxTradesPerDay=intraday_config.max_trades_per_day,
                tradesTakenToday=state.trades_today,
            )
        )
        result = _result_from_record(record)
        if output is not None and output.risk_violations:
            result.warnings.extend(output.risk_violations)
        return result

    def review_execution(
        self,
        *,
        scored: ScoredSignal,
        order: ShadowOrder,
        snapshot: MarketDataSnapshot,
    ) -> AgenticReviewResult:
        if not self.config.enabled:
            return AgenticReviewResult()
        output, record = self.execution_review.review(
            ExecutionSimulationInput(
                signalId=scored.signal.signal_id,
                shadowOrderId=order.shadow_order_id,
                expectedEntry=order.expected_entry,
                simulatedFill=order.simulated_fill,
                spread=order.spread,
                slippage=order.slippage,
                latencyMs=order.latency_ms,
                volume=snapshot.volume,
                volatility=snapshot.atr,
                fillStatus=order.fill_status.value,
            )
        )
        result = _result_from_record(record)
        if output is not None and str(output.recommended_action) == AgentRecommendation.MARK_MISSED.value:
            result.warnings.append("execution_agent_marked_missed_entry")
        return result

    def end_of_day_review(self, report: dict) -> AgenticReviewResult:
        if not self.config.enabled:
            return AgenticReviewResult()
        result = AgenticReviewResult()
        for output, record in (
            self.daily_report.review(GenericReviewInput(payload=report)),
            self.strategy_improvement.review(GenericReviewInput(payload=report)),
            self.drift_detection.review(GenericReviewInput(payload=report)),
        ):
            result.records.append(record)
            if _record_blocks(record):
                result.block = True
                result.allowed = False
            if output is not None and hasattr(output, "recommendations"):
                for recommendation in output.recommendations:
                    if getattr(recommendation, "requires_backtest", True):
                        self.approval_queue.enqueue(
                            HumanApprovalRecord(
                                changeType="STRATEGY_RESEARCH_RECOMMENDATION",
                                proposedByAgent=record.agent_name,
                                evidence=recommendation.model_dump(mode="json", by_alias=True),
                                riskImpact=str(recommendation.risk_level),
                            )
                        )
        return result

    def validate_strategy_change(self, payload: dict) -> AgenticReviewResult:
        if not self.config.enabled:
            return AgenticReviewResult(allowed=False, block=True, warnings=["agentic_review_disabled"])
        _, record = self.backtest_validation.review(GenericReviewInput(payload=payload))
        return _result_from_record(record)


def _result_from_record(record) -> AgenticReviewResult:
    result = AgenticReviewResult(records=[record])
    if record.schema_validation_status != AgentDecisionStatus.VALID:
        result.allowed = False
        result.block = True
        result.warnings.append(record.error or "agent_decision_invalid")
        return result
    parsed = record.parsed_output
    if record.final_action_taken == "BLOCK":
        result.allowed = False
        result.block = True
    if record.severity == AgentSeverity.MEDIUM:
        result.confidence_multiplier = 0.8
    if record.severity == AgentSeverity.HIGH:
        result.allowed = False
        result.block = True
    result.warnings.extend(parsed.get("reasonCodes", []))
    return result


def _record_blocks(record) -> bool:
    return record.final_action_taken == "BLOCK" or record.severity == AgentSeverity.HIGH
