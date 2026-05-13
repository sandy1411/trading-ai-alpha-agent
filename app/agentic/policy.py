from __future__ import annotations

from app.agentic.config import AgenticConfig
from app.agentic.models import AgentRecommendation, AgentSeverity, AgentVerdict, AgenticReviewResult

FORBIDDEN_RECOMMENDATIONS = {
    "FORCE_TRADE",
    "INCREASE_SIZE",
    "INCREASE_RISK",
    "ENABLE_LIVE_TRADING",
    "CHANGE_STRATEGY_LIVE",
    "DELETE_LOGS",
    "MODIFY_JOURNAL",
}


class AgentAuthorityPolicy:
    def __init__(self, config: AgenticConfig | None = None) -> None:
        self.config = config or AgenticConfig.from_settings()

    def validate_recommendation(self, recommendation: str) -> tuple[bool, str | None]:
        normalized = recommendation.upper()
        if normalized in FORBIDDEN_RECOMMENDATIONS:
            return False, "forbidden_agent_recommendation"
        if normalized == AgentRecommendation.BLOCK.value and not self.config.agent_can_block_trade:
            return False, "agent_block_not_allowed"
        if normalized == AgentRecommendation.REDUCE_CONFIDENCE.value and not self.config.agent_can_reduce_confidence:
            return False, "agent_reduce_confidence_not_allowed"
        if normalized == AgentRecommendation.REDUCE_SIZE.value and not self.config.agent_can_recommend_risk_reduction:
            return False, "agent_risk_reduction_not_allowed"
        return True, None

    def apply(
        self,
        *,
        verdict: str,
        severity: str,
        recommendation: str,
        reason_codes: list[str],
        valid: bool,
    ) -> AgenticReviewResult:
        if not valid:
            block = self.config.strict_mode and self.config.fallback_policy == "FAIL_SAFE_BLOCK"
            return AgenticReviewResult(
                allowed=not block,
                block=block,
                warnings=["agent_output_invalid"],
            )

        recommendation_ok, policy_error = self.validate_recommendation(recommendation)
        if not recommendation_ok:
            block = self.config.strict_mode
            return AgenticReviewResult(
                allowed=not block,
                block=block,
                warnings=[policy_error or "agent_policy_violation"],
            )

        warnings = list(reason_codes)
        if severity == AgentSeverity.HIGH.value:
            return AgenticReviewResult(allowed=False, block=True, warnings=warnings)
        if verdict == AgentVerdict.REJECT.value or recommendation == AgentRecommendation.BLOCK.value:
            return AgenticReviewResult(allowed=False, block=True, warnings=warnings)
        if severity == AgentSeverity.MEDIUM.value:
            return AgenticReviewResult(
                allowed=True,
                block=False,
                confidence_multiplier=0.8,
                risk_multiplier=0.75 if recommendation == AgentRecommendation.REDUCE_SIZE.value else 1.0,
                warnings=warnings,
            )
        return AgenticReviewResult(allowed=True, block=False, warnings=warnings)
