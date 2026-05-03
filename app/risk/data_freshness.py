from __future__ import annotations

from app.core.enums import FreshnessStatus, Market
from app.schemas.fx import FXRateStatus
from app.schemas.provider import ProviderHealth


def provider_freshness_reasons(providers: list[ProviderHealth]) -> list[str]:
    if not providers:
        return ["market_data_provider_missing"]
    reasons: list[str] = []
    for provider in providers:
        if not provider.is_healthy_for_live:
            reasons.append(f"provider_unhealthy:{provider.provider_name}")
    return reasons


def fx_rejection_reason(market: Market, fx_status: FXRateStatus | None) -> str | None:
    if market != Market.US:
        return None
    if fx_status is None:
        return "usd_inr_fx_missing"
    if fx_status.freshness_status == FreshnessStatus.MISSING or fx_status.rate is None:
        return "usd_inr_fx_missing"
    if not fx_status.is_fresh:
        return "usd_inr_fx_stale"
    return None
