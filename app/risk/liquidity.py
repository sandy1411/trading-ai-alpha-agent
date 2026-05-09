from __future__ import annotations

from collections.abc import Mapping

from app.core.config import Settings, get_settings
from app.core.enums import Market
from app.schemas.signal import TradeCandidate

QuoteMetrics = Mapping[str, float | int | None]


def liquidity_rejection_reason(
    candidate: TradeCandidate,
    *,
    settings: Settings | None = None,
    quote_metrics: QuoteMetrics | None = None,
    require_quote_metrics: bool = False,
) -> str | None:
    if "illiquid" in {flag.lower() for flag in candidate.risk_flags}:
        return "liquidity_check_failed"
    resolved = settings or get_settings()
    if quote_metrics is None:
        return "liquidity_metrics_missing" if require_quote_metrics else None

    intraday_volume = _metric(quote_metrics, "volume", "intraday_volume")
    average_daily_volume = _metric(quote_metrics, "average_daily_volume", "avg_daily_volume")
    if intraday_volume is None and average_daily_volume is None:
        return "liquidity_volume_missing" if require_quote_metrics else None
    if (
        intraday_volume is not None
        and intraday_volume < resolved.min_live_intraday_volume
    ):
        return "intraday_volume_too_low"
    if (
        average_daily_volume is not None
        and average_daily_volume < resolved.min_live_average_daily_volume
    ):
        return "average_daily_volume_too_low"

    notional_inr = _notional_inr(candidate, quote_metrics, average_daily_volume)
    if notional_inr is None:
        return "liquidity_notional_missing" if require_quote_metrics else None
    if notional_inr < resolved.min_live_average_daily_notional_inr:
        return "average_daily_notional_too_low"
    return None


def _notional_inr(
    candidate: TradeCandidate,
    quote_metrics: QuoteMetrics,
    average_daily_volume: float | None,
) -> float | None:
    configured = _metric(
        quote_metrics,
        "average_daily_notional_inr",
        "avg_daily_notional_inr",
        "notional_inr",
    )
    if configured is not None:
        return configured
    if average_daily_volume is None:
        return None
    price = _metric(quote_metrics, "last_price", "close", "mid_price") or candidate.entry_price
    fx_rate = 1.0
    if candidate.market == Market.US:
        fx_rate = _metric(quote_metrics, "fx_rate", "usd_inr") or 0
    if price <= 0 or fx_rate <= 0:
        return None
    return price * average_daily_volume * fx_rate


def _metric(quote_metrics: QuoteMetrics, *keys: str) -> float | None:
    for key in keys:
        value = quote_metrics.get(key)
        if value is None:
            continue
        numeric = float(value)
        if numeric < 0:
            return None
        return numeric
    return None
