from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.intraday.costs import CostModel
from app.intraday.models import (
    Direction,
    FillStatus,
    MarketDataSnapshot,
    ShadowOrder,
    Signal,
    VirtualPosition,
    VirtualPositionStatus,
)


class VirtualPositionManager:
    def __init__(self, cost_model: CostModel | None = None) -> None:
        self.cost_model = cost_model or CostModel()
        self.positions: dict[str, VirtualPosition] = {}

    def open_position(self, signal: Signal, order: ShadowOrder) -> VirtualPosition | None:
        if order.fill_status != FillStatus.FILLED or order.simulated_fill is None or order.quantity <= 0:
            return None
        position = VirtualPosition(
            position_id=str(uuid4()),
            symbol=signal.symbol,
            market=signal.market,
            direction=signal.direction,
            strategy=signal.strategy_name,
            regime_at_entry=signal.regime_at_signal,
            entry_price=order.simulated_fill,
            stop_loss=signal.stop_loss,
            target_price=signal.target_price,
            quantity=order.quantity,
            risk_amount=abs(order.simulated_fill - signal.stop_loss) * order.quantity,
            status=VirtualPositionStatus.OPEN,
            entry_reason=signal.reason_codes,
            opened_at=order.timestamp,
            current_price=order.simulated_fill,
        )
        self.positions[position.position_id] = position
        return position

    def update_mark(self, position_id: str, snapshot: MarketDataSnapshot) -> VirtualPosition:
        position = self.positions[position_id]
        position.current_price = snapshot.last_price
        gross = self._gross_pnl(position, snapshot.last_price)
        slippage_cost = abs(snapshot.last_price - position.entry_price) * 0
        if position.direction == Direction.LONG:
            buy_value = position.entry_price * position.quantity
            sell_value = snapshot.last_price * position.quantity
        else:
            buy_value = snapshot.last_price * position.quantity
            sell_value = position.entry_price * position.quantity
        charges = self.cost_model.calculate(
            buy_value=buy_value,
            sell_value=sell_value,
            slippage_cost=slippage_cost,
        ).total
        position.gross_pnl = gross
        position.charges = charges
        position.net_pnl = gross - charges
        position.current_pnl = position.net_pnl
        position.max_favorable_excursion = max(position.max_favorable_excursion, gross)
        position.max_adverse_excursion = min(position.max_adverse_excursion, gross)
        return position

    def close_position(
        self,
        position_id: str,
        *,
        exit_price: float,
        exit_reason: str,
        timestamp: datetime | None = None,
    ) -> VirtualPosition:
        position = self.positions[position_id]
        position.current_price = exit_price
        gross = self._gross_pnl(position, exit_price)
        if position.direction == Direction.LONG:
            buy_value = position.entry_price * position.quantity
            sell_value = exit_price * position.quantity
        else:
            buy_value = exit_price * position.quantity
            sell_value = position.entry_price * position.quantity
        charges = self.cost_model.calculate(buy_value=buy_value, sell_value=sell_value).total
        position.gross_pnl = gross
        position.charges = charges
        position.net_pnl = gross - charges
        position.current_pnl = position.net_pnl
        position.exit_reason = exit_reason
        position.closed_at = timestamp or datetime.now(UTC)
        if exit_reason == "STOP_LOSS":
            position.status = VirtualPositionStatus.STOPPED_OUT
        elif exit_reason == "TARGET_HIT":
            position.status = VirtualPositionStatus.TARGET_HIT
        elif exit_reason == "END_OF_DAY":
            position.status = VirtualPositionStatus.FORCE_CLOSED
        elif exit_reason == "INVALIDATED":
            position.status = VirtualPositionStatus.INVALIDATED
        else:
            position.status = VirtualPositionStatus.EXITED
        return position

    @staticmethod
    def _gross_pnl(position: VirtualPosition, price: float) -> float:
        if position.direction == Direction.LONG:
            return (price - position.entry_price) * position.quantity
        return (position.entry_price - price) * position.quantity

