from __future__ import annotations

from dataclasses import dataclass

from app.intraday.config import IntradayShadowConfig
from app.intraday.models import DataQualityReport, MarketDataSnapshot


NIFTY_50_SYMBOLS = {
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO",
    "BAJFINANCE", "BAJAJFINSV", "BEL", "BHARTIARTL", "CIPLA", "COALINDIA",
    "DRREDDY", "EICHERMOT", "ETERNAL", "GRASIM", "HCLTECH", "HDFCBANK",
    "HDFCLIFE", "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDUSINDBK",
    "INFY", "ITC", "JIOFIN", "JSWSTEEL", "KOTAKBANK", "LT", "M&M", "MARUTI",
    "NESTLEIND", "NTPC", "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SBIN",
    "SHRIRAMFIN", "SUNPHARMA", "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TCS",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",
}


@dataclass(frozen=True)
class UniverseDecision:
    allowed: bool
    reasons: list[str]


class UniverseFilter:
    def __init__(
        self,
        config: IntradayShadowConfig | None = None,
        allowed_symbols: set[str] | None = None,
    ) -> None:
        self.config = config or IntradayShadowConfig.from_settings()
        self.allowed_symbols = allowed_symbols or NIFTY_50_SYMBOLS

    def check(
        self,
        snapshot: MarketDataSnapshot,
        quality: DataQualityReport,
    ) -> UniverseDecision:
        reasons: list[str] = []
        symbol = snapshot.symbol.upper()
        if symbol not in self.allowed_symbols:
            reasons.append("symbol_not_in_nifty_liquid_universe")
        if not quality.ok:
            reasons.extend(f"data_quality:{reason}" for reason in quality.reasons)
        if snapshot.volume <= 0:
            reasons.append("low_volume")
        if snapshot.spread_pct is not None and snapshot.spread_pct > self.config.max_spread_pct:
            reasons.append("wide_spread")
        if snapshot.gap_pct is not None and abs(snapshot.gap_pct) > 0.05:
            reasons.append("abnormal_gap")
        if snapshot.last_price <= 0:
            reasons.append("invalid_price")
        return UniverseDecision(allowed=not reasons, reasons=list(dict.fromkeys(reasons)))

