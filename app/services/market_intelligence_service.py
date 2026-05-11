from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import Market, OrderStatus
from app.db.models.news import NewsItem
from app.db.models.order import Order
from app.db.models.risk import RiskEvent
from app.db.models.shadow import ShadowTrainingSample
from app.db.session import SessionLocal
from app.risk.market_calendar import MarketCalendar
from app.schemas.broker import BrokerHealth
from app.schemas.provider import ProviderHealth
from app.services.broker_service import broker_service
from app.services.news_sentiment_service import NewsSentimentService
from app.services.profit_protection_service import profit_protection_service
from app.services.provider_service import provider_service
from app.services.shadow_readiness_service import shadow_readiness_service


@dataclass(frozen=True)
class MarketIntelligenceAgentReport:
    agent_name: str
    agent_version: str
    scope: str
    status: str
    confidence: float
    summary: str
    findings: list[str]
    risks: list[str]
    recommended_actions: list[str]
    data_sources: list[str]
    metrics: dict[str, Any]
    shadow_only: bool = True
    no_order_placement: bool = True
    orders_placed: int = 0

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


class MarketIntelligenceService:
    """Runs deterministic, shadow-only analysis agents for every market session.

    These agents explain what the system is learning from real shadow data. They do
    not create order intents, inflate training samples, or route anything to brokers.
    """

    agent_versions = {
        "SessionReadinessAgent": "v1",
        "ProviderHealthAgent": "v1",
        "NewsSentimentAgent": "v1",
        "PriceActionAgent": "v1",
        "ProfitProtectionAgent": "v1",
        "RiskPostureAgent": "v1",
        "LearningVelocityAgent": "v1",
    }

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.calendar = MarketCalendar(self.settings)
        self.news_sentiment = NewsSentimentService(self.settings)

    def summary(
        self,
        session: Session | None = None,
        *,
        brokers: list[BrokerHealth] | None = None,
        providers: list[ProviderHealth] | None = None,
        readiness: dict[str, Any] | None = None,
        profit_protection: dict[str, Any] | None = None,
        latest_cycle: dict[str, Any] | None = None,
        include_external_health: bool = True,
    ) -> dict[str, Any]:
        close_session = session is None
        db = session or SessionLocal()
        run_id = str(uuid4())
        try:
            if brokers is None:
                brokers = broker_service.statuses() if include_external_health else []
            if providers is None:
                providers = provider_service.statuses() if include_external_health else []
            if readiness is None:
                readiness = shadow_readiness_service.status()
            if profit_protection is None:
                profit_protection = profit_protection_service.summary(db)

            recent_samples = self._recent_samples(db)
            reports = [
                self._session_readiness_agent(readiness, latest_cycle),
                self._provider_health_agent(brokers, providers),
                self._news_sentiment_agent(db),
                self._price_action_agent(recent_samples),
                self._profit_protection_agent(profit_protection),
                self._risk_posture_agent(db),
                self._learning_velocity_agent(db, recent_samples),
            ]
            consensus = self._consensus(reports)
            return {
                "mode": "SHADOW_ONLY_MARKET_INTELLIGENCE",
                "run_id": run_id,
                "generated_at": datetime.now(UTC).isoformat(),
                "agent_count": len(reports),
                "agent_names": [report.agent_name for report in reports],
                "agent_consensus": consensus,
                "agents": [report.model_dump() for report in reports],
                "shadow_only": True,
                "no_order_placement": True,
                "orders_placed": 0,
                "plain_english": (
                    "These agents review real shadow data, market readiness, provider health, "
                    "news availability, risk posture, and profit-protection behavior. They are "
                    "advisory only and cannot place broker orders."
                ),
                "sample_policy": (
                    "Multiple agents do not multiply the same market tick into fake training data. "
                    "They add explanations and risk checks around the real samples already collected."
                ),
            }
        finally:
            if close_session:
                db.close()

    def _session_readiness_agent(
        self,
        readiness: dict[str, Any],
        latest_cycle: dict[str, Any] | None,
    ) -> MarketIntelligenceAgentReport:
        india_calendar = self.calendar.status(Market.INDIA)
        us_calendar = self.calendar.status(Market.US)
        india_ready = bool(readiness.get("ready_for_india_shadow_now"))
        us_ready = bool(readiness.get("ready_for_us_shadow_now"))
        blocked: list[str] = []
        if latest_cycle:
            for key in ("india", "us"):
                cycle = latest_cycle.get(key, {})
                if isinstance(cycle, dict):
                    blocked.extend(str(item) for item in cycle.get("blocked", []))
        status = "OK" if india_ready or us_ready else "WARN"
        if blocked:
            status = "WARN"
        findings = [
            f"India calendar: {india_calendar.state.value} ({india_calendar.reason}).",
            f"US calendar: {us_calendar.state.value} ({us_calendar.reason}).",
            f"India shadow readiness: {'ready' if india_ready else 'waiting'}.",
            f"US shadow readiness: {'ready' if us_ready else 'waiting'}.",
        ]
        if latest_cycle:
            findings.append(
                "Latest cycle observed India={india} symbols and US={us} symbols.".format(
                    india=(latest_cycle.get("india") or {}).get("observed", 0)
                    if isinstance(latest_cycle.get("india"), dict)
                    else 0,
                    us=(latest_cycle.get("us") or {}).get("observed", 0)
                    if isinstance(latest_cycle.get("us"), dict)
                    else 0,
                )
            )
        return self._report(
            agent_name="SessionReadinessAgent",
            scope="INDIA_US_SESSION",
            status=status,
            confidence=0.9,
            summary="Checks whether each market session is usable for shadow observation.",
            findings=findings,
            risks=blocked[:6],
            recommended_actions=[
                "Run the single shadow loop during market hours; keep agents inside that loop.",
                "Treat market-closed or provider-blocked cycles as valid no-trade learning.",
            ],
            data_sources=["MARKET_CALENDAR", "SHADOW_READINESS", "SHADOW_CYCLE_LOG"],
            metrics={
                "india_shadow_ready": india_ready,
                "us_shadow_ready": us_ready,
                "blocked_count": len(blocked),
            },
        )

    def _provider_health_agent(
        self,
        brokers: list[BrokerHealth],
        providers: list[ProviderHealth],
    ) -> MarketIntelligenceAgentReport:
        broker_rows = [broker.model_dump(mode="json") for broker in brokers]
        provider_rows = [provider.model_dump(mode="json") for provider in providers]
        broker_live_ready = sum(1 for broker in brokers if broker.is_healthy_for_live)
        provider_ready = sum(1 for provider in providers if provider.is_healthy_for_live)
        missing = [
            f"{item['provider_name']}:{item['market']}"
            for item in provider_rows
            if item["status"] == "MISSING_CREDENTIALS"
        ]
        degraded = [
            f"{item['provider_name']}:{item['market']}:{item.get('last_error') or item['status']}"
            for item in provider_rows
            if item["status"] not in {"OK"}
        ]
        degraded.extend(
            f"{item['broker_name']}:{item['market']}:{','.join(item.get('rejection_reasons') or ['not_live_ready'])}"
            for item in broker_rows
            if not (
                item["auth_status"] == "VALID"
                and item["account_status"] == "ACTIVE"
                and item["trading_enabled"]
                and item["positions_reconciled"]
            )
        )
        status = "OK" if not degraded and (brokers or providers) else "WARN"
        return self._report(
            agent_name="ProviderHealthAgent",
            scope="BROKER_PROVIDER_HEALTH",
            status=status,
            confidence=0.85 if brokers or providers else 0.4,
            summary="Checks broker, market-data, FX, and news-provider readiness.",
            findings=[
                f"{broker_live_ready}/{len(brokers)} brokers live-ready.",
                f"{provider_ready}/{len(providers)} providers fresh and healthy.",
                f"{len(missing)} providers missing credentials.",
            ],
            risks=degraded[:8],
            recommended_actions=[
                "Do not use unavailable providers as a reason to trade.",
                "Prefer real quote and FX health over dashboard optimism.",
                "Keep Yahoo research data non-primary until rate limits and freshness are controlled.",
            ],
            data_sources=["BROKER_HEALTH", "PROVIDER_HEALTH"],
            metrics={
                "brokers_checked": len(brokers),
                "providers_checked": len(providers),
                "broker_live_ready": broker_live_ready,
                "provider_live_ready": provider_ready,
                "missing_credentials": missing,
            },
        )

    def _news_sentiment_agent(self, db: Session) -> MarketIntelligenceAgentReport:
        latest_news = db.scalar(select(NewsItem).order_by(NewsItem.published_at.desc()).limit(1))
        fresh_cutoff = datetime.now(UTC) - timedelta(minutes=self.settings.news_staleness_minutes)
        fresh_news_count = db.scalar(
            select(func.count())
            .select_from(NewsItem)
            .where(NewsItem.published_at >= fresh_cutoff)
        ) or 0
        risk_window_cutoff = datetime.now(UTC) - timedelta(
            hours=self.settings.news_sentiment_risk_window_hours
        )
        risk_window_news_count = db.scalar(
            select(func.count())
            .select_from(NewsItem)
            .where(NewsItem.published_at >= risk_window_cutoff)
        ) or 0
        has_news_credentials = bool(
            self.settings.alpha_vantage_api_key
            or self.settings.finnhub_api_key
            or self.settings.benzinga_api_key
        )
        latest_at = self._iso_or_none(latest_news.published_at) if latest_news else None
        india_risk = self.news_sentiment.assess(db, market=Market.INDIA)
        us_risk = self.news_sentiment.assess(db, market=Market.US)
        blocking_risks = [risk for risk in (india_risk, us_risk) if risk.blocks_new_entries]
        status = "OK" if has_news_credentials and risk_window_news_count > 0 else "UNAVAILABLE"
        if blocking_risks:
            status = "WARN"
        findings = [
            f"News credentials configured: {'yes' if has_news_credentials else 'no'}.",
            f"Fresh headlines inside {self.settings.news_staleness_minutes} minutes: {fresh_news_count}.",
            (
                "Risk-window headlines inside "
                f"{self.settings.news_sentiment_risk_window_hours} hours: {risk_window_news_count}."
            ),
            f"India news gate: {india_risk.action} ({india_risk.reason}).",
            f"US news gate: {us_risk.action} ({us_risk.reason}).",
        ]
        if latest_news:
            findings.append(f"Latest stored headline provider={latest_news.provider}, symbol={latest_news.symbol or 'market'}." )
        else:
            findings.append("No stored headline ingestion is currently feeding the news table.")
        risks = []
        if not has_news_credentials:
            risks.append("news_credentials_missing")
        if fresh_news_count == 0:
            risks.append("no_headlines_inside_fresh_window")
        if risk_window_news_count == 0:
            risks.append("news_sentiment_unavailable_for_risk_window")
        risks.extend(f"{risk.market.value}:{risk.reason}" for risk in blocking_risks)
        return self._report(
            agent_name="NewsSentimentAgent",
            scope="NEWS_SENTIMENT_ENTRY_GUARD",
            status=status,
            confidence=0.75 if status == "OK" else 0.0,
            summary=(
                "News/sentiment is a risk reducer. It can block or lower confidence; it "
                "cannot upgrade a stock to BUY."
            ),
            findings=findings,
            risks=risks,
            recommended_actions=[
                "Add real Alpha Vantage NEWS_SENTIMENT or Finnhub/Benzinga headline ingestion before relying on sentiment.",
                "Use news risk only to reduce activity or force no-trade, never to create a trade.",
                "Store provider, headline time, symbol, and raw payload for audit.",
            ],
            data_sources=["NEWS_TABLE", "ALPHA_VANTAGE_OR_FINNHUB_OR_BENZINGA_CONFIGURATION"],
            metrics={
                "credentials_configured": has_news_credentials,
                "fresh_news_count": fresh_news_count,
                "risk_window_news_count": risk_window_news_count,
                "risk_window_hours": self.settings.news_sentiment_risk_window_hours,
                "latest_news_at": latest_at,
                "sentiment_used_for_buy": False,
                "india_news_gate": india_risk.model_dump(),
                "us_news_gate": us_risk.model_dump(),
            },
        )

    def _price_action_agent(
        self,
        samples: list[ShadowTrainingSample],
    ) -> MarketIntelligenceAgentReport:
        latest_ideas = self._latest_samples_by_shadow_idea(samples)
        market_metrics = {
            market.value: self._market_sample_metrics(market, samples, latest_ideas)
            for market in Market
        }
        total_samples = len(samples)
        total_pnl = sum(float(sample.hypothetical_pnl_inr or 0) for sample in latest_ideas)
        top = sorted(latest_ideas, key=lambda sample: float(sample.hypothetical_pnl_inr or 0), reverse=True)[:3]
        bottom = sorted(latest_ideas, key=lambda sample: float(sample.hypothetical_pnl_inr or 0))[:3]
        findings = [
            f"Recent timestamped samples inspected: {total_samples}.",
            f"Unique shadow ideas represented: {len(latest_ideas)}.",
            f"Recent latest-mark shadow P&L across unique ideas: INR {total_pnl:,.0f}.",
        ]
        if top:
            findings.append(
                "Strongest recent ideas: "
                + ", ".join(f"{sample.market.value}:{sample.symbol}" for sample in top)
                + "."
            )
        risks = []
        if bottom and any(float(sample.hypothetical_pnl_inr or 0) < 0 for sample in bottom):
            risks.append(
                "Worst recent ideas: "
                + ", ".join(
                    f"{sample.market.value}:{sample.symbol} INR {float(sample.hypothetical_pnl_inr or 0):,.0f}"
                    for sample in bottom[:3]
                )
            )
        return self._report(
            agent_name="PriceActionAgent",
            scope="RECENT_SHADOW_PRICE_ACTION",
            status="OK" if total_samples else "WARN",
            confidence=0.7 if total_samples >= 10 else 0.35,
            summary="Reads real shadow marks for winners, losers, and simple trend evidence.",
            findings=findings,
            risks=risks,
            recommended_actions=[
                "Study why losers failed before increasing intraday speed.",
                "Prefer more independent market-time samples over duplicated opinions.",
                "Keep stop-loss and target metadata mandatory for every trainable row.",
            ],
            data_sources=["SHADOW_TRAINING_SAMPLES"],
            metrics={
                "total_samples": total_samples,
                "unique_shadow_ideas": len(latest_ideas),
                "latest_mark_hypothetical_pnl_inr": total_pnl,
                "markets": market_metrics,
            },
        )

    def _profit_protection_agent(
        self,
        profit_protection: dict[str, Any],
    ) -> MarketIntelligenceAgentReport:
        booking = profit_protection.get("shadow_profit_booking", {})
        alerts_count = int(profit_protection.get("alerts_count") or 0)
        high_urgency_count = int(profit_protection.get("high_urgency_count") or 0)
        giveback = float(profit_protection.get("giveback_from_best_observed_inr") or 0)
        status = "WARN" if high_urgency_count else "OK"
        return self._report(
            agent_name="ProfitProtectionAgent",
            scope="INTRADAY_EXIT_AND_PROFIT_BOOKING",
            status=status,
            confidence=0.8,
            summary="Tracks peak profit, giveback, target touches, and stop-loss exits in shadow mode.",
            findings=[
                f"Profit-protection alerts: {alerts_count}.",
                f"High urgency alerts: {high_urgency_count}.",
                f"Giveback from best observed P&L: INR {giveback:,.0f}.",
                f"Shadow profit-booked exits: {booking.get('booked_profit_count', 0)}.",
                f"Shadow stop-loss exits: {booking.get('booked_loss_count', 0)}.",
            ],
            risks=[
                "Profit fade needs review." if giveback > 0 else "No material giveback detected."
            ],
            recommended_actions=[
                "Review profit-booking rows before changing entry rules.",
                "Do not chase re-entry after a booked profit; wait for a fresh qualified setup.",
                "Stop-loss exits are learning data, not a reason to double size.",
            ],
            data_sources=["SHADOW_TRAINING_SAMPLES", "PROFIT_PROTECTION_SERVICE"],
            metrics={
                "alerts_count": alerts_count,
                "high_urgency_count": high_urgency_count,
                "giveback_from_best_observed_inr": giveback,
                "booked_profit_count": booking.get("booked_profit_count", 0),
                "booked_loss_count": booking.get("booked_loss_count", 0),
            },
        )

    def _risk_posture_agent(self, db: Session) -> MarketIntelligenceAgentReport:
        safety_errors = self.settings.live_mode_safety_errors()
        open_unknown_orders = db.scalar(
            select(func.count())
            .select_from(Order)
            .where(Order.status == OrderStatus.UNKNOWN_REQUIRES_RECONCILIATION)
        ) or 0
        total_orders = db.scalar(select(func.count()).select_from(Order)) or 0
        risk_events_today = db.scalar(
            select(func.count())
            .select_from(RiskEvent)
            .where(RiskEvent.created_at >= datetime.combine(datetime.now(UTC).date(), datetime.min.time(), tzinfo=UTC))
        ) or 0
        status = "OK"
        risks: list[str] = []
        if self.settings.live_trading_enabled or not self.settings.kill_switch:
            status = "BLOCKED"
            risks.append("shadow_system_has_live_flag_or_kill_switch_risk")
        if open_unknown_orders:
            status = "BLOCKED"
            risks.append("unknown_orders_require_reconciliation")
        return self._report(
            agent_name="RiskPostureAgent",
            scope="CAPITAL_PROTECTION",
            status=status,
            confidence=0.95,
            summary="Verifies that advisory agents remain far away from live execution.",
            findings=[
                f"Live trading enabled: {self.settings.live_trading_enabled}.",
                f"Kill switch enabled: {self.settings.kill_switch}.",
                f"Total broker order records: {total_orders}.",
                f"Unknown orders requiring reconciliation: {open_unknown_orders}.",
                f"Risk events today: {risk_events_today}.",
            ],
            risks=risks,
            recommended_actions=[
                "Keep live disabled and kill switch on while shadow agents learn.",
                "Reconcile unknown orders before any future live discussion.",
                "Use no-trade as a valid decision when any gate is unclear.",
            ],
            data_sources=["SYSTEM_CONFIG", "ORDERS_TABLE", "RISK_EVENTS"],
            metrics={
                "safety_errors": safety_errors,
                "total_orders": total_orders,
                "unknown_orders": open_unknown_orders,
                "risk_events_today": risk_events_today,
            },
        )

    def _learning_velocity_agent(
        self,
        db: Session,
        samples: list[ShadowTrainingSample],
    ) -> MarketIntelligenceAgentReport:
        total_samples = db.scalar(select(func.count()).select_from(ShadowTrainingSample)) or 0
        trainable = sum(1 for sample in samples if self._has_trainable_metadata(sample))
        target = self.settings.intraday_min_total_samples
        progress = total_samples / target if target else 0
        india_samples = db.scalar(
            select(func.count())
            .select_from(ShadowTrainingSample)
            .where(ShadowTrainingSample.market == Market.INDIA)
        ) or 0
        us_samples = db.scalar(
            select(func.count())
            .select_from(ShadowTrainingSample)
            .where(ShadowTrainingSample.market == Market.US)
        ) or 0
        return self._report(
            agent_name="LearningVelocityAgent",
            scope="TRAINING_SPEED_AND_SAMPLE_QUALITY",
            status="OK" if progress >= 1 else "WARN",
            confidence=0.75,
            summary="Tracks whether the engine is collecting enough real, stop-aware intraday samples.",
            findings=[
                f"Total stored training samples: {total_samples}/{target}.",
                f"India samples: {india_samples}; US samples: {us_samples}.",
                f"Trainable rows in latest inspected window: {trainable}/{len(samples)}.",
            ],
            risks=[
                "Speed must come from more real market observations, not duplicated agent votes.",
                "A larger sample target delays live trading but reduces overfitting risk.",
            ],
            recommended_actions=[
                "Keep the 60-second loop running during each market session.",
                "Add more symbols only after provider rate limits and quote freshness are healthy.",
                "Segment results by agent finding, market, time of day, and stop/target outcome.",
            ],
            data_sources=["SHADOW_TRAINING_SAMPLES", "CONFIG"],
            metrics={
                "total_samples": total_samples,
                "target_samples": target,
                "progress_pct": progress,
                "india_samples": india_samples,
                "us_samples": us_samples,
                "latest_window_trainable": trainable,
                "latest_window_samples": len(samples),
            },
        )

    def _consensus(self, reports: list[MarketIntelligenceAgentReport]) -> dict[str, Any]:
        blockers = [
            risk
            for report in reports
            if report.status in {"BLOCKED", "UNAVAILABLE", "WARN"}
            for risk in report.risks
            if risk
        ]
        actions = []
        for report in reports:
            actions.extend(report.recommended_actions[:2])
        if any(report.status == "BLOCKED" for report in reports):
            status = "BLOCKED"
            summary = "One or more safety checks are blocked. Keep shadow-only."
        elif any(report.status in {"UNAVAILABLE", "WARN"} for report in reports):
            status = "CAUTION"
            summary = "Agents can analyze shadow data, but some data sources or evidence gates are incomplete."
        else:
            status = "OK"
            summary = "Agents agree the system is suitable for shadow observation only."
        return {
            "status": status,
            "summary": summary,
            "blockers_or_cautions": list(dict.fromkeys(blockers))[:10],
            "top_actions": list(dict.fromkeys(actions))[:8],
            "shadow_only": True,
            "no_order_placement": True,
            "orders_placed": 0,
        }

    def _recent_samples(self, db: Session, limit: int = 500) -> list[ShadowTrainingSample]:
        return list(
            db.scalars(
                select(ShadowTrainingSample)
                .order_by(ShadowTrainingSample.sample_at.desc())
                .limit(limit)
            ).all()
        )

    @staticmethod
    def _market_sample_metrics(
        market: Market,
        samples: list[ShadowTrainingSample],
        latest_ideas: list[ShadowTrainingSample],
    ) -> dict[str, Any]:
        market_samples = [sample for sample in samples if sample.market == market]
        market_ideas = [sample for sample in latest_ideas if sample.market == market]
        pnl_values = [float(sample.hypothetical_pnl_inr or 0) for sample in market_ideas]
        winners = len([value for value in pnl_values if value > 0])
        losers = len([value for value in pnl_values if value < 0])
        return {
            "samples": len(market_samples),
            "unique_shadow_ideas": len(market_ideas),
            "hypothetical_pnl_inr": sum(pnl_values),
            "winners": winners,
            "losers": losers,
            "flat": max(len(market_ideas) - winners - losers, 0),
            "win_rate": winners / len(market_ideas) if market_ideas else 0.0,
        }

    @staticmethod
    def _latest_samples_by_shadow_idea(
        samples: list[ShadowTrainingSample],
    ) -> list[ShadowTrainingSample]:
        latest: dict[tuple[str, str, str, str], ShadowTrainingSample] = {}
        for sample in samples:
            idea_key = sample.observation_id or f"{sample.market.value}:{sample.symbol}:{sample.sample_at.date().isoformat()}"
            key = (
                sample.strategy_name,
                sample.market.value,
                sample.symbol,
                idea_key,
            )
            existing = latest.get(key)
            if existing is None or sample.sample_at > existing.sample_at:
                latest[key] = sample
        return list(latest.values())

    @staticmethod
    def _has_trainable_metadata(sample: ShadowTrainingSample) -> bool:
        metadata = sample.metadata_json or {}
        assessment = metadata.get("assessment") if isinstance(metadata, dict) else {}
        if not isinstance(assessment, dict):
            return False
        return bool(assessment.get("stop_loss")) and bool(assessment.get("reward_risk_ratio"))

    def _report(
        self,
        *,
        agent_name: str,
        scope: str,
        status: str,
        confidence: float,
        summary: str,
        findings: list[str],
        risks: list[str],
        recommended_actions: list[str],
        data_sources: list[str],
        metrics: dict[str, Any],
    ) -> MarketIntelligenceAgentReport:
        return MarketIntelligenceAgentReport(
            agent_name=agent_name,
            agent_version=self.agent_versions[agent_name],
            scope=scope,
            status=status,
            confidence=confidence,
            summary=summary,
            findings=findings,
            risks=risks,
            recommended_actions=recommended_actions,
            data_sources=data_sources,
            metrics=metrics,
        )

    @staticmethod
    def _iso_or_none(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()


market_intelligence_service = MarketIntelligenceService()
