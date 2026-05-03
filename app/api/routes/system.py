from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.enums import TradingMode
from app.core.errors import RiskRejectedError
from app.services.system_state_service import system_state_service

router = APIRouter(prefix="/system", tags=["system"])


class ModeUpdate(BaseModel):
    trading_mode: TradingMode


@router.get("/status")
def system_status() -> dict:
    settings = get_settings()
    state = system_state_service.get_state()
    return {
        "app_name": settings.app_name,
        "trading_mode": state.trading_mode,
        "live_trading_enabled": state.live_trading_enabled,
        "kill_switch": state.kill_switch,
        "safety_errors": settings.live_mode_safety_errors(),
    }


@router.post("/kill-switch/on")
def kill_switch_on() -> dict:
    state = system_state_service.enable_kill_switch()
    return {"kill_switch": state.kill_switch}


@router.post("/kill-switch/off")
def kill_switch_off() -> dict:
    state = system_state_service.disable_kill_switch()
    return {"kill_switch": state.kill_switch}


@router.get("/mode")
def get_mode() -> dict:
    return {"trading_mode": system_state_service.get_state().trading_mode}


@router.post("/mode")
def set_mode(update: ModeUpdate) -> dict:
    try:
        state = system_state_service.set_mode(update.trading_mode)
    except RiskRejectedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"trading_mode": state.trading_mode}
