from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AgentVerdict(StrEnum):
    APPROVE = "APPROVE"
    WARN = "WARN"
    REJECT = "REJECT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class AgentRecommendation(StrEnum):
    ALLOW = "ALLOW"
    REDUCE_CONFIDENCE = "REDUCE_CONFIDENCE"
    BLOCK = "BLOCK"
    WAIT_FOR_PULLBACK = "WAIT_FOR_PULLBACK"
    REDUCE_SIZE = "REDUCE_SIZE"
    REVIEW_ONLY = "REVIEW_ONLY"
    MARK_MISSED = "MARK_MISSED"
    REQUIRE_BACKTEST = "REQUIRE_BACKTEST"
    DISABLE_STRATEGY_TEMPORARILY = "DISABLE_STRATEGY_TEMPORARILY"
    INCREASE_SLIPPAGE_MODEL = "INCREASE_SLIPPAGE_MODEL"


class AgentDecisionStatus(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


class MarketBias(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    UNCERTAIN = "UNCERTAIN"


class VolatilityState(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    PANIC = "PANIC"


class TradeBias(StrEnum):
    LONG_ONLY = "LONG_ONLY"
    SHORT_ONLY = "SHORT_ONLY"
    BOTH_ALLOWED = "BOTH_ALLOWED"
    NO_TRADE = "NO_TRADE"


class TradeQuality(StrEnum):
    GOOD_TRADE_GOOD_OUTCOME = "GOOD_TRADE_GOOD_OUTCOME"
    GOOD_TRADE_BAD_OUTCOME = "GOOD_TRADE_BAD_OUTCOME"
    BAD_TRADE_GOOD_OUTCOME = "BAD_TRADE_GOOD_OUTCOME"
    BAD_TRADE_BAD_OUTCOME = "BAD_TRADE_BAD_OUTCOME"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class AgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, use_enum_values=True)


class AgentBaseOutput(AgentModel):
    agent_name: str = Field(alias="agentName")
    verdict: AgentVerdict
    severity: AgentSeverity
    confidence: float = Field(ge=0, le=1)
    reason_codes: list[str] = Field(default_factory=list, alias="reasonCodes")
    explanation: str = ""
    recommended_action: AgentRecommendation = Field(alias="recommendedAction")
    audit_tags: list[str] = Field(default_factory=list, alias="auditTags")


class SignalCriticInput(AgentModel):
    signal_id: str = Field(alias="signalId")
    symbol: str
    direction: str
    strategy_name: str = Field(alias="strategyName")
    market_regime: str = Field(alias="marketRegime")
    entry_price: float = Field(alias="entryPrice")
    stop_loss: float = Field(alias="stopLoss")
    target_price: float = Field(alias="targetPrice")
    risk_reward_ratio: float = Field(alias="riskRewardRatio")
    confidence_score: float = Field(alias="confidenceScore")
    reason_codes: list[str] = Field(default_factory=list, alias="reasonCodes")
    candle_snapshot: dict[str, Any] = Field(default_factory=dict, alias="candleSnapshot")
    market_snapshot: dict[str, Any] = Field(default_factory=dict, alias="marketSnapshot")
    sector_snapshot: dict[str, Any] = Field(default_factory=dict, alias="sectorSnapshot")
    current_open_positions: int = Field(default=0, alias="currentOpenPositions")
    daily_pnl: float = Field(default=0, alias="dailyPnl")
    trades_taken_today: int = Field(default=0, alias="tradesTakenToday")


class SignalCriticOutput(AgentBaseOutput):
    signal_id: str = Field(alias="signalId")
    risk_multiplier_suggestion: float = Field(default=1.0, ge=0, le=1, alias="riskMultiplierSuggestion")


class RiskAuditorInput(AgentModel):
    signal_id: str = Field(alias="signalId")
    symbol: str
    strategy_name: str = Field(alias="strategyName")
    capital: float
    quantity: int
    entry_price: float = Field(alias="entryPrice")
    stop_loss: float = Field(alias="stopLoss")
    target_price: float = Field(alias="targetPrice")
    stop_distance: float = Field(alias="stopDistance")
    risk_amount: float = Field(alias="riskAmount")
    risk_reward_ratio: float = Field(alias="riskRewardRatio")
    daily_pnl: float = Field(default=0, alias="dailyPnl")
    weekly_pnl: float = Field(default=0, alias="weeklyPnl")
    open_positions: int = Field(default=0, alias="openPositions")
    consecutive_losses: int = Field(default=0, alias="consecutiveLosses")
    max_trades_per_day: int = Field(alias="maxTradesPerDay")
    trades_taken_today: int = Field(default=0, alias="tradesTakenToday")


class RiskAuditorOutput(AgentBaseOutput):
    risk_violations: list[str] = Field(default_factory=list, alias="riskViolations")


class MarketContextInput(AgentModel):
    current_time: datetime = Field(default_factory=lambda: datetime.now(UTC), alias="currentTime")
    nifty_snapshot: dict[str, Any] = Field(default_factory=dict, alias="niftySnapshot")
    bank_nifty_snapshot: dict[str, Any] = Field(default_factory=dict, alias="bankNiftySnapshot")
    sector_snapshots: dict[str, Any] = Field(default_factory=dict, alias="sectorSnapshots")
    india_vix: float | None = Field(default=None, alias="indiaVix")
    opening_gap: float | None = Field(default=None, alias="openingGap")
    previous_day_levels: dict[str, Any] = Field(default_factory=dict, alias="previousDayLevels")
    breadth: float | None = None
    volatility_state: str | None = Field(default=None, alias="volatilityState")


class MarketContextOutput(AgentBaseOutput):
    market_bias: MarketBias = Field(alias="marketBias")
    volatility_state: VolatilityState = Field(alias="volatilityState")
    recommended_trade_bias: TradeBias = Field(alias="recommendedTradeBias")
    risk_multiplier_suggestion: float = Field(default=1.0, ge=0, le=1, alias="riskMultiplierSuggestion")
    avoid_time_windows: list[str] = Field(default_factory=list, alias="avoidTimeWindows")
    key_warnings: list[str] = Field(default_factory=list, alias="keyWarnings")


class RegimeReviewInput(AgentModel):
    deterministic_regime: str = Field(alias="deterministicRegime")
    market_snapshot: dict[str, Any] = Field(default_factory=dict, alias="marketSnapshot")
    index_vwap_state: str | None = Field(default=None, alias="indexVwapState")
    opening_range_state: str | None = Field(default=None, alias="openingRangeState")
    sector_strength: float | None = Field(default=None, alias="sectorStrength")
    breadth: float | None = None
    volatility: float | None = None


class RegimeReviewOutput(AgentBaseOutput):
    agrees_with_regime: bool = Field(alias="agreesWithRegime")
    suggested_regime: str = Field(alias="suggestedRegime")


class ExecutionSimulationInput(AgentModel):
    signal_id: str = Field(alias="signalId")
    shadow_order_id: str = Field(alias="shadowOrderId")
    expected_entry: float = Field(alias="expectedEntry")
    simulated_fill: float | None = Field(alias="simulatedFill")
    spread: float
    slippage: float
    latency_ms: int = Field(alias="latencyMs")
    volume: float
    volatility: float | None = None
    fill_status: str = Field(alias="fillStatus")


class ExecutionSimulationOutput(AgentBaseOutput):
    execution_quality_score: float = Field(default=1.0, ge=0, le=1, alias="executionQualityScore")


class PostTradeReviewInput(AgentModel):
    trade_id: str = Field(alias="tradeId")
    symbol: str
    strategy_name: str = Field(alias="strategyName")
    entry_price: float = Field(alias="entryPrice")
    exit_price: float = Field(alias="exitPrice")
    stop_loss: float = Field(alias="stopLoss")
    target_price: float = Field(alias="targetPrice")
    net_pnl: float = Field(alias="netPnl")
    rules_followed: bool = Field(default=True, alias="rulesFollowed")
    max_favorable_excursion: float = Field(default=0, alias="maxFavorableExcursion")
    max_adverse_excursion: float = Field(default=0, alias="maxAdverseExcursion")


class PostTradeReviewOutput(AgentModel):
    agent_name: str = Field(alias="agentName")
    trade_id: str = Field(alias="tradeId")
    trade_quality: TradeQuality = Field(alias="tradeQuality")
    mistakes: list[str] = Field(default_factory=list)
    what_worked: list[str] = Field(default_factory=list, alias="whatWorked")
    what_failed: list[str] = Field(default_factory=list, alias="whatFailed")
    recommendations: list[str] = Field(default_factory=list)
    should_affect_strategy: bool = Field(alias="shouldAffectStrategy")
    requires_backtest: bool = Field(alias="requiresBacktest")
    confidence: float = Field(default=0.0, ge=0, le=1)


class StrategyRecommendation(AgentModel):
    description: str
    expected_impact: str = Field(alias="expectedImpact")
    evidence: list[str] = Field(default_factory=list)
    risk_level: AgentSeverity = Field(alias="riskLevel")
    requires_backtest: bool = Field(default=True, alias="requiresBacktest")


class GenericReviewInput(AgentModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class StrategyImprovementOutput(AgentBaseOutput):
    recommendations: list[StrategyRecommendation] = Field(default_factory=list)


class BacktestValidationOutput(AgentBaseOutput):
    promotion_allowed: bool = Field(default=False, alias="promotionAllowed")
    required_tests: list[str] = Field(default_factory=list, alias="requiredTests")


class DriftDetectionOutput(AgentBaseOutput):
    drift_detected: bool = Field(default=False, alias="driftDetected")
    windows_checked: list[str] = Field(default_factory=list, alias="windowsChecked")


class ComplianceSafetyOutput(AgentBaseOutput):
    safety_violations: list[str] = Field(default_factory=list, alias="safetyViolations")


class DailyReportOutput(AgentBaseOutput):
    live_readiness: str = Field(alias="liveReadiness")
    summary: str
    next_day_recommendations: list[str] = Field(default_factory=list, alias="nextDayRecommendations")


class AgentDecisionRecord(AgentModel):
    agent_decision_id: str = Field(default_factory=lambda: str(uuid4()), alias="agentDecisionId")
    agent_name: str = Field(alias="agentName")
    agent_version: str = Field(alias="agentVersion")
    prompt_name: str = Field(alias="promptName")
    prompt_version: str = Field(alias="promptVersion")
    prompt_checksum: str = Field(alias="promptChecksum")
    input_hash: str = Field(alias="inputHash")
    raw_input_reference: str = Field(default="inline", alias="rawInputReference")
    raw_output: str = Field(alias="rawOutput")
    parsed_output: dict[str, Any] = Field(default_factory=dict, alias="parsedOutput")
    schema_validation_status: AgentDecisionStatus = Field(alias="schemaValidationStatus")
    confidence: float = Field(default=0.0, ge=0, le=1)
    severity: AgentSeverity = AgentSeverity.LOW
    recommendation: str = ""
    final_action_taken: str = Field(default="NONE", alias="finalActionTaken")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    related_signal_id: str | None = Field(default=None, alias="relatedSignalId")
    related_trade_id: str | None = Field(default=None, alias="relatedTradeId")
    related_strategy: str | None = Field(default=None, alias="relatedStrategy")
    error: str | None = None

    @field_validator("raw_output")
    @classmethod
    def raw_output_required(cls, value: str) -> str:
        if not value:
            return "{}"
        return value


class AgenticReviewResult(AgentModel):
    allowed: bool = True
    block: bool = False
    confidence_multiplier: float = Field(default=1.0, ge=0, le=1)
    risk_multiplier: float = Field(default=1.0, ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)
    records: list[AgentDecisionRecord] = Field(default_factory=list)


class HumanApprovalRecord(AgentModel):
    approval_id: str = Field(default_factory=lambda: str(uuid4()), alias="approvalId")
    change_type: str = Field(alias="changeType")
    proposed_by_agent: str = Field(alias="proposedByAgent")
    evidence: dict[str, Any] = Field(default_factory=dict)
    backtest_result: dict[str, Any] | None = Field(default=None, alias="backtestResult")
    risk_impact: str = Field(alias="riskImpact")
    approved_by: str | None = Field(default=None, alias="approvedBy")
    approved_at: datetime | None = Field(default=None, alias="approvedAt")
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), alias="createdAt")
