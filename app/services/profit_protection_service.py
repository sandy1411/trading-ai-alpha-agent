from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import Market
from app.db.models.shadow import ShadowTrainingSample
from app.db.session import SessionLocal


@dataclass(frozen=True)
class ProfitProtectionDecision:
    market: str
    symbol: str
    review_date: str
    opened_at: str
    latest_at: str
    peak_at: str
    entry_price: float
    latest_price: float
    peak_price: float
    quantity: int
    notional_inr: float
    current_pnl_inr: float
    current_pnl_pct: float
    peak_pnl_inr: float
    peak_pnl_pct: float
    giveback_inr: float
    giveback_pct_of_peak: float
    target_progress: float | None
    stop_loss: float | None
    take_profit: float | None
    stop_touched: bool
    target_touched: bool
    recommended_shadow_exit: str
    label: str
    urgency: str
    reason: str
    reentry_plan: str
    agent_votes: list[dict[str, str]]
    shadow_only: bool = True
    no_order_placement: bool = True

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


class ProfitProtectionService:
    """Tracks peak profit and giveback for shadow-only intraday exits."""

    agent_names = [
        "PeakProfitAgent",
        "GivebackGuardAgent",
        "ProfitBookingAgent",
        "StopTargetAgent",
        "ReEntryPatienceAgent",
    ]

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def summary(self, db: Session | None = None, *, limit_days: int = 5) -> dict[str, Any]:
        close_session = db is None
        session = db or SessionLocal()
        try:
            cutoff = datetime.now(UTC) - timedelta(days=limit_days + 2)
            samples = session.scalars(
                select(ShadowTrainingSample)
                .where(ShadowTrainingSample.sample_at >= cutoff)
                .order_by(ShadowTrainingSample.sample_at.asc())
            ).all()
            decisions = self.analyze_samples(samples, limit_days=limit_days)
            return self._summary_from_decisions(decisions, limit_days=limit_days)
        finally:
            if close_session:
                session.close()

    def analyze_samples(
        self,
        samples: list[ShadowTrainingSample],
        *,
        limit_days: int = 5,
    ) -> list[ProfitProtectionDecision]:
        grouped: dict[tuple[str, str, str], list[ShadowTrainingSample]] = {}
        for sample in samples:
            review_date = self._market_local_date(sample.market, sample.sample_at)
            grouped.setdefault((review_date, sample.market.value, sample.symbol), []).append(sample)

        decisions = [
            self._decision_from_group(review_date, market, symbol, group)
            for (review_date, market, symbol), group in grouped.items()
        ]
        decisions = [decision for decision in decisions if decision is not None]
        decisions.sort(key=lambda item: (item.review_date, item.urgency, item.giveback_inr), reverse=True)
        allowed_dates = sorted({decision.review_date for decision in decisions}, reverse=True)[:limit_days]
        return [decision for decision in decisions if decision.review_date in allowed_dates]

    def _decision_from_group(
        self,
        review_date: str,
        market: str,
        symbol: str,
        group: list[ShadowTrainingSample],
    ) -> ProfitProtectionDecision | None:
        ordered = sorted(group, key=lambda sample: self._aware_utc(sample.sample_at))
        if not ordered:
            return None
        first = ordered[0]
        latest = ordered[-1]
        peak = max(ordered, key=lambda sample: float(sample.hypothetical_pnl_inr or 0))
        assessment = self._assessment(latest) or self._assessment(first)
        stop_loss = self._float_or_none(assessment.get("stop_loss"))
        take_profit = self._float_or_none(assessment.get("take_profit"))
        stop_touched = any(
            stop_loss is not None
            and stop_loss > 0
            and float(sample.current_price or 0) <= stop_loss
            for sample in ordered
        )
        target_touched = any(
            take_profit is not None
            and take_profit > 0
            and float(sample.current_price or 0) >= take_profit
            for sample in ordered
        )
        current_pnl = float(latest.hypothetical_pnl_inr or 0)
        current_notional = float(latest.hypothetical_notional_inr or 0)
        peak_pnl = float(peak.hypothetical_pnl_inr or 0)
        giveback = max(peak_pnl - current_pnl, 0.0)
        giveback_pct = giveback / peak_pnl if peak_pnl > 0 else 0.0
        target_progress = self._target_progress(
            entry_price=float(first.entry_price or 0),
            latest_price=float(latest.current_price or 0),
            take_profit=take_profit,
        )
        peak_pct = (
            float(peak.hypothetical_pnl_pct or 0)
            if peak.hypothetical_pnl_pct is not None
            else 0.0
        )
        can_lock_profit = (
            peak_pnl >= self.settings.intraday_min_profit_lock_inr
            or peak_pct >= self.settings.intraday_min_profit_lock_pct
        )
        giveback_exit = (
            can_lock_profit
            and peak_pnl > 0
            and giveback_pct >= self.settings.intraday_profit_giveback_exit_pct
        )
        proactive_profit_booking = self._profit_booking_triggered(
            current_pnl=current_pnl,
            current_pnl_pct=float(latest.hypothetical_pnl_pct or 0),
            target_progress=target_progress,
        )
        action, label, urgency, reason = self._recommended_exit(
            stop_touched=stop_touched,
            target_touched=target_touched,
            giveback_exit=giveback_exit,
            proactive_profit_booking=proactive_profit_booking,
            can_lock_profit=can_lock_profit,
            current_pnl=current_pnl,
            peak_pnl=peak_pnl,
            giveback_pct=giveback_pct,
            target_progress=target_progress,
        )
        return ProfitProtectionDecision(
            market=market,
            symbol=symbol,
            review_date=review_date,
            opened_at=first.sample_at.isoformat(),
            latest_at=latest.sample_at.isoformat(),
            peak_at=peak.sample_at.isoformat(),
            entry_price=float(first.entry_price or 0),
            latest_price=float(latest.current_price or 0),
            peak_price=float(peak.current_price or 0),
            quantity=int(latest.hypothetical_quantity or 0),
            notional_inr=current_notional,
            current_pnl_inr=current_pnl,
            current_pnl_pct=float(latest.hypothetical_pnl_pct or 0),
            peak_pnl_inr=peak_pnl,
            peak_pnl_pct=peak_pct,
            giveback_inr=giveback,
            giveback_pct_of_peak=giveback_pct,
            target_progress=target_progress,
            stop_loss=stop_loss,
            take_profit=take_profit,
            stop_touched=stop_touched,
            target_touched=target_touched,
            recommended_shadow_exit=action,
            label=label,
            urgency=urgency,
            reason=reason,
            reentry_plan=self._reentry_plan(action),
            agent_votes=self._agent_votes(
                peak_pnl=peak_pnl,
                current_pnl=current_pnl,
                giveback=giveback,
                giveback_pct=giveback_pct,
                stop_touched=stop_touched,
                target_touched=target_touched,
                can_lock_profit=can_lock_profit,
                proactive_profit_booking=proactive_profit_booking,
            ),
        )

    def _summary_from_decisions(
        self,
        decisions: list[ProfitProtectionDecision],
        *,
        limit_days: int,
    ) -> dict[str, Any]:
        today = self._latest_date(decisions)
        today_decisions = [item for item in decisions if item.review_date == today]
        current_total = sum(item.current_pnl_inr for item in today_decisions)
        best_observed_total = sum(max(item.peak_pnl_inr, item.current_pnl_inr) for item in today_decisions)
        giveback_total = max(best_observed_total - current_total, 0.0)
        alerts = [
            item for item in today_decisions
            if item.recommended_shadow_exit
            in {
                "EXIT_PROFIT_GIVEBACK",
                "EXIT_PROFIT_BOOKING",
                "EXIT_TAKE_PROFIT",
                "EXIT_STOP_LOSS",
                "PROTECT_PROFIT",
            }
        ]
        alerts.sort(key=lambda item: (self._urgency_rank(item.urgency), item.giveback_inr), reverse=True)
        booked_profit = [
            item for item in today_decisions
            if item.recommended_shadow_exit
            in {"EXIT_TAKE_PROFIT", "EXIT_PROFIT_GIVEBACK", "EXIT_PROFIT_BOOKING"}
            and item.current_pnl_inr > 0
        ]
        booked_loss = [
            item for item in today_decisions
            if item.recommended_shadow_exit == "EXIT_STOP_LOSS"
        ]
        booked_profit.sort(key=lambda item: item.current_pnl_inr, reverse=True)
        booked_loss.sort(key=lambda item: item.current_pnl_inr)
        return {
            "mode": "SHADOW_ONLY_PROFIT_PROTECTION",
            "agent_names": self.agent_names,
            "generated_at": datetime.now(UTC).isoformat(),
            "lookback_days": limit_days,
            "latest_day": today,
            "current_total_pnl_inr": current_total,
            "best_observed_total_pnl_inr": best_observed_total,
            "giveback_from_best_observed_inr": giveback_total,
            "giveback_pct_of_best_observed": (
                giveback_total / best_observed_total if best_observed_total > 0 else 0.0
            ),
            "alerts_count": len(alerts),
            "high_urgency_count": len([item for item in alerts if item.urgency == "HIGH"]),
            "shadow_profit_booking": {
                "mode": "SHADOW_BOOKING_NOT_REAL_ORDER_EXECUTION",
                "booked_profit_count": len(booked_profit),
                "booked_profit_pnl_inr": sum(item.current_pnl_inr for item in booked_profit),
                "booked_loss_count": len(booked_loss),
                "booked_loss_pnl_inr": sum(item.current_pnl_inr for item in booked_loss),
                "booked_profit_rows": [item.model_dump() for item in booked_profit[:20]],
                "booked_loss_rows": [item.model_dump() for item in booked_loss[:20]],
                "plain_english": (
                    "Profit booking means the shadow exit rule says the position should have exited "
                    "with profit. Stop-loss booking means the shadow exit rule says the loss should "
                    "have been accepted instead of hoping."
                ),
                "shadow_only": True,
                "no_order_placement": True,
            },
            "decisions_today": [item.model_dump() for item in today_decisions],
            "alerts": [item.model_dump() for item in alerts[:20]],
            "plain_english": (
                "This tracks the best profit observed per stock and how much profit was later given back. "
                "It is shadow-only learning and cannot place orders."
            ),
            "safety": {
                "shadow_only": True,
                "no_order_placement": True,
                "uses_broker_orders": False,
            },
            "profit_booking_policy": {
                "enabled": self.settings.intraday_profit_booking_enabled,
                "target_progress_pct": self.settings.intraday_profit_booking_target_progress_pct,
                "min_pnl_inr": self.settings.intraday_profit_booking_min_pnl_inr,
                "min_pnl_pct": self.settings.intraday_profit_booking_min_pnl_pct,
                "plain_english": (
                    "From tomorrow's shadow session, a profit can be booked before the full target "
                    "when the move is meaningful and has reached enough of the target path."
                ),
            },
        }

    @staticmethod
    def _recommended_exit(
        *,
        stop_touched: bool,
        target_touched: bool,
        giveback_exit: bool,
        proactive_profit_booking: bool,
        can_lock_profit: bool,
        current_pnl: float,
        peak_pnl: float,
        giveback_pct: float,
        target_progress: float | None,
    ) -> tuple[str, str, str, str]:
        if stop_touched:
            return (
                "EXIT_STOP_LOSS",
                "Cut loss",
                "HIGH",
                "Stop-loss was touched in the shadow path.",
            )
        if target_touched:
            return (
                "EXIT_TAKE_PROFIT",
                "Take profit",
                "HIGH",
                "Profit target was touched in the shadow path.",
            )
        if proactive_profit_booking:
            progress_text = f"{target_progress:.0%}" if target_progress is not None else "enough"
            return (
                "EXIT_PROFIT_BOOKING",
                "Book profit",
                "HIGH",
                f"Profit is meaningful and has covered {progress_text} of the target path.",
            )
        if giveback_exit:
            return (
                "EXIT_PROFIT_GIVEBACK",
                "Exit on giveback",
                "HIGH",
                f"Peak profit was strong, then gave back {giveback_pct:.0%} of that profit.",
            )
        if can_lock_profit and current_pnl > 0:
            return (
                "PROTECT_PROFIT",
                "Protect profit",
                "MEDIUM",
                "The idea has enough profit to study a trailing/profit-lock exit.",
            )
        if peak_pnl > 0 and current_pnl <= 0:
            return (
                "MISSED_PROFIT_REVIEW",
                "Study missed profit",
                "MEDIUM",
                "The idea had profit earlier but no longer does; review exit timing.",
            )
        if current_pnl > 0:
            return ("HOLD_WINNER", "Hold winner", "LOW", "Positive but not yet at a profit-lock threshold.")
        if current_pnl < 0:
            return ("WATCH_LOSER", "Watch loser", "LOW", "Negative but no stop/exit event has fired.")
        return ("WAIT", "Wait", "LOW", "No meaningful profit/loss movement yet.")

    @staticmethod
    def _reentry_plan(action: str) -> str:
        if action in {"EXIT_TAKE_PROFIT", "EXIT_PROFIT_GIVEBACK", "EXIT_PROFIT_BOOKING", "PROTECT_PROFIT"}:
            return (
                "After an exit, wait for a fresh setup at a better reward/risk. "
                "Do not chase the same stock just because it moved."
            )
        if action == "EXIT_STOP_LOSS":
            return "Do not average down. Re-enter only after the weakness is invalidated by a fresh signal."
        return "Keep observing. Re-entry logic only matters after an exit event."

    @staticmethod
    def _agent_votes(
        *,
        peak_pnl: float,
        current_pnl: float,
        giveback: float,
        giveback_pct: float,
        stop_touched: bool,
        target_touched: bool,
        can_lock_profit: bool,
        proactive_profit_booking: bool,
    ) -> list[dict[str, str]]:
        votes = [
            {
                "agent": "PeakProfitAgent",
                "vote": "PROFIT_LOCK_CANDIDATE" if can_lock_profit else "KEEP_COLLECTING",
                "reason": f"Peak shadow P&L was {peak_pnl:.2f} INR.",
            },
            {
                "agent": "GivebackGuardAgent",
                "vote": "EXIT_REVIEW" if giveback_pct >= 0.35 and peak_pnl > 0 else "NO_GIVEBACK_EXIT",
                "reason": f"Current giveback is {giveback:.2f} INR ({giveback_pct:.0%} of peak).",
            },
            {
                "agent": "ProfitBookingAgent",
                "vote": "BOOK_PROFIT_NOW" if proactive_profit_booking else "NOT_IN_BOOKING_ZONE",
                "reason": "Books meaningful profit before the full target when the configured zone is reached.",
            },
            {
                "agent": "StopTargetAgent",
                "vote": "TARGET_OR_STOP_TOUCHED" if stop_touched or target_touched else "LEVELS_NOT_TOUCHED",
                "reason": f"target_touched={target_touched}, stop_touched={stop_touched}.",
            },
            {
                "agent": "ReEntryPatienceAgent",
                "vote": "WAIT_FOR_FRESH_SETUP" if peak_pnl > current_pnl else "NO_REENTRY_NEEDED",
                "reason": "Re-entry must wait for a fresh qualified setup after any exit.",
            },
        ]
        return votes

    def _profit_booking_triggered(
        self,
        *,
        current_pnl: float,
        current_pnl_pct: float,
        target_progress: float | None,
    ) -> bool:
        if not self.settings.intraday_profit_booking_enabled:
            return False
        if current_pnl <= 0 or target_progress is None:
            return False
        meaningful_profit = (
            current_pnl >= self.settings.intraday_profit_booking_min_pnl_inr
            or current_pnl_pct >= self.settings.intraday_profit_booking_min_pnl_pct
        )
        return (
            meaningful_profit
            and target_progress >= self.settings.intraday_profit_booking_target_progress_pct
        )

    @staticmethod
    def _target_progress(
        *,
        entry_price: float,
        latest_price: float,
        take_profit: float | None,
    ) -> float | None:
        if entry_price <= 0 or take_profit is None or take_profit <= entry_price:
            return None
        return (latest_price - entry_price) / (take_profit - entry_price)

    def _market_local_date(self, market: Market, value: datetime) -> str:
        timezone_name = self.settings.india_timezone if market == Market.INDIA else self.settings.us_timezone
        return self._aware_utc(value).astimezone(ZoneInfo(timezone_name)).date().isoformat()

    @staticmethod
    def _assessment(sample: ShadowTrainingSample) -> dict[str, Any]:
        metadata = sample.metadata_json or {}
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
    def _aware_utc(value: datetime) -> datetime:
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)

    @staticmethod
    def _latest_date(decisions: list[ProfitProtectionDecision]) -> str | None:
        dates = sorted({item.review_date for item in decisions}, reverse=True)
        return dates[0] if dates else None

    @staticmethod
    def _urgency_rank(value: str) -> int:
        return {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(value, 0)


profit_protection_service = ProfitProtectionService()
