from __future__ import annotations

from app.core.config import Settings, get_settings
from app.core.enums import Market
from app.core.errors import TradingAlphaError
from app.data_providers.zerodha_data import ZerodhaDataProvider
from app.intraday.market_data import MarketDataBuilder
from app.intraday.pipeline import IntradayShadowPipeline, empty_professional_shadow_status


class ProfessionalIntradayShadowService:
    """Facade for dashboard/API access to the professional shadow core."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.pipeline = IntradayShadowPipeline()

    def status(self) -> dict[str, object]:
        try:
            report = self.pipeline.today_report()
        except Exception as exc:
            return {
                **empty_professional_shadow_status(),
                "status": "REPORT_UNAVAILABLE",
                "error": str(exc),
            }
        return {
            "mode": "PROFESSIONAL_INTRADAY_SHADOW",
            "shadow_only": True,
            "orders_placed": 0,
            "status": "READY_FOR_SHADOW_SIGNALS",
            "daily_report": report,
            "live_readiness": report["live_readiness"],
        }

    def run_india_once(self, symbols: list[str] | None = None) -> dict[str, object]:
        provider = ZerodhaDataProvider(self.settings)
        selected_symbols = _clean_symbols(symbols or self.settings.shadow_india_symbol_list)
        results: list[dict[str, object]] = []
        blocked: list[dict[str, str]] = []
        if not selected_symbols:
            blocked.append({"symbol": "", "reason": "no_symbols_configured"})
        for symbol in selected_symbols:
            try:
                quote = provider.latest(symbol, Market.INDIA)
                snapshot = MarketDataBuilder.from_zerodha_quote(symbol, quote)
                results.append(self.pipeline.process_snapshot(snapshot))
            except TradingAlphaError as exc:
                blocked.append({"symbol": symbol, "reason": str(exc)})
            except Exception as exc:
                blocked.append({"symbol": symbol, "reason": f"provider_or_pipeline_error:{exc}"})
        return {
            "mode": "PROFESSIONAL_INTRADAY_SHADOW",
            "shadow_only": True,
            "orders_placed": 0,
            "symbols_requested": selected_symbols,
            "symbols_processed": len(results),
            "blocked": blocked,
            "results": results,
            "note": (
                "This consumes live Zerodha quote data and may still reject all trades "
                "if required real candles are missing."
            ),
        }


def _clean_symbols(symbols: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        normalized = symbol.strip().upper()
        if normalized and normalized not in seen:
            cleaned.append(normalized)
            seen.add(normalized)
    return cleaned


professional_intraday_shadow_service = ProfessionalIntradayShadowService()
