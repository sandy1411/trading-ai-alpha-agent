from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.auth import require_control_auth
from app.services.market_intelligence_service import market_intelligence_service
from app.services.professional_intraday_shadow_service import professional_intraday_shadow_service
from app.services.shadow_readiness_service import shadow_readiness_service
from app.services.shadow_training_service import shadow_training_service

router = APIRouter(prefix="/shadow", tags=["shadow"])


@router.get("/status")
def shadow_status() -> dict:
    settings = shadow_training_service.settings
    return {
        "enabled": settings.shadow_training_enabled,
        "interval_seconds": settings.shadow_training_interval_seconds,
        "india_symbols": settings.shadow_india_symbol_list,
        "us_symbols": settings.shadow_us_symbol_list,
        "orders_placed": 0,
        "live_trading_enabled": settings.live_trading_enabled,
        "kill_switch": settings.kill_switch,
    }


@router.get("/readiness")
def shadow_readiness() -> dict:
    return shadow_readiness_service.status()


@router.get("/agents/status")
def shadow_agents_status() -> dict:
    return market_intelligence_service.summary()


@router.get("/professional/status")
def professional_shadow_status() -> dict:
    return professional_intraday_shadow_service.status()


@router.post("/run-cycle", dependencies=[Depends(require_control_auth)])
def run_shadow_cycle() -> dict:
    return shadow_training_service.run_cycle()
