from __future__ import annotations

from pydantic import Field

from app.schemas.common import StrictSchema
from app.schemas.position import OpenPosition


class PortfolioSnapshot(StrictSchema):
    total_value_inr: float = Field(gt=0)
    cash_inr: float = Field(ge=0)
    equity_exposure_inr: float = Field(default=0, ge=0)
    india_exposure_inr: float = Field(default=0, ge=0)
    us_exposure_inr: float = Field(default=0, ge=0)
    daily_pnl_inr: float = 0
    weekly_pnl_inr: float = 0
    monthly_drawdown_pct: float = Field(default=0, ge=0)
    total_drawdown_pct: float = Field(default=0, ge=0)
    positions: list[OpenPosition] = Field(default_factory=list)
    exposures_by_sector: dict[str, float] = Field(default_factory=dict)
    exposures_by_strategy: dict[str, float] = Field(default_factory=dict)
