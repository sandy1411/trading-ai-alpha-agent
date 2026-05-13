from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.intraday.config import IntradayShadowConfig
from app.intraday.models import Direction, FillStatus, MarketDataSnapshot, RiskApproval, ShadowOrder, Signal


class ShadowExecutionSimulator:
    """Research-only fill simulator. It never calls broker APIs."""

    can_place_live_orders = False
    is_broker_adapter = False

    def __init__(self, config: IntradayShadowConfig | None = None) -> None:
        self.config = config or IntradayShadowConfig.from_settings()

    def simulate(
        self,
        signal: Signal,
        approval: RiskApproval,
        snapshot: MarketDataSnapshot,
        *,
        now: datetime | None = None,
    ) -> ShadowOrder:
        if not approval.approved or approval.quantity <= 0:
            return ShadowOrder(
                shadow_order_id=str(uuid4()),
                signal_id=signal.signal_id,
                symbol=signal.symbol,
                direction=signal.direction,
                expected_entry=signal.entry_price,
                simulated_fill=None,
                quantity=0,
                slippage=0.0,
                spread=0.0,
                latency_ms=self.config.latency_ms,
                fill_status=FillStatus.REJECTED,
                rejection_reason="risk_not_approved",
                timestamp=now or datetime.now(UTC),
            )
        move_pct = abs(snapshot.last_price - signal.entry_price) / signal.entry_price
        if move_pct > self.config.max_entry_move_pct:
            return ShadowOrder(
                shadow_order_id=str(uuid4()),
                signal_id=signal.signal_id,
                symbol=signal.symbol,
                direction=signal.direction,
                expected_entry=signal.entry_price,
                simulated_fill=None,
                quantity=approval.quantity,
                slippage=0.0,
                spread=0.0,
                latency_ms=self.config.latency_ms,
                fill_status=FillStatus.MISSED,
                rejection_reason="price_moved_too_far",
                timestamp=now or datetime.now(UTC),
            )
        spread = max((snapshot.ask or signal.entry_price) - (snapshot.bid or signal.entry_price), 0.0)
        half_spread = spread / 2
        slippage = signal.entry_price * self.config.slippage_bps / 10_000
        if signal.direction == Direction.LONG:
            fill = signal.entry_price + slippage + half_spread
        else:
            fill = signal.entry_price - slippage - half_spread
        return ShadowOrder(
            shadow_order_id=str(uuid4()),
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            direction=signal.direction,
            expected_entry=signal.entry_price,
            simulated_fill=round(fill, 4),
            quantity=approval.quantity,
            slippage=round(slippage, 4),
            spread=round(spread, 4),
            latency_ms=self.config.latency_ms,
            fill_status=FillStatus.FILLED,
            timestamp=now or datetime.now(UTC),
        )

