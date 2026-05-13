from __future__ import annotations

from app.intraday.pipeline import IntradayShadowPipeline, empty_professional_shadow_status


class ProfessionalIntradayShadowService:
    """Facade for dashboard/API access to the professional shadow core."""

    def __init__(self) -> None:
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


professional_intraday_shadow_service = ProfessionalIntradayShadowService()

