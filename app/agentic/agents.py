from __future__ import annotations

import json
import time
from hashlib import sha256
from typing import Any, Generic, TypeVar

from pydantic import ValidationError

from app.agentic.config import AgenticConfig
from app.agentic.journal import AgentDecisionJournal
from app.agentic.models import (
    AgentBaseOutput,
    AgentDecisionRecord,
    AgentDecisionStatus,
    AgentRecommendation,
    AgentSeverity,
    AgentVerdict,
    BacktestValidationOutput,
    ComplianceSafetyOutput,
    DailyReportOutput,
    DriftDetectionOutput,
    ExecutionSimulationInput,
    ExecutionSimulationOutput,
    GenericReviewInput,
    MarketBias,
    MarketContextInput,
    MarketContextOutput,
    PostTradeReviewInput,
    PostTradeReviewOutput,
    RegimeReviewInput,
    RegimeReviewOutput,
    RiskAuditorInput,
    RiskAuditorOutput,
    SignalCriticInput,
    SignalCriticOutput,
    StrategyImprovementOutput,
    StrategyRecommendation,
    TradeBias,
    TradeQuality,
    VolatilityState,
)
from app.agentic.policy import AgentAuthorityPolicy
from app.agentic.prompts import get_prompt

TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class BaseReviewAgent(Generic[TInput, TOutput]):
    agent_name = "BaseReviewAgent"
    agent_version = "1.0.0"
    output_model: type[Any] = AgentBaseOutput

    def __init__(
        self,
        *,
        config: AgenticConfig | None = None,
        journal: AgentDecisionJournal | None = None,
        policy: AgentAuthorityPolicy | None = None,
    ) -> None:
        self.config = config or AgenticConfig.from_settings()
        self.journal = journal or AgentDecisionJournal()
        self.policy = policy or AgentAuthorityPolicy(self.config)

    def review(self, payload: TInput) -> tuple[TOutput | None, AgentDecisionRecord]:
        prompt = get_prompt(self.agent_name)
        input_dict = _model_or_mapping(payload)
        input_hash = _hash_json(input_dict)
        started = time.monotonic()
        try:
            raw_output = self._raw_review(payload)
            elapsed_ms = (time.monotonic() - started) * 1000
            if elapsed_ms > self.config.agent_timeout_ms:
                record = self._record(
                    prompt=prompt,
                    input_hash=input_hash,
                    raw_output=raw_output,
                    status=AgentDecisionStatus.TIMEOUT,
                    error="agent_timeout",
                    payload=input_dict,
                )
                self.journal.append(record)
                return None, record
            parsed = self.output_model.model_validate_json(raw_output)
            policy_result = self.policy.apply(
                verdict=str(getattr(parsed, "verdict", AgentVerdict.APPROVE)),
                severity=str(getattr(parsed, "severity", AgentSeverity.LOW)),
                recommendation=str(getattr(parsed, "recommended_action", AgentRecommendation.ALLOW)),
                reason_codes=list(getattr(parsed, "reason_codes", [])),
                valid=True,
            )
            record = self._record(
                prompt=prompt,
                input_hash=input_hash,
                raw_output=raw_output,
                status=AgentDecisionStatus.VALID,
                parsed_output=parsed.model_dump(mode="json", by_alias=True),
                confidence=float(getattr(parsed, "confidence", 0.0)),
                severity=AgentSeverity(str(getattr(parsed, "severity", AgentSeverity.LOW))),
                recommendation=str(getattr(parsed, "recommended_action", "")),
                final_action_taken="BLOCK" if policy_result.block else "ALLOW_OR_WARN",
                payload=input_dict,
            )
            self.journal.append(record)
            return parsed, record
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            raw_output = locals().get("raw_output", "{}")
            record = self._record(
                prompt=prompt,
                input_hash=input_hash,
                raw_output=raw_output,
                status=AgentDecisionStatus.INVALID,
                error=str(exc),
                payload=input_dict,
            )
            self.journal.append(record)
            return None, record
        except Exception as exc:
            record = self._record(
                prompt=prompt,
                input_hash=input_hash,
                raw_output="{}",
                status=AgentDecisionStatus.ERROR,
                error=str(exc),
                payload=input_dict,
            )
            self.journal.append(record)
            return None, record

    def _raw_review(self, payload: TInput) -> str:
        reviewed = self._deterministic_review(payload)
        if hasattr(reviewed, "model_dump_json"):
            return reviewed.model_dump_json(by_alias=True)
        return json.dumps(reviewed, default=str)

    def _deterministic_review(self, payload: TInput) -> TOutput:
        raise NotImplementedError

    def _record(
        self,
        *,
        prompt,
        input_hash: str,
        raw_output: str,
        status: AgentDecisionStatus,
        payload: dict[str, Any],
        parsed_output: dict[str, Any] | None = None,
        confidence: float = 0.0,
        severity: AgentSeverity = AgentSeverity.LOW,
        recommendation: str = "",
        final_action_taken: str = "NONE",
        error: str | None = None,
    ) -> AgentDecisionRecord:
        return AgentDecisionRecord(
            agentName=self.agent_name,
            agentVersion=self.agent_version,
            promptName=prompt.prompt_name,
            promptVersion=prompt.prompt_version,
            promptChecksum=prompt.checksum,
            inputHash=input_hash,
            rawInputReference=_hash_json(payload),
            rawOutput=raw_output,
            parsedOutput=parsed_output or {},
            schemaValidationStatus=status,
            confidence=confidence,
            severity=severity,
            recommendation=recommendation,
            finalActionTaken=final_action_taken,
            relatedSignalId=_first_value(payload, "signalId", "signal_id"),
            relatedTradeId=_first_value(payload, "tradeId", "trade_id", "shadowOrderId"),
            relatedStrategy=_first_value(payload, "strategyName", "strategy_name"),
            error=error,
        )


