from __future__ import annotations

from app.core.enums import TradeAction
from app.schemas.position import OpenPosition
from app.schemas.signal import TradeCandidate


def existing_long_quantity(candidate: TradeCandidate, positions: list[OpenPosition]) -> int:
    for position in positions:
        if position.market == candidate.market and position.symbol == candidate.symbol:
            return max(position.quantity, 0)
    return 0


def long_only_rejection_reason(
    candidate: TradeCandidate, requested_quantity: int, positions: list[OpenPosition]
) -> str | None:
    if candidate.action != TradeAction.SELL:
        return None
    available = existing_long_quantity(candidate, positions)
    if available <= 0:
        return "sell_without_existing_long_position"
    if requested_quantity > available:
        return "sell_quantity_exceeds_existing_long_position"
    return None
