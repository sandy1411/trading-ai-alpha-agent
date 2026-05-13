from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.intraday.config import IntradayShadowConfig
from app.intraday.models import MarketDataSnapshot, MarketRegime


@dataclass(frozen=True)
class RegimeResult:
    regime: MarketRegime
    reasons: list[str]
    metrics: dict[str, float | int | str | bool | None]


class MarketRegimeClassifier:
    def __init__(self, config: IntradayShadowConfig | None = None) -> None:
        self.config = config or IntradayShadowConfig.from_settings()

    def classify(
        self,
        snapshot: MarketDataSnapshot,
        *,
        timestamp: datetime | None = None,
    ) -> RegimeResult:
        reasons: list[str] = []
        metrics = {
            "index_trend": snapshot.index_trend,
            "sector_trend": snapshot.sector_trend,
            "market_breadth": snapshot.market_breadth,
            "gap_pct": snapshot.gap_pct,
            "atr_pct": (snapshot.atr / snapshot.last_price) if snapshot.atr and snapshot.last_price else None,
            "volume": snapshot.volume,
            "above_vwap": snapshot.vwap is not None and snapshot.last_price > snapshot.vwap,
            "below_vwap": snapshot.vwap is not None and snapshot.last_price < snapshot.vwap,
        }

        if snapshot.volume <= 0:
            return RegimeResult(MarketRegime.LOW_LIQUIDITY, ["volume_missing"], metrics)
        if snapshot.spread_pct is not None and snapshot.spread_pct > self.config.max_spread_pct:
            return RegimeResult(MarketRegime.LOW_LIQUIDITY, ["spread_too_wide"], metrics)
        atr_pct = metrics["atr_pct"]
        if atr_pct is not None and atr_pct > 0.025 and not self.config.allow_high_volatility_trades:
            return RegimeResult(MarketRegime.HIGH_VOLATILITY, ["atr_panic_zone"], metrics)

        bullish_votes = 0
        bearish_votes = 0
        if snapshot.index_trend is not None:
            if snapshot.index_trend > 0.002:
                bullish_votes += 1
                reasons.append("index_up")
            elif snapshot.index_trend < -0.002:
                bearish_votes += 1
                reasons.append("index_down")
        if snapshot.sector_trend is not None:
            if snapshot.sector_trend > 0.001:
                bullish_votes += 1
                reasons.append("sector_up")
            elif snapshot.sector_trend < -0.001:
                bearish_votes += 1
                reasons.append("sector_down")
        if snapshot.vwap is not None:
            if snapshot.last_price > snapshot.vwap:
                bullish_votes += 1
                reasons.append("price_above_vwap")
            elif snapshot.last_price < snapshot.vwap:
                bearish_votes += 1
                reasons.append("price_below_vwap")
        if snapshot.opening_range_high_15m and snapshot.last_price > snapshot.opening_range_high_15m:
            bullish_votes += 1
            reasons.append("above_opening_range")
        if snapshot.opening_range_low_15m and snapshot.last_price < snapshot.opening_range_low_15m:
            bearish_votes += 1
            reasons.append("below_opening_range")
        if snapshot.gap_pct is not None:
            if snapshot.gap_pct > 0.004:
                bullish_votes += 1
                reasons.append("gap_up")
            elif snapshot.gap_pct < -0.004:
                bearish_votes += 1
                reasons.append("gap_down")

        metrics["bullish_votes"] = bullish_votes
        metrics["bearish_votes"] = bearish_votes
        if bullish_votes >= 3 and bearish_votes == 0:
            return RegimeResult(MarketRegime.STRONG_BULLISH, reasons, metrics)
        if bearish_votes >= 3 and bullish_votes == 0:
            return RegimeResult(MarketRegime.STRONG_BEARISH, reasons, metrics)
        if bullish_votes > bearish_votes:
            return RegimeResult(MarketRegime.WEAK_BULLISH, reasons, metrics)
        if bearish_votes > bullish_votes:
            return RegimeResult(MarketRegime.WEAK_BEARISH, reasons, metrics)
        return RegimeResult(MarketRegime.SIDEWAYS, reasons or ["mixed_market"], metrics)

