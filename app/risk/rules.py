from __future__ import annotations

from app.core.enums import TradeAction
from app.schemas.signal import TradeCandidate


def stop_loss_rejection_reason(candidate: TradeCandidate) -> str | None:
    if candidate.action in {TradeAction.BUY, TradeAction.SELL} and candidate.stop_loss is None:
        return "stop_loss_required"
    if candidate.stop_loss is not None and candidate.stop_loss == candidate.entry_price:
        return "stop_loss_equals_entry_price"
    return None


def reward_risk_rejection_reason(candidate: TradeCandidate, minimum_ratio: float) -> str | None:
    if candidate.reward_risk_ratio < minimum_ratio:
        return "reward_risk_ratio_below_minimum"
    return None
