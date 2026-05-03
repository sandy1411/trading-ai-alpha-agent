from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/snapshot")
def portfolio_snapshot() -> dict:
    settings = get_settings()
    return {
        "base_currency": settings.base_currency,
        "total_value_inr": settings.starting_capital_inr,
        "cash_inr": settings.starting_capital_inr,
        "positions": [],
    }