class MarketContextAgent(BaseReviewAgent[MarketContextInput, MarketContextOutput]):
    agent_name = "MarketContextAgent"
    output_model = MarketContextOutput

    def _deterministic_review(self, payload: MarketContextInput) -> MarketContextOutput:
        reasons: list[str] = []
        bias = MarketBias.UNCERTAIN
        if payload.breadth is not None:
            if payload.breadth >= 0.6:
                bias = MarketBias.BULLISH
                reasons.append("positive_breadth")
            elif payload.breadth <= 0.4:
                bias = MarketBias.BEARISH
                reasons.append("negative_breadth")
        volatility = VolatilityState.NORMAL
        if payload.india_vix is not None and payload.india_vix >= 22:
            volatility = VolatilityState.PANIC
            reasons.append("india_vix_panic")
        elif payload.india_vix is not None and payload.india_vix >= 17:
            volatility = VolatilityState.HIGH
            reasons.append("india_vix_high")
        trade_bias = TradeBias.NO_TRADE if volatility == VolatilityState.PANIC else TradeBias.BOTH_ALLOWED
        severity = AgentSeverity.HIGH if volatility == VolatilityState.PANIC else AgentSeverity.LOW
        return MarketContextOutput(
            agentName=self.agent_name,
            verdict=AgentVerdict.WARN if reasons else AgentVerdict.INSUFFICIENT_DATA,
            severity=severity,
            confidence=0.65 if reasons else 0.25,
            reasonCodes=reasons or ["insufficient_market_context"],
            explanation="Broad market context reviewed without authority to force trades.",
            recommendedAction=AgentRecommendation.BLOCK if severity == AgentSeverity.HIGH else AgentRecommendation.ALLOW,
            marketBias=bias,
            volatilityState=volatility,
            recommendedTradeBias=trade_bias,
            riskMultiplierSuggestion=0.0 if severity == AgentSeverity.HIGH else 1.0,
            avoidTimeWindows=[],
            keyWarnings=reasons,
            auditTags=["pre_market"],
        )


class RegimeReviewAgent(BaseReviewAgent[RegimeReviewInput, RegimeReviewOutput]):
    agent_name = "RegimeReviewAgent"
    output_model = RegimeReviewOutput

    def _deterministic_review(self, payload: RegimeReviewInput) -> RegimeReviewOutput:
        snapshot = payload.market_snapshot
        last_price = _float(snapshot.get("last_price"))
        vwap = _float(snapshot.get("vwap"))
        suggested = payload.deterministic_regime
        reasons: list[str] = []
        if last_price and vwap:
            if last_price > vwap and "BEARISH" in payload.deterministic_regime:
                suggested = "SIDEWAYS"
                reasons.append("price_above_vwap_disagrees_with_bearish_regime")
            if last_price < vwap and "BULLISH" in payload.deterministic_regime:
                suggested = "SIDEWAYS"
                reasons.append("price_below_vwap_disagrees_with_bullish_regime")
        agrees = not reasons
        return RegimeReviewOutput(
            agentName=self.agent_name,
            verdict=AgentVerdict.APPROVE if agrees else AgentVerdict.WARN,
            severity=AgentSeverity.LOW if agrees else AgentSeverity.MEDIUM,
            confidence=0.7 if last_price and vwap else 0.3,
            reasonCodes=reasons or ["regime_review_clear"],
            explanation="Reviewed deterministic regime against supplied VWAP context.",
            recommendedAction=AgentRecommendation.ALLOW if agrees else AgentRecommendation.REDUCE_CONFIDENCE,
            agreesWithRegime=agrees,
            suggestedRegime=suggested,
            auditTags=["regime_review"],
        )


