from __future__ import annotations

from fastapi import APIRouter

from app.services.broker_service import broker_service

router = APIRouter(prefix="/brokers", tags=["brokers"])


@router.get("/status")
def broker_status() -> list[dict]:
    return [status.model_dump() for status in broker_service.statuses()]
