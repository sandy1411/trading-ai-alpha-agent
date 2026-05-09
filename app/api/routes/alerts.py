from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import require_control_auth
from app.core.errors import FailClosedError
from app.services.email_service import email_summary_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/daily-summary")
def daily_summary_preview() -> dict[str, str]:
    return {"summary": email_summary_service.build_daily_summary_text()}


@router.post("/daily-summary/email", dependencies=[Depends(require_control_auth)])
def send_daily_summary_email() -> dict[str, str | bool]:
    try:
        return email_summary_service.send_daily_summary()
    except FailClosedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
