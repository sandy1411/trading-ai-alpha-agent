from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import Market, OrderStatus
from app.core.security import mask_secret
from app.db.models.audit import AuditLog
from app.db.models.order import Order
from app.db.models.portfolio import PortfolioSnapshot as PortfolioSnapshotModel
from app.db.models.risk import RiskDecisionModel, RiskEvent
from app.db.models.shadow import DailyMarketReviewSnapshot, ShadowObservation
from app.db.models.signal import AgentSignal
from app.db.session import SessionLocal
from app.services.broker_service import broker_service
from app.services.intraday_model_training_service import intraday_model_training_service
from app.services.provider_service import provider_service
from app.services.shadow_readiness_service import shadow_readiness_service
from app.services.system_state_service import system_state_service
from app.services.zerodha_token_service import zerodha_auth_status
from app.strategies.intraday_shadow import IntradayShadowPlaybook


class PerformanceService:
    def daily_summary(self, db: Session | None = None) -> dict[str, Any]:
        close_session = db is None
        session = db or SessionLocal()
        try:
            start = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
            latest_portfolio = session.scalar(
                select(PortfolioSnapshotModel).order_by(PortfolioSnapshotModel.snapshot_at.desc())
            )
            order_counts = {
                status.value: session.scalar(
                    select(func.count()).select_from(Order).where(Order.status == status)
                )
                or 0
                for status in OrderStatus
            }
            decisions_today = session.scalar(
                select(func.count())
                .select_from(RiskDecisionModel)
                .where(RiskDecisionModel.created_at >= start)
            ) or 0
            risk_events_today = session.scalar(
                select(func.count()).select_from(RiskEvent).where(RiskEvent.created_at >= start)
            ) or 0
            total_observations = session.scalar(select(func.count()).select_from(ShadowObservation)) or 0
            total_observations_by_market = {
                market.value: session.scalar(
                    select(func.count())
                    .select_from(ShadowObservation)
                    .where(ShadowObservation.market == market)
                )
                or 0
                for market in Market
            }
            observations_today_by_market = {
                market.value: session.scalar(
                    select(func.count())
                    .select_from(ShadowObservation)
                    .where(
                        ShadowObservation.market == market,
                        ShadowObservation.last_marked_at >= start,
                    )
                )
                or 0
                for market in Market
            }
            recent_orders = session.scalars(
                select(Order).order_by(Order.created_at.desc()).limit(50)
            ).all()
            recent_observations = session.scalars(
                select(ShadowObservation)
                .order_by(ShadowObservation.last_marked_at.desc())
                .limit(100)
            ).all()
            recent_risk_events = session.scalars(
                select(RiskEvent).order_by(RiskEvent.created_at.desc()).limit(30)
            ).all()
            recent_audit_logs = session.scalars(
                select(AuditLog).order_by(AuditLog.created_at.desc()).limit(30)
            ).all()
            recent_signals = session.scalars(
                select(AgentSignal).order_by(AgentSignal.created_at.desc()).limit(50)
            ).all()
            signals_today = session.scalars(
                select(AgentSignal).where(AgentSignal.created_at >= start)
            ).all()
            active_observations = [
                observation
                for observation in recent_observations
                if observation.status == "OPEN_OBSERVATION"
            ]
            shadow_notional = sum(float(item.hypothetical_notional_inr) for item in active_observations)
            shadow_pnl = sum(float(item.hypothetical_pnl_inr) for item in active_observations)
            winners = len([item for item in active_observations if float(item.hypothetical_pnl_inr) > 0])
            losers = len([item for item in active_observations if float(item.hypothetical_pnl_inr) < 0])
            state = system_state_service.get_state()
            settings = get_settings()
            daily_review = self._daily_review_summary(session, settings)
            if close_session:
                session.commit()
            latest_cycle = self._latest_shadow_cycle()
            readiness = shadow_readiness_service.status()
            brokers = broker_service.statuses()
            providers = provider_service.statuses()
            intraday_model_report = intraday_model_training_service.status(session)
            studied_symbols_today = sorted({signal.symbol for signal in signals_today})
            improvement_actions = self._improvement_actions(
                latest_cycle=latest_cycle,
                readiness=readiness,
                studied_symbols_today=studied_symbols_today,
            )
            market_summaries = {
                market.value: self._market_summary(
                    market=market,
                    settings=settings,
                    readiness=readiness,
                    brokers=[broker.model_dump(mode="json") for broker in brokers],
                    providers=[provider.model_dump(mode="json") for provider in providers],
                    latest_cycle=latest_cycle,
                    active_observations=active_observations,
                    recent_observations=recent_observations,
                    signals_today=signals_today,
                    recent_risk_events=recent_risk_events,
                    total_observations=total_observations_by_market[market.value],
                    observations_today=observations_today_by_market[market.value],
                )
                for market in Market
            }
            training = self._training_summary(
                settings=settings,
                total_observations=total_observations,
                market_summaries=market_summaries,
                order_counts=order_counts,
                latest_cycle=latest_cycle,
                intraday_model_report=intraday_model_report,
            )
            strategy_lab = self._strategy_lab_summary(
                total_observations=total_observations,
                market_summaries=market_summaries,
            )
            return {
                "generated_at": datetime.now(UTC).isoformat(),
                "app_name": settings.app_name,
                "system": {
                    "trading_mode": state.trading_mode.value,
                    "live_trading_enabled": state.live_trading_enabled,
                    "kill_switch": state.kill_switch,
                    "safety_errors": settings.live_mode_safety_errors(),
                },
                "bot_activity": {
                    "live_trading_status": "DISABLED" if not state.live_trading_enabled else "ENABLED",
                    "shadow_status": self._shadow_status(latest_cycle, settings.shadow_training_interval_seconds),
                    "current_action": self._current_action(latest_cycle),
                    "last_cycle": latest_cycle,
                    "studied_symbols_today": studied_symbols_today,
                    "improvement_actions": improvement_actions,
                },
                "portfolio": {
                    "total_value_inr": float(latest_portfolio.total_value_inr)
                    if latest_portfolio
                    else settings.starting_capital_inr,
                    "cash_inr": float(latest_portfolio.cash_inr)
                    if latest_portfolio
                    else settings.starting_capital_inr,
                    "daily_pnl_inr": float(latest_portfolio.daily_pnl_inr)
                    if latest_portfolio
                    else 0.0,
                    "monthly_drawdown_pct": float(latest_portfolio.monthly_drawdown_pct)
                    if latest_portfolio
                    else 0.0,
                    "total_drawdown_pct": float(latest_portfolio.total_drawdown_pct)
                    if latest_portfolio
                    else 0.0,
                },
                "orders": order_counts,
                "recent_orders": [
                    {
                        "id": order.id,
                        "created_at": order.created_at.isoformat(),
                        "market": order.market.value,
                        "broker": order.broker.value,
                        "symbol": order.symbol,
                        "side": order.side.value,
                        "quantity": order.quantity,
                        "order_type": order.order_type.value,
                        "limit_price": self._float_or_none(order.limit_price),
                        "status": order.status.value,
                        "reconciliation_state": order.reconciliation_state.value,
                        "broker_order_id": order.broker_order_id,
                    }
                    for order in recent_orders
                ],
                "risk": {
                    "decisions_today": decisions_today,
                    "risk_events_today": risk_events_today,
                    "max_risk_per_trade_pct": settings.max_risk_per_trade_pct,
                    "max_daily_loss_pct": settings.max_daily_loss_pct,
                    "max_total_drawdown_pct": settings.max_total_drawdown_pct,
                },
                "shadow": {
                    "hypothesis_notional_per_symbol_inr": settings.shadow_hypothesis_notional_inr,
                    "active_observations": len(active_observations),
                    "hypothetical_notional_inr": shadow_notional,
                    "hypothetical_pnl_inr": shadow_pnl,
                    "hypothetical_pnl_pct": shadow_pnl / shadow_notional if shadow_notional else 0,
                    "winners": winners,
                    "losers": losers,
                    "flat": max(len(active_observations) - winners - losers, 0),
                    "recent_observations": [
                        {
                            "id": observation.id,
                            "market": observation.market.value,
                            "symbol": observation.symbol,
                            "status": observation.status,
                            "opened_at": observation.opened_at.isoformat(),
                            "last_marked_at": observation.last_marked_at.isoformat(),
                            "entry_price": float(observation.entry_price),
                            "current_price": float(observation.current_price),
                            "hypothetical_quantity": observation.hypothetical_quantity,
                            "hypothetical_notional_inr": float(
                                observation.hypothetical_notional_inr
                            ),
                            "hypothetical_pnl_inr": float(observation.hypothetical_pnl_inr),
                            "hypothetical_pnl_pct": float(observation.hypothetical_pnl_pct),
                            "notes": observation.notes,
                            "assessment": self._assessment_from_observation(observation),
                        }
                        for observation in recent_observations
                    ],
                },
                "markets": market_summaries,
                "daily_review": daily_review,
                "training": training,
                "model_training": intraday_model_report,
                "strategy_lab": strategy_lab,
                "recent_signals": [
                    {
                        "id": signal.id,
                        "created_at": signal.created_at.isoformat(),
                        "market": signal.market.value,
                        "symbol": signal.symbol,
                        "action": signal.action.value,
                        "confidence": float(signal.confidence),
                        "strategy_name": signal.strategy_name,
                        "data_sources": signal.data_sources,
                    }
                    for signal in recent_signals
                ],
                "recent_risk_events": [
                    {
                        "id": event.id,
                        "created_at": event.created_at.isoformat(),
                        "market": event.market.value if event.market else "",
                        "event_type": event.event_type,
                        "severity": event.severity,
                        "message": event.message,
                    }
                    for event in recent_risk_events
                ],
                "recent_audit_logs": [
                    {
                        "id": audit.id,
                        "created_at": audit.created_at.isoformat(),
                        "actor": audit.actor,
                        "action": audit.action,
                        "entity_type": audit.entity_type,
                        "message": audit.message,
                    }
                    for audit in recent_audit_logs
                ],
                "readiness": readiness,
                "zerodha_auth": zerodha_auth_status(settings),
                "email": {
                    "enabled": settings.enable_email_summary,
                    "smtp_host": settings.email_smtp_host,
                    "smtp_port": settings.email_smtp_port,
                    "smtp_use_tls": settings.email_smtp_use_tls,
                    "smtp_require_auth": settings.email_smtp_require_auth,
                    "recipient_configured": bool(settings.email_to),
                    "recipient_masked": self._mask_email(settings.email_to),
                    "local_preview_url": "http://127.0.0.1:8025"
                    if settings.email_smtp_host in {"localhost", "127.0.0.1"}
                    and settings.email_smtp_port == 1025
                    else "",
                },
                "brokers": [status.model_dump(mode="json") for status in brokers],
                "providers": [status.model_dump(mode="json") for status in providers],
            }
        finally:
            if close_session:
                session.close()

    @staticmethod
    def _float_or_none(value: object) -> float | None:
        return None if value is None else float(value)

    @staticmethod
    def _assessment_from_observation(observation: ShadowObservation) -> dict[str, Any]:
        metadata = observation.metadata_json or {}
        assessment = metadata.get("assessment")
        return assessment if isinstance(assessment, dict) else {}

    @staticmethod
    def _market_summary(
        *,
        market: Market,
        settings: Any,
        readiness: dict[str, Any],
        brokers: list[dict[str, Any]],
        providers: list[dict[str, Any]],
        latest_cycle: dict[str, Any] | None,
        active_observations: list[ShadowObservation],
        recent_observations: list[ShadowObservation],
        signals_today: list[AgentSignal],
        recent_risk_events: list[RiskEvent],
        total_observations: int,
        observations_today: int,
    ) -> dict[str, Any]:
        market_observations = [
            observation for observation in active_observations if observation.market == market
        ]
        market_recent_observations = [
            observation for observation in recent_observations if observation.market == market
        ]
        notional = sum(float(item.hypothetical_notional_inr) for item in market_observations)
        pnl = sum(float(item.hypothetical_pnl_inr) for item in market_observations)
        winners = len([item for item in market_observations if float(item.hypothetical_pnl_inr) > 0])
        losers = len([item for item in market_observations if float(item.hypothetical_pnl_inr) < 0])
        cycle_key = market.value.lower()
        cycle = latest_cycle.get(cycle_key, {}) if latest_cycle else {}
        configured_symbols = (
            settings.shadow_india_symbol_list
            if market == Market.INDIA
            else settings.shadow_us_symbol_list
        )
        readiness_key = (
            "ready_for_india_shadow_now"
            if market == Market.INDIA
            else "ready_for_us_shadow_now"
        )
        market_checks = [
            check
            for check in readiness.get("checks", [])
            if (
                market == Market.INDIA
                and (
                    check.get("name", "").startswith("india")
                    or "zerodha" in check.get("name", "")
                )
            )
            or (
                market == Market.US
                and (
                    check.get("name", "").startswith("us")
                    or "alpaca" in check.get("name", "")
                    or "fx" in check.get("name", "")
                )
            )
        ]
        return {
            "market": market.value,
            "display_name": "India" if market == Market.INDIA else "United States",
            "timezone": settings.india_timezone if market == Market.INDIA else settings.us_timezone,
            "currency": "INR" if market == Market.INDIA else "USD",
            "reporting_currency": settings.base_currency,
            "shadow_ready_now": bool(readiness.get(readiness_key)),
            "configured_symbols": configured_symbols,
            "configured_symbol_count": len(configured_symbols),
            "observed_last_cycle": cycle.get("observed", 0) if isinstance(cycle, dict) else 0,
            "blocked_last_cycle": cycle.get("blocked", []) if isinstance(cycle, dict) else [],
            "symbols_last_cycle": cycle.get("symbols", []) if isinstance(cycle, dict) else [],
            "active_observations": len(market_observations),
            "recent_observations": len(market_recent_observations),
            "total_observations": total_observations,
            "observations_today": observations_today,
            "hypothetical_notional_inr": notional,
            "hypothetical_pnl_inr": pnl,
            "hypothetical_pnl_pct": pnl / notional if notional else 0.0,
            "winners": winners,
            "losers": losers,
            "flat": max(len(market_observations) - winners - losers, 0),
            "signals_today": len([signal for signal in signals_today if signal.market == market]),
            "latest_marked_at": (
                max(observation.last_marked_at for observation in market_recent_observations).isoformat()
                if market_recent_observations
                else None
            ),
            "brokers": [broker for broker in brokers if broker.get("market") == market.value],
            "providers": [provider for provider in providers if provider.get("market") == market.value],
            "readiness_checks": market_checks,
            "risk_events_recent": len(
                [event for event in recent_risk_events if event.market == market]
            ),
        }

    @staticmethod
    def _training_summary(
        *,
        settings: Any,
        total_observations: int,
        market_summaries: dict[str, dict[str, Any]],
        order_counts: dict[str, int],
        latest_cycle: dict[str, Any] | None,
        intraday_model_report: dict[str, Any],
    ) -> dict[str, Any]:
        minimum_review_samples_per_market = 100
        total_real_orders = sum(order_counts.values())
        market_progress = {
            market: min(
                summary["total_observations"] / minimum_review_samples_per_market,
                1.0,
            )
            for market, summary in market_summaries.items()
        }
        checks = [
            {
                "name": "collect_india_shadow_samples",
                "passed": market_summaries[Market.INDIA.value]["total_observations"]
                >= minimum_review_samples_per_market,
                "detail": (
                    f"{market_summaries[Market.INDIA.value]['total_observations']}/"
                    f"{minimum_review_samples_per_market}"
                ),
            },
            {
                "name": "collect_us_shadow_samples",
                "passed": market_summaries[Market.US.value]["total_observations"]
                >= minimum_review_samples_per_market,
                "detail": (
                    f"{market_summaries[Market.US.value]['total_observations']}/"
                    f"{minimum_review_samples_per_market}"
                ),
            },
            {
                "name": "real_orders_must_remain_zero",
                "passed": total_real_orders == 0,
                "detail": str(total_real_orders),
            },
            {
                "name": "stop_target_rr_recorded",
                "passed": total_observations > 0,
                "detail": "Each new shadow observation stores deterministic stop, target, and reward/risk metadata.",
            },
        ]
        return {
            "phase": "SHADOW_DATA_COLLECTION",
            "strategy_name": "conservative_shadow_v1",
            "promotion_status": "LIVE_BLOCKED_BY_DESIGN",
            "minimum_review_samples_per_market": minimum_review_samples_per_market,
            "total_observations": total_observations,
            "market_progress": market_progress,
            "checks": checks,
            "current_loop_interval_seconds": settings.shadow_training_interval_seconds,
            "last_cycle_status": latest_cycle.get("status") if latest_cycle else "NO_CYCLE_RECORDED",
            "intraday_model": intraday_model_report,
            "model_notes": [
                "The engine is collecting real-data shadow observations for calibration.",
                f"Intraday model training status: {intraday_model_report['status']}.",
                "No learned model is allowed to place orders.",
                "Promotion requires manual review, risk approval, reconciliation, and compliance gates.",
            ],
        }

    @staticmethod
    def _strategy_lab_summary(
        *,
        total_observations: int,
        market_summaries: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        playbook = IntradayShadowPlaybook()
        summary = playbook.dashboard_summary()
        india_samples = market_summaries[Market.INDIA.value]["total_observations"]
        us_samples = market_summaries[Market.US.value]["total_observations"]
        enough_samples = all(
            samples >= playbook.min_samples_per_profile
            for samples in [india_samples, us_samples]
        )
        summary["evidence"] = {
            "total_shadow_observations": total_observations,
            "india_shadow_observations": india_samples,
            "us_shadow_observations": us_samples,
            "sample_gate_passed": enough_samples,
            "sample_gate_detail": (
                f"India {india_samples}/{playbook.min_samples_per_profile}, "
                f"US {us_samples}/{playbook.min_samples_per_profile}"
            ),
        }
        summary["live_readiness"] = {
            "status": "NOT_READY",
            "reason": (
                "Intraday work remains shadow-only until evidence, compliance, "
                "broker health, risk approval, and reconciliation gates are complete."
            ),
        }
        return summary

    @classmethod
    def _daily_review_summary(cls, session: Session, settings: Any) -> dict[str, Any]:
        market_reviews: dict[str, dict[str, Any]] = {}
        for market in Market:
            review_date, start_utc, end_utc = cls._market_day_window(
                settings=settings,
                market=market,
                days_ago=1,
            )
            observations = session.scalars(
                select(ShadowObservation)
                .where(
                    ShadowObservation.market == market,
                    ShadowObservation.last_marked_at >= start_utc,
                    ShadowObservation.last_marked_at < end_utc,
                )
                .order_by(ShadowObservation.last_marked_at.desc())
            ).all()
            signals = session.scalars(
                select(AgentSignal)
                .where(
                    AgentSignal.market == market,
                    AgentSignal.created_at >= start_utc,
                    AgentSignal.created_at < end_utc,
                )
                .order_by(AgentSignal.created_at.desc())
            ).all()
            orders = session.scalars(
                select(Order)
                .where(
                    Order.market == market,
                    Order.created_at >= start_utc,
                    Order.created_at < end_utc,
                )
                .order_by(Order.created_at.desc())
            ).all()
            risk_events = session.scalars(
                select(RiskEvent)
                .where(
                    RiskEvent.market == market,
                    RiskEvent.created_at >= start_utc,
                    RiskEvent.created_at < end_utc,
                )
                .order_by(RiskEvent.created_at.desc())
            ).all()
            market_reviews[market.value] = cls._daily_market_review(
                market=market,
                review_date=review_date,
                observations=observations,
                signals=signals,
                orders=orders,
                risk_events=risk_events,
            )
            cls._upsert_daily_market_review_snapshot(
                session=session,
                review=market_reviews[market.value],
            )
        history = cls._daily_review_history(session)
        return {
            "title": "Yesterday's Shadow Review",
            "mode": "SHADOW_REVIEW_NOT_REALIZED_TRADING_PNL",
            "generated_at": datetime.now(UTC).isoformat(),
            "markets": market_reviews,
            "history": history,
            "summary": (
                "Brief daily review of shadow observations. P&L is hypothetical unless real orders "
                "are explicitly shown."
            ),
        }

    @classmethod
    def _daily_market_review(
        cls,
        *,
        market: Market,
        review_date: str,
        observations: list[ShadowObservation],
        signals: list[AgentSignal],
        orders: list[Order],
        risk_events: list[RiskEvent],
    ) -> dict[str, Any]:
        symbols = sorted({item.symbol for item in observations}.union({item.symbol for item in signals}))
        notional = sum(float(item.hypothetical_notional_inr) for item in observations)
        pnl = sum(float(item.hypothetical_pnl_inr) for item in observations)
        winners = len([item for item in observations if float(item.hypothetical_pnl_inr) > 0])
        losers = len([item for item in observations if float(item.hypothetical_pnl_inr) < 0])
        flat = max(len(observations) - winners - losers, 0)
        buy_signals = len([item for item in signals if item.action.value == "BUY"])
        no_trade_signals = len([item for item in signals if item.action.value == "NO_TRADE"])
        best = max(observations, key=lambda item: float(item.hypothetical_pnl_inr), default=None)
        worst = min(observations, key=lambda item: float(item.hypothetical_pnl_inr), default=None)
        status = "NO_DATA"
        if observations:
            if pnl > 0:
                status = "NET_POSITIVE_SHADOW"
            elif pnl < 0:
                status = "NET_NEGATIVE_SHADOW"
            else:
                status = "FLAT_SHADOW"

        lessons = cls._daily_lessons(
            observations=observations,
            signals=signals,
            orders=orders,
            pnl=pnl,
            risk_events=risk_events,
        )
        next_focus = cls._daily_next_focus(observations=observations, signals=signals, pnl=pnl)
        return {
            "market": market.value,
            "display_name": "India" if market == Market.INDIA else "United States",
            "review_date": review_date,
            "status": status,
            "brief": cls._daily_brief(
                market=market,
                observations=observations,
                signals=signals,
                orders=orders,
                pnl=pnl,
            ),
            "shadow_hypotheses": len(observations),
            "signals": len(signals),
            "buy_hypotheses": buy_signals,
            "no_trade_signals": no_trade_signals,
            "real_orders": len(orders),
            "symbols_studied": symbols,
            "hypothetical_notional_inr": notional,
            "hypothetical_pnl_inr": pnl,
            "hypothetical_pnl_pct": pnl / notional if notional else 0.0,
            "winners": winners,
            "losers": losers,
            "flat": flat,
            "best_symbol": cls._symbol_pnl(best),
            "worst_symbol": cls._symbol_pnl(worst),
            "lessons": lessons,
            "next_focus": next_focus,
            "risk_events": len(risk_events),
        }

    @staticmethod
    def _market_day_window(
        *,
        settings: Any,
        market: Market,
        days_ago: int,
    ) -> tuple[str, datetime, datetime]:
        timezone_name = settings.india_timezone if market == Market.INDIA else settings.us_timezone
        timezone = ZoneInfo(timezone_name)
        review_date = datetime.now(timezone).date() - timedelta(days=days_ago)
        start_local = datetime.combine(review_date, time.min, tzinfo=timezone)
        end_local = start_local + timedelta(days=1)
        return (
            review_date.isoformat(),
            start_local.astimezone(UTC),
            end_local.astimezone(UTC),
        )

    @staticmethod
    def _upsert_daily_market_review_snapshot(session: Session, review: dict[str, Any]) -> None:
        review_date = datetime.strptime(str(review["review_date"]), "%Y-%m-%d").date()
        snapshot = session.scalar(
            select(DailyMarketReviewSnapshot).where(
                DailyMarketReviewSnapshot.market == Market(str(review["market"])),
                DailyMarketReviewSnapshot.review_date == review_date,
            )
        )
        if snapshot is None:
            snapshot = DailyMarketReviewSnapshot(
                market=Market(str(review["market"])),
                review_date=review_date,
            )
            session.add(snapshot)
        snapshot.status = str(review["status"])
        snapshot.signals = int(review["signals"])
        snapshot.shadow_hypotheses = int(review["shadow_hypotheses"])
        snapshot.real_orders = int(review["real_orders"])
        snapshot.buy_hypotheses = int(review["buy_hypotheses"])
        snapshot.no_trade_signals = int(review["no_trade_signals"])
        snapshot.winners = int(review["winners"])
        snapshot.losers = int(review["losers"])
        snapshot.flat = int(review["flat"])
        snapshot.hypothetical_notional_inr = float(review["hypothetical_notional_inr"])
        snapshot.hypothetical_pnl_inr = float(review["hypothetical_pnl_inr"])
        snapshot.hypothetical_pnl_pct = float(review["hypothetical_pnl_pct"])
        snapshot.payload = {
            "brief": review["brief"],
            "symbols_studied": review["symbols_studied"],
            "best_symbol": review["best_symbol"],
            "worst_symbol": review["worst_symbol"],
            "lessons": review["lessons"],
            "next_focus": review["next_focus"],
            "risk_events": review["risk_events"],
        }
        session.flush()

    @staticmethod
    def _daily_review_history(session: Session, limit_days: int = 14) -> list[dict[str, Any]]:
        snapshots = session.scalars(
            select(DailyMarketReviewSnapshot)
            .order_by(DailyMarketReviewSnapshot.review_date.desc())
            .limit(limit_days * len(Market))
        ).all()
        by_date: dict[str, dict[str, Any]] = {}
        for snapshot in snapshots:
            key = snapshot.review_date.isoformat()
            row = by_date.setdefault(
                key,
                {
                    "review_date": key,
                    "INDIA": None,
                    "US": None,
                    "total_hypothetical_pnl_inr": 0.0,
                    "total_real_orders": 0,
                },
            )
            market_row = {
                "market": snapshot.market.value,
                "status": snapshot.status,
                "signals": snapshot.signals,
                "shadow_hypotheses": snapshot.shadow_hypotheses,
                "real_orders": snapshot.real_orders,
                "hypothetical_pnl_inr": float(snapshot.hypothetical_pnl_inr),
                "hypothetical_pnl_pct": float(snapshot.hypothetical_pnl_pct),
                "winners": snapshot.winners,
                "losers": snapshot.losers,
                "flat": snapshot.flat,
            }
            row[snapshot.market.value] = market_row
            row["total_hypothetical_pnl_inr"] += float(snapshot.hypothetical_pnl_inr)
            row["total_real_orders"] += snapshot.real_orders
        return list(by_date.values())[:limit_days]

    @staticmethod
    def _symbol_pnl(observation: ShadowObservation | None) -> dict[str, Any] | None:
        if observation is None:
            return None
        return {
            "symbol": observation.symbol,
            "pnl_inr": float(observation.hypothetical_pnl_inr),
            "pnl_pct": float(observation.hypothetical_pnl_pct),
        }

    @staticmethod
    def _daily_brief(
        *,
        market: Market,
        observations: list[ShadowObservation],
        signals: list[AgentSignal],
        orders: list[Order],
        pnl: float,
    ) -> str:
        if not observations and not signals:
            return f"{market.value}: no shadow samples were recorded for the review day."
        order_text = "no real orders" if not orders else f"{len(orders)} real order records"
        return (
            f"{market.value}: reviewed {len(signals)} signals and {len(observations)} shadow "
            f"marks; hypothetical P&L {pnl:,.0f} INR; {order_text}."
        )

    @staticmethod
    def _daily_lessons(
        *,
        observations: list[ShadowObservation],
        signals: list[AgentSignal],
        orders: list[Order],
        pnl: float,
        risk_events: list[RiskEvent],
    ) -> list[str]:
        if not observations and not signals:
            return ["No market-hours shadow sample was available for this day."]
        lessons: list[str] = []
        if not orders:
            lessons.append("Real-order count stayed at zero, matching shadow-mode safety.")
        if pnl > 0:
            lessons.append("Shadow marks ended net positive; verify stop/target behavior before promotion.")
        elif pnl < 0:
            lessons.append("Shadow marks ended net negative; keep sizing conservative and inspect losers.")
        else:
            lessons.append("Shadow marks were flat or not yet conclusive.")
        if risk_events:
            lessons.append("Risk events occurred; review blockers before changing strategy speed.")
        buy_signals = len([item for item in signals if item.action.value == "BUY"])
        if buy_signals == 0:
            lessons.append("The quality filter stayed selective and did not create buy hypotheses.")
        return lessons[:3]

    @staticmethod
    def _daily_next_focus(
        *,
        observations: list[ShadowObservation],
        signals: list[AgentSignal],
        pnl: float,
    ) -> list[str]:
        if not observations and not signals:
            return ["Collect a full market-session sample before drawing conclusions."]
        focus = ["Compare shadow marks against stop, target, and time-exit rules."]
        if pnl < 0:
            focus.append("Inspect the worst symbols and tighten rejection reasons.")
        else:
            focus.append("Increase sample count before changing risk or entry rules.")
        focus.append("Keep live trading disabled until the review gate is passed.")
        return focus[:3]

    @staticmethod
    def _mask_email(value: str) -> str:
        if not value or "@" not in value:
            return ""
        local, domain = value.split("@", 1)
        return f"{mask_secret(local)}@{domain}"

    @staticmethod
    def _latest_shadow_cycle() -> dict[str, Any] | None:
        log_path = Path(".runtime") / "shadow_training.log"
        if not log_path.exists():
            return None
        lines = [line.strip() for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            return None
        try:
            return dict(json.loads(lines[-1]))
        except json.JSONDecodeError:
            return {"status": "unreadable_shadow_log"}

    @staticmethod
    def _shadow_status(latest_cycle: dict[str, Any] | None, interval_seconds: int) -> str:
        if not latest_cycle or not latest_cycle.get("started_at"):
            return "NO_CYCLE_RECORDED"
        try:
            started_at = datetime.fromisoformat(str(latest_cycle["started_at"]))
        except ValueError:
            return "UNKNOWN"
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        age_seconds = (datetime.now(UTC) - started_at.astimezone(UTC)).total_seconds()
        return "RUNNING_OR_RECENT" if age_seconds <= interval_seconds * 2 else "STALE"

    @staticmethod
    def _current_action(latest_cycle: dict[str, Any] | None) -> str:
        if not latest_cycle:
            return "Waiting for first shadow-training cycle."
        if latest_cycle.get("status") == "error":
            return f"Shadow cycle error: {latest_cycle.get('error', 'unknown')}"
        messages: list[str] = []
        for key, label in {"india": "India", "us": "US"}.items():
            market_cycle = latest_cycle.get(key, {})
            observed = market_cycle.get("observed", 0) if isinstance(market_cycle, dict) else 0
            blocked = market_cycle.get("blocked", []) if isinstance(market_cycle, dict) else []
            if observed:
                messages.append(f"{label}: observed {observed} symbols")
            elif blocked:
                messages.append(f"{label}: waiting ({', '.join(str(item) for item in blocked)})")
            else:
                messages.append(f"{label}: standing by")
        return f"{' | '.join(messages)}. No orders placed."

    @staticmethod
    def _improvement_actions(
        *,
        latest_cycle: dict[str, Any] | None,
        readiness: dict[str, Any],
        studied_symbols_today: list[str],
    ) -> list[str]:
        actions: list[str] = []
        if not studied_symbols_today:
            actions.append("Collect first market-hours shadow observations for configured India symbols.")
        actions.append("Collect intraday strategy-lab samples before increasing risk or speed.")
        checks = readiness.get("checks", [])
        for check in checks:
            if not check.get("passed") and check.get("severity") == "WARN":
                actions.append(str(check.get("detail") or check.get("name")))
        if latest_cycle and latest_cycle.get("orders_placed", 0) != 0:
            actions.append("Investigate unexpected order placement immediately.")
        actions.append("Compare shadow observations against later marks before adding any strategy scoring.")
        return list(dict.fromkeys(actions))


performance_service = PerformanceService()
