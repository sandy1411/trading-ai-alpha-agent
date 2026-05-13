from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict
from datetime import time

from app.core.enums import Market
from app.intraday.models import Candle, Direction, MarketDataSnapshot, MarketRegime, Signal
from app.intraday.regime import RegimeResult


class IntradayStrategy(ABC):
    strategy_name: str

    @abstractmethod
    def generate(
        self,
        snapshot: MarketDataSnapshot,
        regime: RegimeResult,
    ) -> Signal | None:
        raise NotImplementedError


class VWAPTrendLongStrategy(IntradayStrategy):
    strategy_name = "VWAP_TREND_LONG"

    def generate(self, snapshot: MarketDataSnapshot, regime: RegimeResult) -> Signal | None:
        if regime.regime not in {MarketRegime.STRONG_BULLISH, MarketRegime.WEAK_BULLISH}:
            return None
        if snapshot.vwap is None or snapshot.last_price <= snapshot.vwap:
            return None
        if snapshot.sector_trend is not None and snapshot.sector_trend < -0.001:
            return None
        if not _higher_high_higher_low(snapshot.candles_1m):
            return None
        if not _volume_confirmation(snapshot.candles_1m):
            return None
        if not _near_level(snapshot.last_price, snapshot.vwap, max_pct=0.008):
            return None
        stop = min(snapshot.vwap, snapshot.candles_1m[-2].low if len(snapshot.candles_1m) >= 2 else snapshot.vwap)
        risk = snapshot.last_price - stop
        if risk <= 0:
            return None
        target = snapshot.last_price + risk * 2
        return Signal.create(
            symbol=snapshot.symbol,
            market=snapshot.market,
            direction=Direction.LONG,
            strategy_name=self.strategy_name,
            regime_at_signal=regime.regime,
            entry_price=snapshot.last_price,
            stop_loss=round(stop, 2),
            target_price=round(target, 2),
            confidence_score=0.72,
            reason_codes=[
                "bullish_regime",
                "price_above_vwap",
                "higher_high_higher_low",
                "volume_confirmation",
                "pullback_near_vwap",
            ],
            invalidation_rules=["price_closes_below_vwap", "regime_turns_bearish"],
            candle_snapshot=_candle_snapshot(snapshot),
            market_snapshot=_market_snapshot(snapshot, regime),
            timestamp=snapshot.timestamp,
        )


class VWAPTrendShortStrategy(IntradayStrategy):
    strategy_name = "VWAP_TREND_SHORT"

    def generate(self, snapshot: MarketDataSnapshot, regime: RegimeResult) -> Signal | None:
        if regime.regime not in {MarketRegime.STRONG_BEARISH, MarketRegime.WEAK_BEARISH}:
            return None
        if snapshot.vwap is None or snapshot.last_price >= snapshot.vwap:
            return None
        if snapshot.sector_trend is not None and snapshot.sector_trend > 0.001:
            return None
        if not _lower_high_lower_low(snapshot.candles_1m):
            return None
        if not _volume_confirmation(snapshot.candles_1m):
            return None
        if not _near_level(snapshot.last_price, snapshot.vwap, max_pct=0.008):
            return None
        stop = max(snapshot.vwap, snapshot.candles_1m[-2].high if len(snapshot.candles_1m) >= 2 else snapshot.vwap)
        risk = stop - snapshot.last_price
        if risk <= 0:
            return None
        target = snapshot.last_price - risk * 2
        return Signal.create(
            symbol=snapshot.symbol,
            market=snapshot.market,
            direction=Direction.SHORT,
            strategy_name=self.strategy_name,
            regime_at_signal=regime.regime,
            entry_price=snapshot.last_price,
            stop_loss=round(stop, 2),
            target_price=round(target, 2),
            confidence_score=0.70,
            reason_codes=[
                "bearish_regime",
                "price_below_vwap",
                "lower_high_lower_low",
                "volume_confirmation",
                "pullback_failure_near_vwap",
            ],
            invalidation_rules=["price_closes_above_vwap", "regime_turns_bullish"],
            candle_snapshot=_candle_snapshot(snapshot),
            market_snapshot=_market_snapshot(snapshot, regime),
            timestamp=snapshot.timestamp,
        )


