from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from app.core.config import get_settings
from app.core.errors import TradingAlphaError
from app.core.security import mask_secret
from app.services.zerodha_token_service import (
    build_login_url,
    exchange_request_token,
    save_request_token,
    zerodha_auth_status,
)

router = APIRouter(prefix="/zerodha", tags=["zerodha"])


@router.get("/auth/status")
def zerodha_auth_status_endpoint() -> dict[str, object]:
    return zerodha_auth_status()


@router.get("/login")
def zerodha_login() -> RedirectResponse:
    return RedirectResponse(build_login_url())


@router.get("/callback")
def zerodha_callback(
    request_token: str | None = Query(default=None),
    action: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> dict[str, str | None]:
    exchange_status = "not_attempted"
    masked_access_token = None
    user_id = None
    if request_token:
        save_request_token(request_token)
        if get_settings().zerodha_auto_exchange_on_callback:
            try:
                result = exchange_request_token(request_token, write_env=True)
                exchange_status = "success"
                user_id = str(result.get("user_id") or "")
                masked_access_token = "stored_locally"
            except TradingAlphaError as exc:
                exchange_status = f"failed:{exc}"
    return {
        "status": status,
        "action": action,
        "request_token": mask_secret(request_token) if request_token else None,
        "access_token": masked_access_token,
        "exchange_status": exchange_status,
        "user_id": user_id,
        "next_step": (
            "If exchange_status is success, the access token is stored locally. "
            "If it failed, run: .\\.venv\\Scripts\\python.exe scripts\\zerodha_exchange_token.py --write-env"
        ),
        "safety": "Keep TRADING_MODE=SHADOW_LIVE, LIVE_TRADING_ENABLED=false, LIVE_ORDERS_ENABLED=false, KILL_SWITCH=true.",
    }
