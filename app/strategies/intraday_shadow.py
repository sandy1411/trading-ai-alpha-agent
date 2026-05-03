from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class IntradayStrategyProfile:
    code: str
    name: str
    status: str
    market_fit: list[str]
    entry_model: str
    exit_model: str
    stop_model: str
    risk_controls: list[str]
    promotion_gates: list[str]
    disabled_reasons: list[str]

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


class IntradayShadowPlaybook:
    """Shadow-only intraday research plan.

    These profiles define what the platform should observe and score before any
    future micro-live discussion. They do not create orders or override risk gates.
    """

    min_samples_per_profile = 200
    min_positive_expectancy_days = 20
    max_shadow_drawdown_pct = 0.02
    max_hypothesis_risk_per_trade_pct = 0.0025
    min_reward_risk_ratio = 2.0

    def profiles(self) -> list[IntradayStrategyProfile]:
        return [
            IntradayStrategyProfile(
                code="OPENING_RANGE_CONTINUATION",
                name="Opening range continuation",
                status="SHADOW_OBSERVE",
                market_fit=["INDIA", "US"],
                entry_model=(
                    "Observe only after the initial range is formed; require price strength, "
                    "volume confirmation, and no gap-risk blocker."
                ),
                exit_model=(
                    "Exit hypothesis at stop, target, loss of session trend, or time cutoff."
                ),
                stop_model="Initial stop below opening range/VWAP structure; never widen stop.",
                risk_controls=[
                    "No entry during first noisy minutes.",
                    "No averaging down.",
                    "No new entry after market-specific cutoff.",
                    "Reward/risk must be at least 2.0 before candidate is considered.",
                ],
                promotion_gates=[
                    "At least 200 market-hours samples.",
                    "Positive expectancy after costs and slippage assumptions.",
                    "No single-day shadow drawdown above 2%.",
                ],
                disabled_reasons=[],
            ),
            IntradayStrategyProfile(
                code="VWAP_PULLBACK_CONTINUATION",
                name="VWAP pullback continuation",
                status="SHADOW_OBSERVE",
                market_fit=["INDIA", "US"],
                entry_model=(
                    "Observe pullback toward VWAP only when broader session trend is intact "
                    "and price recovers without breaking risk structure."
                ),
                exit_model="Exit hypothesis at stop, prior high/target, or failed VWAP reclaim.",
                stop_model="Stop below pullback swing low or VWAP failure band.",
                risk_controls=[
                    "Reject extended moves far above VWAP.",
                    "Require fresh quote and market-calendar open status.",
                    "Skip low-liquidity or high-spread symbols.",
                    "One active hypothesis per symbol.",
                ],
                promotion_gates=[
                    "At least 200 market-hours samples.",
                    "Average win/loss ratio remains favorable after slippage.",
                    "Loss clusters trigger cooling-off rule.",
                ],
                disabled_reasons=[],
            ),
            IntradayStrategyProfile(
                code="GAP_RISK_FILTER",
                name="Gap risk filter",
                status="GUARDRAIL_ONLY",
                market_fit=["INDIA", "US"],
                entry_model="Not an entry strategy; it blocks lower-quality intraday hypotheses.",
                exit_model="Forces no-trade when gap or news risk exceeds configured bands.",
                stop_model="No stop because blocked hypotheses never become order candidates.",
                risk_controls=[
                    "Block large adverse gaps.",
                    "Block missing prior close/open/high/low data.",
                    "Block stale FX for US observations.",
                    "Block missing provider health.",
                ],
                promotion_gates=[
                    "Keep enabled before any faster strategy is considered.",
                    "Must explain every blocked opportunity in audit/risk telemetry.",
                ],
                disabled_reasons=[],
            ),
            IntradayStrategyProfile(
                code="FAST_MEAN_REVERSION",
                name="Fast mean reversion",
                status="DISABLED_HIGH_RISK",
                market_fit=["INDIA", "US"],
                entry_model=(
                    "Disabled for now. Mean reversion can look attractive in backtests and "
                    "fail badly during trend days."
                ),
                exit_model="N/A until enabled for shadow-only research.",
                stop_model="N/A until enabled for shadow-only research.",
                risk_controls=[
                    "Needs tick-level spread/impact study first.",
                    "Needs circuit/halts/news filters first.",
                    "Needs hard daily loss and cooling-off controls first.",
                ],
                promotion_gates=[
                    "Separate research approval required.",
                    "At least 500 shadow samples before reconsideration.",
                ],
                disabled_reasons=[
                    "Higher tail risk than continuation strategies.",
                    "More sensitive to latency and spread.",
                ],
            ),
        ]

    def dashboard_summary(self) -> dict[str, Any]:
        profiles = self.profiles()
        return {
            "mode": "SHADOW_ONLY_INTRADAY_RESEARCH",
            "capital_posture": "PROTECT_CAPITAL_FIRST",
            "aggression_policy": (
                "Do not increase aggressiveness until shadow evidence, slippage, and "
                "compliance gates are reviewed."
            ),
            "min_samples_per_profile": self.min_samples_per_profile,
            "min_positive_expectancy_days": self.min_positive_expectancy_days,
            "max_shadow_drawdown_pct": self.max_shadow_drawdown_pct,
            "max_hypothesis_risk_per_trade_pct": self.max_hypothesis_risk_per_trade_pct,
            "min_reward_risk_ratio": self.min_reward_risk_ratio,
            "profiles": [profile.model_dump() for profile in profiles],
            "intraday_guardrails": [
                "Stop-loss must exist before any candidate is considered.",
                "No short selling, margin, options, derivatives, or leverage in v1.",
                "No new live entry while kill switch is on or live trading is disabled.",
                "Unknown broker status blocks duplicates and requires reconciliation.",
                "Market closed, stale data, stale FX, or provider degradation blocks live paths.",
                "A losing streak must reduce activity, not increase size.",
            ],
            "recommended_next_steps": [
                "Collect more India and US market-hours shadow samples.",
                "Measure slippage/latency assumptions separately from signal quality.",
                "Add close-out tracking so every hypothesis has a final outcome reason.",
                "Review strategy evidence weekly before changing risk limits.",
            ],
        }
