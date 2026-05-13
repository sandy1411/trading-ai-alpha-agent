from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class AgenticConfig:
    enabled: bool = True
    strict_mode: bool = True
    agent_can_block_trade: bool = True
    agent_can_reduce_confidence: bool = True
    agent_can_recommend_risk_reduction: bool = True
    agent_can_force_trade: bool = False
    agent_can_increase_risk: bool = False
    agent_can_change_strategy_live: bool = False
    agent_timeout_ms: int = 1500
    max_retries: int = 0
    fallback_policy: str = "FAIL_SAFE_BLOCK"

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "AgenticConfig":
        resolved = settings or get_settings()
        return cls(
            enabled=resolved.agentic_review_enabled,
            strict_mode=resolved.agentic_strict_mode,
            agent_can_block_trade=resolved.agent_can_block_trade,
            agent_can_reduce_confidence=resolved.agent_can_reduce_confidence,
            agent_can_recommend_risk_reduction=resolved.agent_can_recommend_risk_reduction,
            agent_can_force_trade=resolved.agent_can_force_trade,
            agent_can_increase_risk=resolved.agent_can_increase_risk,
            agent_can_change_strategy_live=resolved.agent_can_change_strategy_live,
            agent_timeout_ms=resolved.agent_timeout_ms,
            max_retries=resolved.agent_max_retries,
            fallback_policy=resolved.agent_fallback_policy,
        )
