from __future__ import annotations

from app.schemas.common import StrictSchema


class SystemSummary(StrictSchema):
    app_name: str
    trading_mode: str
    live_trading_enabled: bool
    kill_switch: bool
    safety_errors: list[str]
