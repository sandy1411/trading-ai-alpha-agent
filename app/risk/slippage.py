from __future__ import annotations

from collections.abc import Mapping

from app.core.config import Settings, get_settings
from app.schemas.signal import TradeCandidate

QuoteMetrics = Mapping[str, float | int | None]


def slippage_rejection_reason(
    candidate: TradeCandidate,
    *,
    settings: Settings | None = None,
    quote_metrics: QuoteMetrics | None = None,
    require_quote_metrics: bool = False,
) -> str | None:
    if "high_slippage" in {flag.lower() for flag in candidate.risk_flags}:
        return "slippage_check_failed"
    resolved = settings or get_settings()
    if quote_metrics is None:
        return "slippage_metrics_missing" if require_quote_metrics else None

    spread_pct = _spread_pct(quote_metrics)
    if spread_pct is None:
        return "bid_ask_spread_missing" if require_quote_metrics else None
    if spread_pct > resolved.max_live_bid_ask_spread_pct:
        return "bid_ask_spread_too_wide"

    estimated_slippage_pct = _metric(
        quote_metrics,
        "estimated_slippage_pct",
        "expected_slippage_pct",
        "slippage_pct",
    )
    if (
        estimated_slippage_pct is not None
        and estimated_slippage_pct > resolved.max_live_estimated_slippage_pct
    ):
        return "estimated_slippage_too_high"
    return None


def _spread_pct(quote_metrics: QuoteMetrics) -> float | None:
    configured = _metric(quote_metrics, "spread_pct", "bid_ask_spread_pct")
    if configured is not None:
        return configured
    spread_bps = _metric(quote_metrics, "spread_bps", "bid_ask_spread_bps")
    if spread_bps is not None:
        return spread_bps / 10_000
    bid = _metric(quote_metrics, "bid", "best_bid")
    ask = _metric(quote_metrics, "ask", "best_ask")
    if bid is None or ask is None:
        return None
    if bid <= 0 or ask <= 0 or ask < bid:
        return None
    mid = (bid + ask) / 2
    if mid <= 0:
        return None
    return (ask - bid) / mid


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
