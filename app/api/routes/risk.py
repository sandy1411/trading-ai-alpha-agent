from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.risk import RiskConfig

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/status")
def risk_status() -> dict:
    settings = get_settings()
    return {
        "risk_engine_required": settings.risk_engine_required,
        "long_only_mode": settings.long_only_mode,
        "risk_config": RiskConfig.from_settings(settings).model_dump(),
    }
