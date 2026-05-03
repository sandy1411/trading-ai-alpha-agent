from __future__ import annotations

from app.core.enums import Market
from app.core.errors import FailClosedError
from app.schemas.fx import FXRateStatus


def convert_to_inr(amount: float, market: Market, fx_status: FXRateStatus | None = None) -> float:
    if market == Market.INDIA:
        return amount
    if fx_status is None or not fx_status.is_fresh or fx_status.rate is None:
        raise FailClosedError("fresh_usd_inr_fx_required")
    return amount * fx_status.rate