class SignalCriticAgent(BaseReviewAgent[SignalCriticInput, SignalCriticOutput]):
    agent_name = "SignalCriticAgent"
    output_model = SignalCriticOutput

    def _deterministic_review(self, payload: SignalCriticInput) -> SignalCriticOutput:
        reasons: list[str] = []
        severity = AgentSeverity.LOW
        action = AgentRecommendation.ALLOW
        verdict = AgentVerdict.APPROVE
        if payload.risk_reward_ratio < 1.5:
            reasons.append("risk_reward_too_low")
            severity = AgentSeverity.HIGH
        if payload.stop_loss <= 0 or payload.stop_loss == payload.entry_price:
            reasons.append("invalid_stop_loss")
            severity = AgentSeverity.HIGH
        if payload.direction == "LONG" and "BEARISH" in payload.market_regime:
            reasons.append("long_signal_against_bearish_regime")
            severity = AgentSeverity.HIGH
        if payload.direction == "SHORT" and "BULLISH" in payload.market_regime:
            reasons.append("short_signal_against_bullish_regime")
            severity = AgentSeverity.HIGH
        last_close = _float(payload.candle_snapshot.get("close"))
        if last_close and abs(payload.entry_price - last_close) / payload.entry_price > 0.01:
            reasons.append("entry_far_from_latest_candle_close")
            severity = max_severity(severity, AgentSeverity.MEDIUM)
        if payload.trades_taken_today >= 3:
            reasons.append("trade_count_near_daily_limit")
            severity = max_severity(severity, AgentSeverity.MEDIUM)
        if severity == AgentSeverity.HIGH:
            verdict = AgentVerdict.REJECT
            action = AgentRecommendation.BLOCK
        elif severity == AgentSeverity.MEDIUM:
            verdict = AgentVerdict.WARN
            action = AgentRecommendation.REDUCE_CONFIDENCE
        return SignalCriticOutput(
            agentName=self.agent_name,
            signalId=payload.signal_id,
            verdict=verdict,
            severity=severity,
            confidence=0.82 if reasons else 0.72,
            reasonCodes=reasons or ["signal_context_acceptable"],
            explanation="Signal critique completed. Agent cannot force trades or increase size.",
            recommendedAction=action,
            riskMultiplierSuggestion=0.0 if action == AgentRecommendation.BLOCK else 1.0,
            auditTags=["pre_signal_acceptance"],
        )


class RiskAuditorAgent(BaseReviewAgent[RiskAuditorInput, RiskAuditorOutput]):
    agent_name = "RiskAuditorAgent"
    output_model = RiskAuditorOutput

    def _deterministic_review(self, payload: RiskAuditorInput) -> RiskAuditorOutput:
        violations: list[str] = []
        if payload.quantity <= 0:
            violations.append("quantity_not_positive")
        if payload.stop_distance <= 0:
            violations.append("stop_distance_invalid")
        if payload.risk_reward_ratio < 1.5:
            violations.append("risk_reward_below_policy")
        if payload.trades_taken_today >= payload.max_trades_per_day:
            violations.append("daily_trade_limit_reached")
        if payload.risk_amount > payload.capital * 0.005:
            violations.append("risk_amount_above_hard_shadow_cap")
        severity = AgentSeverity.HIGH if violations else AgentSeverity.LOW
        return RiskAuditorOutput(
            agentName=self.agent_name,
            verdict=AgentVerdict.REJECT if violations else AgentVerdict.APPROVE,
            severity=severity,
            confidence=0.9,
            reasonCodes=violations or ["risk_manager_output_acceptable"],
            explanation="Risk audit reviewed deterministic approval before shadow execution.",
            recommendedAction=AgentRecommendation.BLOCK if violations else AgentRecommendation.ALLOW,
            riskViolations=violations,
            auditTags=["pre_shadow_execution"],
        )


