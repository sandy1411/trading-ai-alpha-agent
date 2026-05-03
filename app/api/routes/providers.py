from __future__ import annotations

from fastapi import APIRouter

from app.services.provider_service import provider_service

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/status")
def provider_status() -> list[dict]:
    return [status.model_dump() for status in provider_service.statuses()]