class OpeningRangeBreakoutStrategy(IntradayStrategy):
    strategy_name = "OPENING_RANGE_BREAKOUT_BREAKDOWN"

    def __init__(self, *, allow_first_five_minutes: bool = False) -> None:
        self.allow_first_five_minutes = allow_first_five_minutes

    def generate(self, snapshot: MarketDataSnapshot, regime: RegimeResult) -> Signal | None:
        if not self.allow_first_five_minutes and snapshot.timestamp.time() < time(9, 20):
            return None
        if regime.regime == MarketRegime.SIDEWAYS:
            return None
        if (
            snapshot.opening_range_high_15m
            and snapshot.last_price > snapshot.opening_range_high_15m
            and regime.regime in {MarketRegime.STRONG_BULLISH, MarketRegime.WEAK_BULLISH}
            and _volume_confirmation(snapshot.candles_1m)
        ):
            stop = snapshot.opening_range_low_15m or snapshot.vwap or snapshot.last_price
            risk = snapshot.last_price - stop
            if risk <= 0:
                return None
            return Signal.create(
                symbol=snapshot.symbol,
                market=snapshot.market,
                direction=Direction.LONG,
                strategy_name=self.strategy_name,
                regime_at_signal=regime.regime,
                entry_price=snapshot.last_price,
                stop_loss=round(stop, 2),
                target_price=round(snapshot.last_price + risk * 2, 2),
                confidence_score=0.73,
                reason_codes=["opening_range_breakout", "bullish_regime", "volume_confirmation"],
                invalidation_rules=["falls_back_inside_opening_range"],
                candle_snapshot=_candle_snapshot(snapshot),
                market_snapshot=_market_snapshot(snapshot, regime),
                timestamp=snapshot.timestamp,
            )
        if (
            snapshot.opening_range_low_15m
            and snapshot.last_price < snapshot.opening_range_low_15m
            and regime.regime in {MarketRegime.STRONG_BEARISH, MarketRegime.WEAK_BEARISH}
            and _volume_confirmation(snapshot.candles_1m)
        ):
            stop = snapshot.opening_range_high_15m or snapshot.vwap or snapshot.last_price
            risk = stop - snapshot.last_price
            if risk <= 0:
                return None
            return Signal.create(
                symbol=snapshot.symbol,
                market=snapshot.market,
                direction=Direction.SHORT,
                strategy_name=self.strategy_name,
                regime_at_signal=regime.regime,
                entry_price=snapshot.last_price,
                stop_loss=round(stop, 2),
                target_price=round(snapshot.last_price - risk * 2, 2),
                confidence_score=0.73,
                reason_codes=["opening_range_breakdown", "bearish_regime", "volume_confirmation"],
                invalidation_rules=["reclaims_opening_range"],
                candle_snapshot=_candle_snapshot(snapshot),
                market_snapshot=_market_snapshot(snapshot, regime),
                timestamp=snapshot.timestamp,
            )
        return None


def _higher_high_higher_low(candles: tuple[Candle, ...]) -> bool:
    if len(candles) < 3:
        return False
    a, b, c = candles[-3:]
    return b.high >= a.high and c.high >= b.high and b.low >= a.low and c.low >= b.low


def _lower_high_lower_low(candles: tuple[Candle, ...]) -> bool:
    if len(candles) < 3:
        return False
    a, b, c = candles[-3:]
    return b.high <= a.high and c.high <= b.high and b.low <= a.low and c.low <= b.low


def _volume_confirmation(candles: tuple[Candle, ...]) -> bool:
    if len(candles) < 4:
        return False
    baseline = sum(candle.volume for candle in candles[-4:-1]) / 3
    return candles[-1].volume >= baseline * 1.1 if baseline > 0 else False


def _near_level(price: float, level: float, *, max_pct: float) -> bool:
    if price <= 0 or level <= 0:
        return False
    return abs(price - level) / price <= max_pct


def _candle_snapshot(snapshot: MarketDataSnapshot) -> dict[str, object]:
    latest = snapshot.candles_1m[-1] if snapshot.candles_1m else None
    return asdict(latest) if latest else {}


def _market_snapshot(snapshot: MarketDataSnapshot, regime: RegimeResult) -> dict[str, object]:
    return {
        "market": snapshot.market.value if isinstance(snapshot.market, Market) else str(snapshot.market),
        "symbol": snapshot.symbol,
        "last_price": snapshot.last_price,
        "vwap": snapshot.vwap,
        "volume": snapshot.volume,
        "regime": regime.regime.value,
        "regime_reasons": regime.reasons,
        "spread_pct": snapshot.spread_pct,
    }

