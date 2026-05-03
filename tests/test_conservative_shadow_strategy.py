from __future__ import annotations

from app.core.enums import TradeAction
from app.strategies.conservative_shadow import ConservativeShadowStrategy


def test_conservative_shadow_strategy_defines_stop_target_and_rr() -> None:
    strategy = ConservativeShadowStrategy()
    quote = {
        "data": {
            "NSE:RELIANCE": {
                "last_price": 102.0,
                "average_price": 100.5,
                "volume": 100000,
                "ohlc": {"open": 100.0, "high": 103.0, "low": 99.5, "close": 99.0},
            }
        }
    }

    assessment = strategy.assess(quote, 102.0)

    assert assessment.action == TradeAction.BUY
    assert assessment.confidence >= strategy.min_confidence
    assert assessment.stop_loss is not None
    assert assessment.stop_loss < 102.0
    assert assessment.take_profit is not None
    assert assessment.take_profit > 102.0
    assert assessment.reward_risk_ratio >= strategy.min_reward_risk_ratio
    assert "observation_only_no_order_intent" in assessment.risk_flags


def test_conservative_shadow_strategy_fails_closed_without_ohlc() -> None:
    strategy = ConservativeShadowStrategy()
    quote = {"data": {"NSE:RELIANCE": {"last_price": 102.0}}}

    assessment = strategy.assess(quote, 102.0)

    assert assessment.action == TradeAction.NO_TRADE
    assert assessment.stop_loss is None
    assert "insufficient_ohlc_for_strategy" in assessment.risk_flags
