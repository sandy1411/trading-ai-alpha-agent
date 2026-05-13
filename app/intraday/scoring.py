from __future__ import annotations

from app.intraday.config import IntradayShadowConfig
from app.intraday.models import Direction, MarketRegime, ScoredSignal, Signal, SignalDecision


class SignalScoringEngine:
    def __init__(self, config: IntradayShadowConfig | None = None) -> None:
        self.config = config or IntradayShadowConfig.from_settings()

    def score(self, signal: Signal) -> ScoredSignal:
        reasons: list[str] = []
        components = {
            "regime_alignment": self._regime_score(signal),
            "vwap_alignment": 15 if self._has_reason(signal, "vwap") else 0,
            "sector_strength": 15 if self._regime_metric(signal, "sector") else 8,
            "volume_confirmation": 15 if "volume_confirmation" in signal.reason_codes else 0,
            "price_structure": 15 if self._structure_confirmed(signal) else 0,
            "risk_reward_quality": 10 if signal.risk_reward_ratio >= self.config.min_reward_to_risk else 0,
            "liquidity_spread_quality": 5 if self._spread_ok(signal) else 0,
        }
        score = sum(components.values())
        if signal.regime_at_signal == MarketRegime.SIDEWAYS and not self.config.allow_sideways_trades:
            score = min(score, self.config.watch_score - 1)
            reasons.append("sideways_regime_reject")
        if signal.regime_at_signal in {MarketRegime.HIGH_VOLATILITY, MarketRegime.LOW_LIQUIDITY, MarketRegime.NO_TRADE}:
            score = min(score, self.config.watch_score - 1)
            reasons.append(f"{signal.regime_at_signal.value.lower()}_reject")
        if signal.risk_reward_ratio < self.config.min_reward_to_risk:
            reasons.append("risk_reward_below_threshold")
        if score >= self.config.min_signal_score:
            decision = SignalDecision.VALID
            reasons.append("score_valid")
        elif score >= self.config.watch_score:
            decision = SignalDecision.WATCH_ONLY
            reasons.append("score_watch_only")
        else:
            decision = SignalDecision.REJECTED
            reasons.append("score_rejected")
        return ScoredSignal(
            signal=signal,
            score=score,
            decision=decision,
            reasons=list(dict.fromkeys([*reasons, *signal.reason_codes])),
            component_scores=components,
        )

    @staticmethod
    def _has_reason(signal: Signal, needle: str) -> bool:
        return any(needle in reason for reason in signal.reason_codes)

    @staticmethod
    def _structure_confirmed(signal: Signal) -> bool:
        return any(reason in signal.reason_codes for reason in {
            "higher_high_higher_low",
            "lower_high_lower_low",
            "opening_range_breakout",
            "opening_range_breakdown",
        })

    @staticmethod
    def _regime_metric(signal: Signal, needle: str) -> bool:
        reasons = signal.market_snapshot.get("regime_reasons", [])
        return any(needle in str(reason) for reason in reasons)

    @staticmethod
    def _spread_ok(signal: Signal) -> bool:
        spread = signal.market_snapshot.get("spread_pct")
        return spread is None or float(spread) <= 0.003

    @staticmethod
    def _regime_score(signal: Signal) -> int:
        bullish = {MarketRegime.STRONG_BULLISH, MarketRegime.WEAK_BULLISH}
        bearish = {MarketRegime.STRONG_BEARISH, MarketRegime.WEAK_BEARISH}
        if signal.direction == Direction.LONG and signal.regime_at_signal in bullish:
            return 25
        if signal.direction == Direction.SHORT and signal.regime_at_signal in bearish:
            return 25
        return 0