class ExecutionSimulationAgent(BaseReviewAgent[ExecutionSimulationInput, ExecutionSimulationOutput]):
    agent_name = "ExecutionSimulationAgent"
    output_model = ExecutionSimulationOutput

    def _deterministic_review(self, payload: ExecutionSimulationInput) -> ExecutionSimulationOutput:
        reasons: list[str] = []
        action = AgentRecommendation.ALLOW
        severity = AgentSeverity.LOW
        if payload.fill_status == "MISSED":
            reasons.append("missed_entry")
            action = AgentRecommendation.MARK_MISSED
            severity = AgentSeverity.MEDIUM
        if payload.expected_entry > 0 and payload.simulated_fill is not None:
            slippage_pct = abs(payload.simulated_fill - payload.expected_entry) / payload.expected_entry
            if slippage_pct > 0.0025:
                reasons.append("high_simulated_slippage")
                action = AgentRecommendation.INCREASE_SLIPPAGE_MODEL
                severity = AgentSeverity.MEDIUM
        return ExecutionSimulationOutput(
            agentName=self.agent_name,
            verdict=AgentVerdict.WARN if reasons else AgentVerdict.APPROVE,
            severity=severity,
            confidence=0.75,
            reasonCodes=reasons or ["execution_simulation_reasonable"],
            explanation="Execution simulation reviewed; no broker order path exists here.",
            recommendedAction=action,
            executionQualityScore=0.7 if reasons else 1.0,
            auditTags=["post_shadow_fill"],
        )


class PostTradeReviewAgent(BaseReviewAgent[PostTradeReviewInput, PostTradeReviewOutput]):
    agent_name = "PostTradeReviewAgent"
    output_model = PostTradeReviewOutput

    def _deterministic_review(self, payload: PostTradeReviewInput) -> PostTradeReviewOutput:
        profitable = payload.net_pnl > 0
        good_process = payload.rules_followed and payload.stop_loss > 0
        quality = (
            TradeQuality.GOOD_TRADE_GOOD_OUTCOME
            if good_process and profitable
            else TradeQuality.GOOD_TRADE_BAD_OUTCOME
            if good_process
            else TradeQuality.BAD_TRADE_GOOD_OUTCOME
            if profitable
            else TradeQuality.BAD_TRADE_BAD_OUTCOME
        )
        return PostTradeReviewOutput(
            agentName=self.agent_name,
            tradeId=payload.trade_id,
            tradeQuality=quality,
            mistakes=[] if good_process else ["rules_not_followed"],
            whatWorked=["positive_process"] if good_process else [],
            whatFailed=[] if profitable else ["trade_lost_money_after_costs"],
            recommendations=["review_in_backtest_before_strategy_change"],
            shouldAffectStrategy=not good_process,
            requiresBacktest=True,
            confidence=0.75,
        )


class BacktestValidationAgent(BaseReviewAgent[GenericReviewInput, BacktestValidationOutput]):
    agent_name = "BacktestValidationAgent"
    output_model = BacktestValidationOutput

    def _deterministic_review(self, payload: GenericReviewInput) -> BacktestValidationOutput:
        return BacktestValidationOutput(
            agentName=self.agent_name,
            verdict=AgentVerdict.REJECT,
            severity=AgentSeverity.HIGH,
            confidence=0.95,
            reasonCodes=["backtest_not_run", "walk_forward_not_run", "cost_sensitivity_not_run"],
            explanation="No strategy promotion is allowed until full validation exists.",
            recommendedAction=AgentRecommendation.REQUIRE_BACKTEST,
            promotionAllowed=False,
            requiredTests=[
                "historical_backtest",
                "out_of_sample_test",
                "walk_forward_test",
                "cost_adjusted_test",
                "slippage_sensitivity",
            ],
            auditTags=["promotion_gate"],
        )


class DriftDetectionAgent(BaseReviewAgent[GenericReviewInput, DriftDetectionOutput]):
    agent_name = "DriftDetectionAgent"
    output_model = DriftDetectionOutput

    def _deterministic_review(self, payload: GenericReviewInput) -> DriftDetectionOutput:
        rows = payload.payload.get("trades", []) if isinstance(payload.payload, dict) else []
        drift = len(rows) > 0 and sum(1 for row in rows[-20:] if row.get("net_pnl", 0) < 0) > 12
        return DriftDetectionOutput(
            agentName=self.agent_name,
            verdict=AgentVerdict.WARN if drift else AgentVerdict.APPROVE,
            severity=AgentSeverity.MEDIUM if drift else AgentSeverity.LOW,
            confidence=0.6 if rows else 0.25,
            reasonCodes=["rolling_loss_cluster"] if drift else ["insufficient_or_no_drift_detected"],
            explanation="Rolling drift scan completed with no authority to change live strategy.",
            recommendedAction=AgentRecommendation.DISABLE_STRATEGY_TEMPORARILY if drift else AgentRecommendation.ALLOW,
            driftDetected=drift,
            windowsChecked=["last_20_trades", "last_50_trades", "last_100_trades", "last_5_sessions", "last_10_sessions"],
            auditTags=["drift_detection"],
        )


