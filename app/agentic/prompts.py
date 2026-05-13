from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256


BASE_SAFETY_INSTRUCTIONS = """
You are a trading research review agent. Return JSON only.
Use only the supplied input data. If evidence is missing, return INSUFFICIENT_DATA.
Do not place orders, force trades, increase risk, change live settings, average down,
martingale, hide losses, rewrite journals, or deploy strategy changes.
Always include severity, confidence, reason codes, uncertainty, and an allowed recommendation.
"""


@dataclass(frozen=True)
class PromptTemplate:
    prompt_name: str
    prompt_version: str
    body: str
    created_at: str
    active: bool = True

    @property
    def checksum(self) -> str:
        return sha256(self.body.encode("utf-8")).hexdigest()


PROMPTS: dict[str, PromptTemplate] = {
    name: PromptTemplate(
        prompt_name=name,
        prompt_version="1.0.0",
        created_at=datetime(2026, 5, 13, tzinfo=UTC).isoformat(),
        body=f"{BASE_SAFETY_INSTRUCTIONS}\nAgent task: {task}",
    )
    for name, task in {
        "MarketContextAgent": "Review broad market context and recommend bias/risk reduction only.",
        "RegimeReviewAgent": "Review deterministic market regime and flag disagreement.",
        "SignalCriticAgent": "Critically review a candidate signal before risk approval.",
        "RiskAuditorAgent": "Audit RiskManager output before shadow execution.",
        "ExecutionSimulationAgent": "Review whether shadow execution assumptions are realistic.",
        "PostTradeReviewAgent": "Classify completed trade quality and lessons.",
        "BacktestValidationAgent": "Validate proposed strategy changes before promotion.",
        "DriftDetectionAgent": "Detect performance decay and strategy drift.",
        "StrategyImprovementAgent": "Recommend research changes that require validation.",
        "ComplianceSafetyAgent": "Check compliance and live-trading safety posture.",
        "DailyReportAgent": "Generate end-of-day review summary and readiness status.",
    }.items()
}


def get_prompt(agent_name: str) -> PromptTemplate:
    return PROMPTS[agent_name]
