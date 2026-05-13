from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

from app.intraday.config import IntradayShadowConfig
from app.intraday.models import Direction, MarketDataSnapshot, MarketRegime, VirtualPosition


@dataclass(frozen=True)
class ExitDecision:
    should_exit: bool
    reason: str = ""
    exit_price: float | None = None


class ExitManager:
    def __init__(self, config: IntradayShadowConfig | None = None) -> None:
        self.config = config or IntradayShadowConfig.from_settings()

    def evaluate(
        self,
        position: VirtualPosition,
        snapshot: MarketDataSnapshot,
        *,
        current_regime: MarketRegime,
        now: datetime | None = None,
    ) -> ExitDecision:
        checked_at = now or snapshot.timestamp
        local_time = checked_at.time()
        if position.direction == Direction.LONG:
            if snapshot.last_price <= position.stop_loss:
                return ExitDecision(True, "STOP_LOSS", position.stop_loss)
            if snapshot.last_price >= position.target_price:
                return ExitDecision(True, "TARGET_HIT", position.target_price)
            if snapshot.vwap is not None and snapshot.last_price < snapshot.vwap:
                return ExitDecision(True, "VWAP_BREAK", snapshot.last_price)
            if current_regime in {MarketRegime.STRONG_BEARISH, MarketRegime.WEAK_BEARISH}:
                return ExitDecision(True, "REGIME_CHANGE", snapshot.last_price)
        else:
            if snapshot.last_price >= position.stop_loss:
                return ExitDecision(True, "STOP_LOSS", position.stop_loss)
            if snapshot.last_price <= position.target_price:
                return ExitDecision(True, "TARGET_HIT", position.target_price)
            if snapshot.vwap is not None and snapshot.last_price > snapshot.vwap:
                return ExitDecision(True, "VWAP_BREAK", snapshot.last_price)
            if current_regime in {MarketRegime.STRONG_BULLISH, MarketRegime.WEAK_BULLISH}:
                return ExitDecision(True, "REGIME_CHANGE", snapshot.last_price)
        if local_time >= self._parse_time(self.config.force_close_time):
            return ExitDecision(True, "END_OF_DAY", snapshot.last_price)
        return ExitDecision(False)

    @staticmethod
    def _parse_time(value: str) -> time:
        hour, minute = [int(part) for part in value.split(":", 1)]
        return time(hour, minute)