class StrategyImprovementAgent(BaseReviewAgent[GenericReviewInput, StrategyImprovementOutput]):
    agent_name = "StrategyImprovementAgent"
    output_model = StrategyImprovementOutput

    def _deterministic_review(self, payload: GenericReviewInput) -> StrategyImprovementOutput:
        recommendation = StrategyRecommendation(
            description="Keep collecting shadow samples before changing live strategy thresholds.",
            expectedImpact="reduces_overfitting_risk",
            evidence=["live_readiness_blocked", "insufficient_shadow_sessions"],
            riskLevel=AgentSeverity.LOW,
            requiresBacktest=True,
        )
        return StrategyImprovementOutput(
            agentName=self.agent_name,
            verdict=AgentVerdict.WARN,
            severity=AgentSeverity.LOW,
            confidence=0.7,
            reasonCodes=["strategy_changes_require_backtest"],
            explanation="Research recommendations are queued only; they are never auto-applied.",
            recommendedAction=AgentRecommendation.REQUIRE_BACKTEST,
            recommendations=[recommendation],
            auditTags=["strategy_research"],
        )


class ComplianceSafetyAgent(BaseReviewAgent[GenericReviewInput, ComplianceSafetyOutput]):
    agent_name = "ComplianceSafetyAgent"
    output_model = ComplianceSafetyOutput

    def _deterministic_review(self, payload: GenericReviewInput) -> ComplianceSafetyOutput:
        data = payload.payload
        violations: list[str] = []
        if data.get("live_orders_enabled") is not False:
            violations.append("live_orders_not_disabled")
        if data.get("live_trading_enabled") is not False:
            violations.append("live_trading_not_disabled")
        if data.get("kill_switch") is not True:
            violations.append("kill_switch_not_enabled")
        if data.get("trading_mode") not in {"SHADOW_LIVE", "SHADOW_LIVE_REAL_DATA"}:
            violations.append("unexpected_trading_mode")
        return ComplianceSafetyOutput(
            agentName=self.agent_name,
            verdict=AgentVerdict.REJECT if violations else AgentVerdict.APPROVE,
            severity=AgentSeverity.HIGH if violations else AgentSeverity.LOW,
            confidence=0.95,
            reasonCodes=violations or ["shadow_safety_posture_confirmed"],
            explanation="Compliance safety checked live-trading posture and audit requirements.",
            recommendedAction=AgentRecommendation.BLOCK if violations else AgentRecommendation.ALLOW,
            safetyViolations=violations,
            auditTags=["compliance_safety"],
        )


class DailyReportAgent(BaseReviewAgent[GenericReviewInput, DailyReportOutput]):
    agent_name = "DailyReportAgent"
    output_model = DailyReportOutput

    def _deterministic_review(self, payload: GenericReviewInput) -> DailyReportOutput:
        data = payload.payload
        net_pnl = _float(data.get("net_pnl")) or 0.0
        trades = int(data.get("trades_taken") or 0)
        summary = f"Shadow day reviewed: trades={trades}, net_pnl={net_pnl:.2f}, live readiness blocked."
        return DailyReportOutput(
            agentName=self.agent_name,
            verdict=AgentVerdict.WARN,
            severity=AgentSeverity.LOW,
            confidence=0.75,
            reasonCodes=["daily_report_generated", "live_readiness_blocked"],
            explanation="Daily report generated from supplied journal data only.",
            recommendedAction=AgentRecommendation.REVIEW_ONLY,
            liveReadiness="BLOCKED",
            summary=summary,
            nextDayRecommendations=["continue_shadow_collection", "do_not_enable_live_trading"],
            auditTags=["daily_report"],
        )


def _model_or_mapping(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, dict):
        return value
    return {"value": str(value)}


def _hash_json(payload: dict[str, Any]) -> str:
    return sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _first_value(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value)
    return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def max_severity(left: AgentSeverity, right: AgentSeverity) -> AgentSeverity:
    order = {AgentSeverity.LOW: 1, AgentSeverity.MEDIUM: 2, AgentSeverity.HIGH: 3}
    return left if order[left] >= order[right] else right
