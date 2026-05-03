from __future__ import annotations

from app.schemas.common import StrictSchema


class StrategyRead(StrictSchema):
    id: str
    name: str
    enabled: bool
    allocation_limits: dict = {}
