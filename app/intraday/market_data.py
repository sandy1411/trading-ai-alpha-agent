from __future__ import annotations

from datetime import UTC, datetime
from statistics import mean
from typing import Any

from app.core.enums import Market
from app.intraday.config import IntradayShadowConfig
from app.intraday.models import Candle, DataQualityReport, MarketDataSnapshot


class MarketDataBuilder:
    """Builds normalized snapshots from provider payloads.

    It does not fabricate candle history. If candles are unavailable, the data-quality
    monitor blocks strategies that require candles.
    """

    @staticmethod
    def from_zerodha_quote(
        symbol: str,
        quote: dict[str, Any],
        *,
        timestamp: datetime | None = None,
        candles_1m: list[Candle] | None = None,
        candles_3m: list[Candle] | None = None,
        candles_5m: list[Candle] | None = None,
    ) -> MarketDataSnapshot:
        data = quote.get("data") if isinstance(quote, dict) else {}
        payload = next(iter(data.values())) if isinstance(data, dict) and data else {}
        payload = payload if isinstance(payload, dict) else {}
        ohlc = payload.get("ohlc") if isinstance(payload.get("ohlc"), dict) else {}
        last_price = float(payload.get("last_price") or 0)
        volume = float(payload.get("volume") or 0)
        vwap = _positive_float(payload.get("average_price"))
        close = _positive_float(ohlc.get("close"))
        open_price = _positive_float(ohlc.get("open"))
        gap_pct = ((open_price - close) / close) if open_price and close else None
        candles_1m_tuple = tuple(candles_1m or ())
        return MarketDataSnapshot(
            market=Market.INDIA,
            symbol=symbol.upper(),
            timestamp=timestamp or datetime.now(UTC),
            last_price=last_price,
            vwap=vwap,
            volume=volume,
            previous_day_high=_positive_float(ohlc.get("high")),
            previous_day_low=_positive_float(ohlc.get("low")),
            opening_range_high_15m=_range_high(candles_1m_tuple, 15),
            opening_range_low_15m=_range_low(candles_1m_tuple, 15),
            opening_range_high_30m=_range_high(candles_1m_tuple, 30),
            opening_range_low_30m=_range_low(candles_1m_tuple, 30),
            atr=calculate_atr(candles_5m or candles_1m or []),
            candles_1m=candles_1m_tuple,
            candles_3m=tuple(candles_3m or ()),
            candles_5m=tuple(candles_5m or ()),
            gap_pct=gap_pct,
            source="ZERODHA_KITE_QUOTE",
            raw=quote,
        )


class DataQualityMonitor:
    def __init__(self, config: IntradayShadowConfig | None = None) -> None:
        self.config = config or IntradayShadowConfig.from_settings()

    def check(self, snapshot: MarketDataSnapshot, *, now: datetime | None = None) -> DataQualityReport:
        checked_at = now or datetime.now(UTC)
        reasons: list[str] = []
        metrics: dict[str, float | int | str | bool | None] = {
            "last_price": snapshot.last_price,
            "volume": snapshot.volume,
            "spread_pct": snapshot.spread_pct,
            "feed_connected": snapshot.feed_connected,
            "candles_1m": len(snapshot.candles_1m),
            "candles_3m": len(snapshot.candles_3m),
            "candles_5m": len(snapshot.candles_5m),
        }
        age_seconds = (checked_at - snapshot.timestamp).total_seconds()
        metrics["age_seconds"] = age_seconds
        if age_seconds > self.config.max_data_age_seconds:
            reasons.append("stale_data")
        if snapshot.last_price <= 0:
            reasons.append("abnormal_price")
        if snapshot.volume <= 0:
            reasons.append("abnormal_volume")
        if not snapshot.feed_connected:
            reasons.append("feed_disconnected")
        if snapshot.candles_1m and _has_missing_candles(snapshot.candles_1m, expected_seconds=60):
            reasons.append("missing_1m_candle")
        if not snapshot.candles_1m:
            reasons.append("missing_1m_candles")
        if not snapshot.candles_3m:
            reasons.append("missing_3m_candles")
        if not snapshot.candles_5m:
            reasons.append("missing_5m_candles")
        if snapshot.spread_pct is not None and snapshot.spread_pct > self.config.max_spread_pct:
            reasons.append("spread_too_wide")
        if snapshot.bid is not None and snapshot.ask is not None and snapshot.bid > snapshot.ask:
            reasons.append("invalid_bid_ask")
        return DataQualityReport(ok=not reasons, reasons=list(dict.fromkeys(reasons)), metrics=metrics)


def calculate_vwap(candles: list[Candle] | tuple[Candle, ...]) -> float | None:
    values = []
    volumes = []
    for candle in candles:
        typical = (candle.high + candle.low + candle.close) / 3
        values.append(typical * candle.volume)
        volumes.append(candle.volume)
    total_volume = sum(volumes)
    return sum(values) / total_volume if total_volume > 0 else None


def calculate_atr(candles: list[Candle] | tuple[Candle, ...], period: int = 14) -> float | None:
    if len(candles) < 2:
        return None
    ordered = list(candles)[-period:]
    true_ranges = []
    previous_close = ordered[0].close
    for candle in ordered[1:]:
        true_ranges.append(
            max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        )
        previous_close = candle.close
    return mean(true_ranges) if true_ranges else None


def _has_missing_candles(candles: tuple[Candle, ...], *, expected_seconds: int) -> bool:
    ordered = sorted(candles, key=lambda candle: candle.timestamp)
    for previous, current in zip(ordered, ordered[1:]):
        if (current.timestamp - previous.timestamp).total_seconds() > expected_seconds * 1.5:
            return True
    return False


def _range_high(candles: tuple[Candle, ...], count: int) -> float | None:
    selected = candles[:count]
    return max((candle.high for candle in selected), default=None)


def _range_low(candles: tuple[Candle, ...], count: int) -> float | None:
    selected = candles[:count]
    return min((candle.low for candle in selected), default=None)


def _positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None

