from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.core.config import Settings, get_settings
from app.db.models.shadow import ShadowObservation


@dataclass(frozen=True)
class ShadowExitDecision:
    action: str
    label: str
    urgency: str
    reason: str
    progress_to_target: float | None
    progress_to_stop: float | None
    reentry_plan: str
    shadow_only: bool = True
    no_order_placement: bool = True

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


class ShadowExitService:
    """Explains shadow-only exit and re-entry logic.

    This service never creates an order intent. It only labels what the bot
    should learn from an open shadow observation: hold, protect profit, cut loss,
    or wait for a cleaner re-entry after an exit.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def evaluate_observation(self, observation: ShadowObservation) -> ShadowExitDecision:
        assessment = self._assessment(observation)
        entry = float(observation.entry_price or 0)
        current = float(observation.current_price or 0)
        quantity = int(observation.hypothetical_quantity or 0)
        stop_loss = self._float_or_none(assessment.get("stop_loss"))
        take_profit = self._float_or_none(assessment.get("take_profit"))

        if entry <= 0 or current <= 0:
            return self._decision(
                action="NO_EXIT_LEVELS",
                label="Missing price",
                urgency="WAIT",
                reason="Entry/current price is missing, so this row is not useful for exit learning.",
            )
        if quantity <= 0:
            return self._decision(
                action="NO_POSITION_SIZE",
                label="No shadow size",
                urgency="WAIT",
                reason="The shadow budget is too small for a whole-share test at this price.",
                reentry_plan="Increase only the research budget if desired; never infer a live trade from a zero-size row.",
            )
        if stop_loss is None or stop_loss <= 0 or take_profit is None or take_profit <= 0:
            return self._decision(
                action="NO_EXIT_LEVELS",
                label="No trade",
                urgency="WAIT",
                reason="Stop loss or profit target is missing, so the idea must stay non-tradable.",
            )

        target_distance = max(take_profit - entry, 0)
        stop_distance = max(entry - stop_loss, 0)
        progress_to_target = self._safe_ratio(current - entry, target_distance)
        progress_to_stop = self._safe_ratio(entry - current, stop_distance)
        current_pnl = float(observation.hypothetical_pnl_inr or 0)
        current_notional = float(observation.hypothetical_notional_inr or 0)
        current_pnl_pct = current_pnl / current_notional if current_notional > 0 else 0.0

        if current <= stop_loss:
            return self._decision(
                action="EXIT_STOP_LOSS",
                label="Cut loss",
                urgency="HIGH",
                reason="Current price has touched or crossed the stop-loss level.",
                progress_to_target=progress_to_target,
                progress_to_stop=progress_to_stop,
                reentry_plan=(
                    "Do not average down. Reconsider only after a fresh signal with price reclaiming "
                    "the setup and a new stop-loss."
                ),
            )
        if current >= take_profit:
            return self._decision(
                action="EXIT_TAKE_PROFIT",
                label="Take profit",
                urgency="HIGH",
                reason="Current price has touched or crossed the profit target.",
                progress_to_target=progress_to_target,
                progress_to_stop=progress_to_stop,
                reentry_plan=(
                    "After profit-taking, wait for a fresh pullback/reclaim setup. Do not chase the same "
                    "stock at a worse reward/risk."
                ),
            )
        if self._profit_booking_triggered(
            current_pnl=current_pnl,
            current_pnl_pct=current_pnl_pct,
            progress_to_target=progress_to_target,
        ):
            return self._decision(
                action="EXIT_PROFIT_BOOKING",
                label="Book profit",
                urgency="HIGH",
                reason=(
                    "The idea has reached the configured profit-booking zone before target. "
                    "For shadow learning, record an exit instead of letting a good gain fade."
                ),
                progress_to_target=progress_to_target,
                progress_to_stop=progress_to_stop,
                reentry_plan=(
                    "After booking profit, wait for a fresh pullback/reclaim setup. "
                    "Do not immediately chase the same stock at a worse price."
                ),
            )
        if progress_to_target is not None and progress_to_target >= self.settings.intraday_exit_profit_lock_pct:
            return self._decision(
                action="LOCK_PROFIT_OR_TRAIL",
                label="Protect profit",
                urgency="MEDIUM",
                reason="The idea has covered most of the path to target; the bot should learn whether a trailing exit works better.",
                progress_to_target=progress_to_target,
                progress_to_stop=progress_to_stop,
                reentry_plan="If exited early, wait for a cleaner re-entry near support/VWAP with a new stop.",
            )
        if progress_to_stop is not None and progress_to_stop >= self.settings.intraday_exit_loss_watch_pct:
            return self._decision(
                action="WATCH_STOP_CLOSELY",
                label="Near stop",
                urgency="MEDIUM",
                reason="The idea is moving toward stop-loss; avoid adding size and learn if earlier exits reduce damage.",
                progress_to_target=progress_to_target,
                progress_to_stop=progress_to_stop,
                reentry_plan="Only re-enter after the original weakness is invalidated by a new high-quality signal.",
            )
        if current > entry:
            return self._decision(
                action="HOLD_WINNER",
                label="Hold winner",
                urgency="LOW",
                reason="The idea is positive but has not reached the profit-protection zone yet.",
                progress_to_target=progress_to_target,
                progress_to_stop=progress_to_stop,
                reentry_plan="No re-entry needed while the shadow idea remains open and valid.",
            )
        if current < entry:
            return self._decision(
                action="HOLD_WITH_STOP",
                label="Small loss",
                urgency="LOW",
                reason="The idea is down but still above stop-loss.",
                progress_to_target=progress_to_target,
                progress_to_stop=progress_to_stop,
                reentry_plan="Do not average down. Wait for either stop, recovery, or a fresh setup.",
            )
        return self._decision(
            action="WAIT_FOR_MOVE",
            label="Flat",
            urgency="LOW",
            reason="The idea has not moved enough to learn an exit outcome yet.",
            progress_to_target=progress_to_target,
            progress_to_stop=progress_to_stop,
            reentry_plan="Keep observing until price approaches target, stop, or time exit.",
        )

    def _profit_booking_triggered(
        self,
        *,
        current_pnl: float,
        current_pnl_pct: float,
        progress_to_target: float | None,
    ) -> bool:
        if not self.settings.intraday_profit_booking_enabled:
            return False
        if current_pnl <= 0 or progress_to_target is None:
            return False
        meaningful_profit = (
            current_pnl >= self.settings.intraday_profit_booking_min_pnl_inr
            or current_pnl_pct >= self.settings.intraday_profit_booking_min_pnl_pct
        )
        return (
            meaningful_profit
            and progress_to_target >= self.settings.intraday_profit_booking_target_progress_pct
        )

    @staticmethod
    def _assessment(observation: ShadowObservation) -> dict[str, Any]:
        metadata = observation.metadata_json or {}
        assessment = metadata.get("assessment") if isinstance(metadata, dict) else {}
        return assessment if isinstance(assessment, dict) else {}

    @staticmethod
    def _float_or_none(value: object) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_ratio(numerator: float, denominator: float) -> float | None:
        if denominator <= 0:
            return None
        return numerator / denominator

    @staticmethod
    def _decision(
        *,
        action: str,
        label: str,
        urgency: str,
        reason: str,
        progress_to_target: float | None = None,
        progress_to_stop: float | None = None,
        reentry_plan: str = "Wait for a fresh qualified setup before considering the same stock again.",
    ) -> ShadowExitDecision:
        return ShadowExitDecision(
            action=action,
            label=label,
            urgency=urgency,
            reason=reason,
            progress_to_target=progress_to_target,
            progress_to_stop=progress_to_stop,
            reentry_plan=reentry_plan,
        )


shadow_exit_service = ShadowExitService()
