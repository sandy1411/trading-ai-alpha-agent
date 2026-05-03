from __future__ import annotations

from pydantic import Field

from app.core.enums import AssetClass, Market, TradeAction
from app.schemas.common import StrictSchema


class TradeCandidate(StrictSchema):
    market: Market
    symbol: str
    instrument_id: str
    asset_class: AssetClass
    action: TradeAction
    strategy_name: str
    confidence: float = Field(ge=0, le=1)
    entry_price: float = Field(gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    expected_risk: float = Field(ge=0)
    expected_reward: float = Field(ge=0)
    reward_risk_ratio: float = Field(ge=0)
    reasons: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
