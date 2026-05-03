from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.core.enums import TradeAction


@dataclass(frozen=True)
class ConservativeSignalAssessment:
    action: TradeAction
    confidence: float
    stop_loss: float | None
    take_profit: float | None
    expected_risk: float
    expected_reward: float
    reward_risk_ratio: float
    reasons: list[str]
    risk_flags: list[str]
    metrics: dict[str, float | str | bool]

    def model_dump(self) -> dict[str, Any]:
        data = asdict(self)
        data["action"] = self.action.value
        return data


class ConservativeShadowStrategy:
    """Long-only quality filter for observation-only shadow hypotheses.

    This is deliberately conservative and transparent. It uses only real quote fields from
    the provider response; when quote quality is weak, it returns NO_TRADE.
    """

    min_confidence = 0.65
    min_reward_risk_ratio = 1.8
    min_range_pct = 0.0025
    max_range_pct = 0.045
    max_adverse_gap_pct = -0.03
    min_stop_pct = 0.008
    max_stop_pct = 0.03
    stop_range_multiplier = 1.5
    reward_multiple = 2.0

    def assess(self, quote: dict[str, Any], last_price: float | None) -> ConservativeSignalAssessment:
        if last_price is None or last_price <= 0:
            return self._no_trade(["last_price_missing"], {"last_price": 0.0})

        quote_data = self._first_quote_payload(quote)
        ohlc = quote_data.get("ohlc") if isinstance(quote_data.get("ohlc"), dict) else {}
        open_price = self._positive_float(ohlc.get("open"))
        high_price = self._positive_float(ohlc.get("high"))
        low_price = self._positive_float(ohlc.get("low"))
        close_price = self._positive_float(ohlc.get("close"))
        average_price = self._positive_float(quote_data.get("average_price"))
        volume = self._positive_float(quote_data.get("volume"))

        metrics: dict[str, float | str | bool] = {
            "last_price": last_price,
            "quote_has_ohlc": bool(ohlc),
            "volume": volume or 0.0,
        }
        reasons: list[str] = []
        risk_flags: list[str] = ["observation_only_no_order_intent"]

        if not all([open_price, high_price, low_price, close_price]):
            risk_flags.append("insufficient_ohlc_for_strategy")
            return self._no_trade(risk_flags, metrics)

        assert open_price is not None
        assert high_price is not None
        assert low_price is not None
        assert close_price is not None

        session_range = max(high_price - low_price, 0)
        true_range_proxy = max(
            session_range,
            abs(high_price - close_price),
            abs(low_price - close_price),
            last_price * self.min_stop_pct,
        )
        range_pct = session_range / last_price
        intraday_change_pct = (last_price - open_price) / open_price
        prior_close_change_pct = (last_price - close_price) / close_price
        gap_pct = (open_price - close_price) / close_price
        average_price_distance_pct = (
            (last_price - average_price) / last_price if average_price else 0.0
        )
        stop_pct = min(
            max((true_range_proxy * self.stop_range_multiplier) / last_price, self.min_stop_pct),
            self.max_stop_pct,
        )
        stop_loss = round(last_price * (1 - stop_pct), 2)
        expected_risk = round(last_price - stop_loss, 4)
        take_profit = round(last_price + expected_risk * self.reward_multiple, 2)
        expected_reward = round(take_profit - last_price, 4)
        reward_risk_ratio = (
            round(expected_reward / expected_risk, 4) if expected_risk > 0 else 0.0
        )

        metrics.update(
            {
                "open_price": open_price,
                "high_price": high_price,
                "low_price": low_price,
                "close_price": close_price,
                "average_price": average_price or 0.0,
                "range_pct": range_pct,
                "intraday_change_pct": intraday_change_pct,
                "prior_close_change_pct": prior_close_change_pct,
                "gap_pct": gap_pct,
                "average_price_distance_pct": average_price_distance_pct,
                "true_range_proxy": true_range_proxy,
                "stop_pct": stop_pct,
                "stop_method": "single_session_true_range_proxy",
            }
        )

        score = 0.35
        if last_price > open_price:
            score += 0.14
            reasons.append("price_above_session_open")
        else:
            risk_flags.append("price_not_above_session_open")

        if last_price > close_price:
            score += 0.14
            reasons.append("price_above_prior_close")
        else:
            risk_flags.append("price_not_above_prior_close")

        if average_price and last_price >= average_price:
            score += 0.12
            reasons.append("price_above_average_traded_price")
        elif average_price:
            risk_flags.append("price_below_average_traded_price")
        else:
            risk_flags.append("average_price_missing")

        if self.min_range_pct <= range_pct <= self.max_range_pct:
            score += 0.10
            reasons.append("session_range_inside_risk_band")
        else:
            risk_flags.append("session_range_outside_risk_band")

        if gap_pct >= self.max_adverse_gap_pct:
            score += 0.07
            reasons.append("gap_risk_inside_limit")
        else:
            risk_flags.append("adverse_gap_too_large")

        if volume and volume > 0:
            score += 0.05
            reasons.append("volume_present")
        else:
            risk_flags.append("volume_missing")

        if reward_risk_ratio >= self.min_reward_risk_ratio:
            score += 0.03
            reasons.append("reward_risk_meets_threshold")
        else:
            risk_flags.append("reward_risk_below_threshold")

        confidence = round(min(score, 0.82), 4)
        action = (
            TradeAction.BUY
            if confidence >= self.min_confidence
            and reward_risk_ratio >= self.min_reward_risk_ratio
            and not self._has_hard_blocker(risk_flags)
            else TradeAction.NO_TRADE
        )
        if action == TradeAction.NO_TRADE:
            reasons.append("quality_filter_did_not_clear_buy_threshold")

        return ConservativeSignalAssessment(
            action=action,
            confidence=confidence,
            stop_loss=stop_loss,
            take_profit=take_profit,
            expected_risk=expected_risk,
            expected_reward=expected_reward,
            reward_risk_ratio=reward_risk_ratio,
            reasons=reasons,
            risk_flags=risk_flags,
            metrics=metrics,
        )

    @staticmethod
    def _first_quote_payload(quote: dict[str, Any]) -> dict[str, Any]:
        data = quote.get("data")
        if isinstance(data, dict) and data:
            first = next(iter(data.values()))
            if isinstance(first, dict):
                return first
        return {}

    @staticmethod
    def _positive_float(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @classmethod
    def _has_hard_blocker(cls, risk_flags: list[str]) -> bool:
        hard_blockers = {
            "insufficient_ohlc_for_strategy",
            "price_not_above_session_open",
            "price_not_above_prior_close",
            "price_below_average_traded_price",
            "session_range_outside_risk_band",
            "adverse_gap_too_large",
            "reward_risk_below_threshold",
        }
        return bool(hard_blockers.intersection(risk_flags))

    @staticmethod
    def _no_trade(
        risk_flags: list[str], metrics: dict[str, float | str | bool]
    ) -> ConservativeSignalAssessment:
        return ConservativeSignalAssessment(
            action=TradeAction.NO_TRADE,
            confidence=0.0,
            stop_loss=None,
            take_profit=None,
            expected_risk=0.0,
            expected_reward=0.0,
            reward_risk_ratio=0.0,
            reasons=["insufficient_quality_for_trade_candidate"],
            risk_flags=risk_flags,
            metrics=metrics,
        )
