from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from math import floor
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import AssetClass, Market, RiskDecisionType, TradeAction
from app.core.errors import TradingAlphaError
from app.core.time_utils import as_timezone, ensure_utc
from app.data_providers.alpaca_data import AlpacaDataProvider
from app.data_providers.fx_provider import FXProvider
from app.data_providers.zerodha_data import ZerodhaDataProvider
from app.db.models.audit import AuditLog
from app.db.models.instrument import Instrument
from app.db.models.risk import RiskDecisionModel, RiskEvent
from app.db.models.shadow import ShadowObservation, ShadowTrainingSample
from app.db.models.signal import AgentSignal
from app.db.models.strategy import Strategy
from app.db.session import SessionLocal
from app.risk.market_calendar import MarketCalendar
from app.services.intraday_model_training_service import intraday_model_training_service
from app.services.market_intelligence_service import market_intelligence_service
from app.services.news_sentiment_service import NewsSentimentService
from app.services.shadow_exit_service import shadow_exit_service
from app.strategies.conservative_shadow import ConservativeShadowStrategy


class ShadowTrainingService:
    strategy_name = "shadow_training_observation_v1"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.calendar = MarketCalendar(self.settings)
        self.news_sentiment = NewsSentimentService(self.settings)
        self.strategy = ConservativeShadowStrategy()

    def run_cycle(self, db: Session | None = None) -> dict[str, Any]:
        close_session = db is None
        session = db or SessionLocal()
        started_at = datetime.now(UTC)
        result: dict[str, Any] = {
            "started_at": started_at.isoformat(),
            "mode": self.settings.trading_mode.value,
            "live_trading_enabled": self.settings.live_trading_enabled,
            "kill_switch": self.settings.kill_switch,
            "orders_placed": 0,
            "shadow_observations_updated": 0,
            "india": {"observed": 0, "blocked": [], "symbols": self.settings.shadow_india_symbol_list},
            "us": {"observed": 0, "blocked": [], "symbols": self.settings.shadow_us_symbol_list},
        }

        try:
            if not self.settings.shadow_training_enabled:
                result["status"] = "disabled"
                return result
            strategy = self._get_or_create_strategy(session)
            result["news_sentiment_ingestion"] = self.news_sentiment.ingest_if_due(session)
            result["stale_intraday_closed"] = {
                "india": self._close_stale_intraday_observations(session, Market.INDIA, started_at),
                "us": self._close_stale_intraday_observations(session, Market.US, started_at),
            }
            self._run_india_cycle(session, strategy, result)
            self._run_us_cycle(session, strategy, result)
            result["intraday_model_training"] = self._run_intraday_model_training(session)
            result["market_intelligence"] = market_intelligence_service.summary(
                session,
                brokers=[],
                providers=[],
                readiness={
                    "ready_for_india_shadow_now": not result["india"]["blocked"],
                    "ready_for_us_shadow_now": not result["us"]["blocked"],
                    "checks": [],
                },
                latest_cycle=result,
                include_external_health=False,
            )
            session.add(
                AuditLog(
                    actor="shadow_training_service",
                    action="shadow_cycle_completed",
                    entity_type="shadow_training",
                    message="Shadow training cycle completed without order placement.",
                    context=result,
                )
            )
            session.commit()
            result["status"] = "completed"
            return result
        except Exception:
            session.rollback()
            raise
        finally:
            if close_session:
                session.close()

    def _run_india_cycle(self, session: Session, strategy: Strategy, result: dict[str, Any]) -> None:
        calendar_status = self.calendar.status(Market.INDIA)
        if not calendar_status.is_open:
            reason = f"india_market_not_open:{calendar_status.reason}"
            result["india"]["blocked"].append(reason)
            self._record_risk_event(session, Market.INDIA, reason, "India shadow scan skipped.")
            return

        provider = ZerodhaDataProvider(self.settings)
        for symbol in self.settings.shadow_india_symbol_list:
            try:
                quote = provider.latest(symbol, Market.INDIA)
                last_price = self._extract_last_price(quote)
                assessment = self.strategy.assess(quote, last_price)
                instrument = self._get_or_create_instrument(session, Market.INDIA, symbol)
                signal = AgentSignal(
                    strategy_id=strategy.id,
                    instrument_id=instrument.id,
                    market=Market.INDIA,
                    symbol=symbol,
                    asset_class=AssetClass.EQUITY,
                    action=assessment.action,
                    confidence=assessment.confidence,
                    strategy_name=self.strategy_name,
                    payload={
                        "last_price": last_price,
                        "quote": quote,
                        "assessment": assessment.model_dump(),
                        "shadow_note": "Observation only. No order intent created.",
                    },
                    data_sources=["ZERODHA_KITE"],
                )
                session.add(signal)
                session.flush()
                session.add(
                    RiskDecisionModel(
                        signal_id=signal.id,
                        decision=RiskDecisionType.NO_TRADE,
                        approved_quantity=0,
                        approved_capital=0,
                        approved_risk=0,
                        rejection_reasons=assessment.risk_flags,
                        required_actions=["observe_only_no_order", *assessment.reasons],
                        risk_metrics={
                            "last_price": last_price or 0,
                            "stop_loss": assessment.stop_loss or 0,
                            "take_profit": assessment.take_profit or 0,
                            "expected_risk": assessment.expected_risk,
                            "expected_reward": assessment.expected_reward,
                            "reward_risk_ratio": assessment.reward_risk_ratio,
                            "confidence": assessment.confidence,
                            **assessment.metrics,
                        },
                    )
                )
                if last_price is not None and last_price > 0:
                    updated = self._record_shadow_observation(
                        session, instrument, symbol, signal.id, last_price, assessment
                    )
                    if updated:
                        result["shadow_observations_updated"] += 1
                result["india"]["observed"] += 1
            except TradingAlphaError as exc:
                reason = f"{symbol}:{exc}"
                result["india"]["blocked"].append(reason)
                self._record_risk_event(session, Market.INDIA, "india_shadow_symbol_blocked", reason)

    def _run_us_cycle(self, session: Session, strategy: Strategy, result: dict[str, Any]) -> None:
        calendar_status = self.calendar.status(Market.US)
        if not calendar_status.is_open:
            reason = f"us_market_not_open:{calendar_status.reason}"
            result["us"]["blocked"].append(reason)
            self._record_risk_event(session, Market.US, reason, "US shadow scan skipped.")
            return

        try:
            fx_status = FXProvider(self.settings).get_usd_inr()
        except TradingAlphaError as exc:
            reason = f"us_shadow_fx_blocked:{exc}"
            result["us"]["blocked"].append(reason)
            self._record_risk_event(session, Market.US, "us_shadow_fx_blocked", reason, "WARN")
            return

        if not fx_status.is_fresh or fx_status.rate is None:
            reason = "us_shadow_fx_blocked:usd_inr_fx_stale_or_missing"
            result["us"]["blocked"].append(reason)
            self._record_risk_event(session, Market.US, "us_shadow_fx_blocked", reason, "WARN")
            return

        provider = AlpacaDataProvider(self.settings)
        for symbol in self.settings.shadow_us_symbol_list:
            try:
                quote = provider.latest(symbol, Market.US)
                last_price = self._extract_last_price(quote)
                assessment = self.strategy.assess(quote, last_price)
                instrument = self._get_or_create_instrument(session, Market.US, symbol)
                signal = AgentSignal(
                    strategy_id=strategy.id,
                    instrument_id=instrument.id,
                    market=Market.US,
                    symbol=symbol,
                    asset_class=AssetClass.ETF if symbol in {"SPY", "QQQ"} else AssetClass.EQUITY,
                    action=assessment.action,
                    confidence=assessment.confidence,
                    strategy_name=self.strategy_name,
                    payload={
                        "last_price_usd": last_price,
                        "usd_inr": fx_status.rate,
                        "quote": quote,
                        "assessment": assessment.model_dump(),
                        "shadow_note": "Observation only. No order intent created.",
                    },
                    data_sources=["ALPACA_DATA", fx_status.source],
                )
                session.add(signal)
                session.flush()
                session.add(
                    RiskDecisionModel(
                        signal_id=signal.id,
                        decision=RiskDecisionType.NO_TRADE,
                        approved_quantity=0,
                        approved_capital=0,
                        approved_risk=0,
                        rejection_reasons=assessment.risk_flags,
                        required_actions=["observe_only_no_order", *assessment.reasons],
                        risk_metrics={
                            "last_price_usd": last_price or 0,
                            "usd_inr": fx_status.rate,
                            "stop_loss_usd": assessment.stop_loss or 0,
                            "take_profit_usd": assessment.take_profit or 0,
                            "expected_risk_usd": assessment.expected_risk,
                            "expected_reward_usd": assessment.expected_reward,
                            "reward_risk_ratio": assessment.reward_risk_ratio,
                            "confidence": assessment.confidence,
                            **assessment.metrics,
                        },
                    )
                )
                if last_price is not None and last_price > 0:
                    updated = self._record_shadow_observation(
                        session,
                        instrument,
                        symbol,
                        signal.id,
                        last_price,
                        assessment,
                        market=Market.US,
                        fx_rate=fx_status.rate,
                    )
                    if updated:
                        result["shadow_observations_updated"] += 1
                result["us"]["observed"] += 1
            except TradingAlphaError as exc:
                reason = f"{symbol}:{exc}"
                result["us"]["blocked"].append(reason)
                self._record_risk_event(session, Market.US, "us_shadow_symbol_blocked", reason)

    def _get_or_create_strategy(self, session: Session) -> Strategy:
        strategy = session.scalar(select(Strategy).where(Strategy.name == self.strategy_name))
        if strategy:
            return strategy
        strategy = Strategy(
            name=self.strategy_name,
            description="Observation-only shadow training. It never creates order intents.",
            enabled=True,
        )
        session.add(strategy)
        session.flush()
        return strategy

    def _get_or_create_instrument(self, session: Session, market: Market, symbol: str) -> Instrument:
        instrument = session.scalar(
            select(Instrument).where(Instrument.market == market, Instrument.symbol == symbol)
        )
        if instrument:
            return instrument
        instrument = Instrument(
            market=market,
            symbol=symbol,
            name=symbol,
            asset_class=AssetClass.EQUITY,
            currency="INR" if market == Market.INDIA else "USD",
            exchange="NSE" if market == Market.INDIA else "US",
            is_active=True,
        )
        session.add(instrument)
        session.flush()
        return instrument

    def _record_shadow_observation(
        self,
        session: Session,
        instrument: Instrument,
        symbol: str,
        signal_id: str,
        last_price: float,
        assessment: Any,
        market: Market = Market.INDIA,
        fx_rate: float = 1.0,
    ) -> bool:
        now = datetime.now(UTC)
        observation = session.scalar(
            select(ShadowObservation).where(
                ShadowObservation.strategy_name == self.strategy_name,
                ShadowObservation.market == market,
                ShadowObservation.symbol == symbol,
                ShadowObservation.status == "OPEN_OBSERVATION",
            )
        )
        if observation is None:
            action_value = (
                assessment.action.value if hasattr(assessment.action, "value") else str(assessment.action)
            )
            if action_value != TradeAction.BUY.value:
                self._record_risk_event(
                    session,
                    market,
                    "shadow_entry_quality_blocked",
                    (
                        f"{symbol}: strategy returned {action_value}; "
                        "no fresh shadow buy/watch observation opened."
                    ),
                    "INFO",
                )
                return False
            news_risk = self.news_sentiment.assess(session, market=market, symbol=symbol)
            if self.settings.news_sentiment_block_shadow_entries and news_risk.blocks_new_entries:
                self._record_risk_event(
                    session,
                    market,
                    "shadow_news_sentiment_entry_blocked",
                    (
                        f"{symbol}: fresh shadow entry blocked by news/sentiment guard. "
                        f"{news_risk.reason}"
                    ),
                    news_risk.severity,
                    context=news_risk.model_dump(),
                )
                return False
            cooldown = self._active_reentry_cooldown(session, market, symbol, now)
            if cooldown is not None:
                self._record_risk_event(
                    session,
                    market,
                    "shadow_reentry_cooldown_active",
                    (
                        f"{symbol}: previous shadow exit is cooling down until "
                        f"{cooldown.isoformat()}; no immediate re-entry opened."
                    ),
                    "INFO",
                )
                return False
            loss_pause = self._active_loss_discipline_pause(session, market, symbol, now)
            if loss_pause is not None:
                self._record_risk_event(
                    session,
                    market,
                    "shadow_loss_discipline_pause",
                    (
                        f"{symbol}: new shadow entry paused by loss discipline. "
                        f"{loss_pause['reason']}"
                    ),
                    "WARN",
                )
                return False
            quantity, notional = self._shadow_size(entry_price=last_price, fx_rate=fx_rate)
            entry_assessment = assessment.model_dump()
            observation = ShadowObservation(
                strategy_name=self.strategy_name,
                market=market,
                symbol=symbol,
                instrument_id=instrument.id,
                signal_id=signal_id,
                opened_at=now,
                last_marked_at=now,
                entry_price=last_price,
                current_price=last_price,
                hypothetical_quantity=quantity,
                hypothetical_notional_inr=notional,
                hypothetical_pnl_inr=0,
                hypothetical_pnl_pct=0,
                notes=[
                    "Shadow hypothesis only. No order intent, broker order, or fill was created.",
                    "Stop and target are deterministic quality-control levels, not guarantees.",
                ],
                metadata_json={
                    "source": "ALPACA_DATA" if market == Market.US else "ZERODHA_KITE_QUOTE",
                    "price_currency": "USD" if market == Market.US else "INR",
                    "usd_inr": fx_rate,
                    "shadow_notional_per_symbol_inr": self.settings.shadow_hypothesis_notional_inr,
                    "sizing_policy": "whole_share_shadow_budget",
                    "assessment": entry_assessment,
                    "entry_assessment": entry_assessment,
                    "latest_assessment": entry_assessment,
                },
            )
            session.add(observation)
        else:
            entry_price = float(observation.entry_price)
            quantity, notional = self._shadow_size(entry_price=entry_price, fx_rate=fx_rate)
            pnl = (last_price - entry_price) * quantity * fx_rate
            pnl_pct = pnl / float(notional or 1)
            existing_metadata = observation.metadata_json or {}
            entry_assessment = (
                existing_metadata.get("entry_assessment")
                or existing_metadata.get("assessment")
                or assessment.model_dump()
            )
            latest_assessment = assessment.model_dump()
            observation.signal_id = signal_id
            observation.hypothetical_quantity = quantity
            observation.hypothetical_notional_inr = notional
            observation.current_price = last_price
            observation.last_marked_at = now
            observation.hypothetical_pnl_inr = pnl
            observation.hypothetical_pnl_pct = pnl_pct
            observation.metadata_json = {
                **existing_metadata,
                "source": "ALPACA_DATA" if market == Market.US else "ZERODHA_KITE_QUOTE",
                "price_currency": "USD" if market == Market.US else "INR",
                "usd_inr": fx_rate,
                "shadow_notional_per_symbol_inr": self.settings.shadow_hypothesis_notional_inr,
                "sizing_policy": "whole_share_shadow_budget",
                "assessment": entry_assessment,
                "entry_assessment": entry_assessment,
                "latest_assessment": latest_assessment,
            }
        session.flush()
        self._record_intraday_training_sample(session, observation, signal_id, assessment, fx_rate)
        self._apply_shadow_exit_policy(
            session, observation, signal_id, assessment, fx_rate, datetime.now(UTC)
        )
        return True

    def _shadow_size(self, *, entry_price: float, fx_rate: float) -> tuple[int, float]:
        price_inr = entry_price * fx_rate
        quantity = floor(self.settings.shadow_hypothesis_notional_inr / price_inr) if price_inr > 0 else 0
        return quantity, quantity * entry_price * fx_rate

    def _record_intraday_training_sample(
        self,
        session: Session,
        observation: ShadowObservation,
        signal_id: str,
        assessment: Any,
        fx_rate: float,
    ) -> None:
        observation_metadata = observation.metadata_json or {}
        entry_assessment = (
            observation_metadata.get("entry_assessment")
            or observation_metadata.get("assessment")
            or assessment.model_dump()
        )
        session.add(
            ShadowTrainingSample(
                observation_id=observation.id,
                strategy_name=observation.strategy_name,
                market=observation.market,
                symbol=observation.symbol,
                instrument_id=observation.instrument_id,
                signal_id=signal_id,
                sample_at=datetime.now(UTC),
                entry_price=observation.entry_price,
                current_price=observation.current_price,
                hypothetical_quantity=observation.hypothetical_quantity,
                hypothetical_notional_inr=observation.hypothetical_notional_inr,
                hypothetical_pnl_inr=observation.hypothetical_pnl_inr,
                hypothetical_pnl_pct=observation.hypothetical_pnl_pct,
                sample_kind="INTRADAY_MARK",
                metadata_json={
                    "source": "ALPACA_DATA" if observation.market == Market.US else "ZERODHA_KITE_QUOTE",
                    "price_currency": "USD" if observation.market == Market.US else "INR",
                    "usd_inr": fx_rate,
                    "assessment": entry_assessment,
                    "latest_assessment": self._assessment_dump(assessment),
                    "shadow_note": "Timestamped intraday training sample only. No order intent created.",
                },
            )
        )

    def _apply_shadow_exit_policy(
        self,
        session: Session,
        observation: ShadowObservation,
        signal_id: str,
        assessment: Any,
        fx_rate: float,
        now: datetime,
    ) -> None:
        if not self.settings.intraday_shadow_exit_enabled:
            return
        if observation.status != "OPEN_OBSERVATION":
            return

        exit_decision = shadow_exit_service.evaluate_observation(observation).model_dump()
        close_actions = {
            "EXIT_STOP_LOSS",
            "EXIT_TAKE_PROFIT",
            "EXIT_PROFIT_BOOKING",
            "EXIT_PROFIT_GIVEBACK",
        }
        if exit_decision["action"] not in close_actions:
            path_decision = self._profit_path_exit_decision(session, observation)
            if path_decision and path_decision["action"] in close_actions:
                exit_decision = path_decision

        if exit_decision["action"] not in close_actions:
            return

        self._close_shadow_observation(
            session=session,
            observation=observation,
            signal_id=signal_id,
            assessment=assessment,
            fx_rate=fx_rate,
            now=now,
            exit_decision=exit_decision,
        )

    def _profit_path_exit_decision(
        self,
        session: Session,
        observation: ShadowObservation,
    ) -> dict[str, Any] | None:
        samples = session.scalars(
            select(ShadowTrainingSample)
            .where(ShadowTrainingSample.observation_id == observation.id)
            .order_by(ShadowTrainingSample.sample_at.asc())
        ).all()
        if len(samples) < 2:
            return None

        peak = max(samples, key=lambda sample: float(sample.hypothetical_pnl_inr or 0))
        peak_pnl = float(peak.hypothetical_pnl_inr or 0)
        current_pnl = float(observation.hypothetical_pnl_inr or 0)
        notional = float(observation.hypothetical_notional_inr or 0)
        peak_pct = float(peak.hypothetical_pnl_pct or 0)
        current_pct = current_pnl / notional if notional else 0.0
        giveback = max(peak_pnl - current_pnl, 0.0)
        giveback_pct = giveback / peak_pnl if peak_pnl > 0 else 0.0
        can_lock_profit = (
            peak_pnl >= self.settings.intraday_min_profit_lock_inr
            or peak_pct >= self.settings.intraday_min_profit_lock_pct
        )
        if (
            can_lock_profit
            and peak_pnl > 0
            and giveback_pct >= self.settings.intraday_profit_giveback_exit_pct
        ):
            return {
                "action": "EXIT_PROFIT_GIVEBACK",
                "label": "Book profit after giveback",
                "urgency": "HIGH",
                "reason": (
                    f"Shadow profit peaked at {peak_pnl:.2f} INR and then gave back "
                    f"{giveback_pct:.0%}. Freeze the shadow exit instead of watching "
                    "a good gain fade."
                ),
                "progress_to_target": None,
                "progress_to_stop": None,
                "reentry_plan": (
                    "Wait for the re-entry cooldown and a fresh setup. Do not chase "
                    "the same stock immediately after profit booking."
                ),
                "peak_pnl_inr": peak_pnl,
                "peak_pnl_pct": peak_pct,
                "current_pnl_inr": current_pnl,
                "current_pnl_pct": current_pct,
                "giveback_inr": giveback,
                "giveback_pct_of_peak": giveback_pct,
                "shadow_only": True,
                "no_order_placement": True,
            }
        return None

    def _close_shadow_observation(
        self,
        *,
        session: Session,
        observation: ShadowObservation,
        signal_id: str,
        assessment: Any,
        fx_rate: float,
        now: datetime,
        exit_decision: dict[str, Any],
    ) -> None:
        status = self._closed_status(exit_decision["action"])
        reentry_blocked_until = now + timedelta(minutes=self.settings.intraday_reentry_cooldown_minutes)
        metadata = observation.metadata_json or {}
        shadow_exit = {
            "action": exit_decision["action"],
            "label": exit_decision["label"],
            "urgency": exit_decision["urgency"],
            "reason": exit_decision["reason"],
            "reentry_plan": exit_decision["reentry_plan"],
            "exited_at": now.isoformat(),
            "exit_price": float(observation.current_price or 0),
            "exit_pnl_inr": float(observation.hypothetical_pnl_inr or 0),
            "exit_pnl_pct": float(observation.hypothetical_pnl_pct or 0),
            "peak_pnl_inr": exit_decision.get("peak_pnl_inr"),
            "giveback_inr": exit_decision.get("giveback_inr"),
            "shadow_only": True,
            "no_order_placement": True,
        }
        observation.status = status
        observation.metadata_json = {
            **metadata,
            "latest_assessment": self._assessment_dump(assessment),
            "shadow_exit": shadow_exit,
            "reentry_blocked_until": reentry_blocked_until.isoformat(),
        }
        observation.notes = [
            *(observation.notes or []),
            (
                f"Shadow exit recorded: {exit_decision['action']}. "
                "No broker order was created."
            ),
        ]
        session.add(
            ShadowTrainingSample(
                observation_id=observation.id,
                strategy_name=observation.strategy_name,
                market=observation.market,
                symbol=observation.symbol,
                instrument_id=observation.instrument_id,
                signal_id=signal_id,
                sample_at=now,
                entry_price=observation.entry_price,
                current_price=observation.current_price,
                hypothetical_quantity=observation.hypothetical_quantity,
                hypothetical_notional_inr=observation.hypothetical_notional_inr,
                hypothetical_pnl_inr=observation.hypothetical_pnl_inr,
                hypothetical_pnl_pct=observation.hypothetical_pnl_pct,
                sample_kind="SHADOW_EXIT",
                metadata_json={
                    "source": "ALPACA_DATA" if observation.market == Market.US else "ZERODHA_KITE_QUOTE",
                    "price_currency": "USD" if observation.market == Market.US else "INR",
                    "usd_inr": fx_rate,
                    "assessment": metadata.get("entry_assessment") or metadata.get("assessment") or {},
                    "latest_assessment": self._assessment_dump(assessment),
                    "shadow_exit": shadow_exit,
                    "shadow_note": "Closed shadow observation only. No order intent created.",
                },
            )
        )
        session.add(
            AuditLog(
                actor="shadow_training_service",
                action="shadow_exit_recorded",
                entity_type="shadow_observation",
                entity_id=observation.id,
                message=(
                    f"{observation.market.value} {observation.symbol}: "
                    f"{exit_decision['label']} recorded in shadow mode."
                ),
                context={
                    "status": status,
                    "exit_decision": shadow_exit,
                    "orders_placed": 0,
                },
            )
        )
        self._record_risk_event(
            session,
            observation.market,
            "shadow_exit_recorded",
            (
                f"{observation.symbol}: {exit_decision['action']} at "
                f"{float(observation.current_price or 0):.2f}; no order placed."
            ),
            "INFO",
        )

    @staticmethod
    def _closed_status(action: str) -> str:
        return {
            "EXIT_STOP_LOSS": "CLOSED_SHADOW_STOP_LOSS",
            "EXIT_TAKE_PROFIT": "CLOSED_SHADOW_TAKE_PROFIT",
            "EXIT_PROFIT_BOOKING": "CLOSED_SHADOW_PROFIT_BOOKED",
            "EXIT_PROFIT_GIVEBACK": "CLOSED_SHADOW_PROFIT_GIVEBACK",
            "EXIT_SESSION_CLOSE": "CLOSED_SHADOW_SESSION_CLOSE",
        }.get(action, "CLOSED_SHADOW_EXIT")

    def _close_stale_intraday_observations(
        self,
        session: Session,
        market: Market,
        now: datetime,
    ) -> int:
        day_start = self._market_day_start_utc(market, now)
        stale_rows = session.scalars(
            select(ShadowObservation).where(
                ShadowObservation.strategy_name == self.strategy_name,
                ShadowObservation.market == market,
                ShadowObservation.status == "OPEN_OBSERVATION",
                ShadowObservation.opened_at < day_start,
            )
        ).all()
        closed = 0
        for observation in stale_rows:
            metadata = observation.metadata_json or {}
            assessment = (
                metadata.get("latest_assessment")
                or metadata.get("entry_assessment")
                or metadata.get("assessment")
                or {}
            )
            marked_at = ensure_utc(observation.last_marked_at or observation.opened_at)
            exit_time = min(marked_at, day_start - timedelta(microseconds=1))
            fx_rate = self._metadata_float(metadata.get("usd_inr"), default=1.0)
            self._close_shadow_observation(
                session=session,
                observation=observation,
                signal_id=observation.signal_id or "",
                assessment=assessment,
                fx_rate=fx_rate,
                now=exit_time,
                exit_decision={
                    "action": "EXIT_SESSION_CLOSE",
                    "label": "Intraday session close",
                    "urgency": "HIGH",
                    "reason": (
                        "Intraday shadow observations cannot carry overnight. "
                        "Closed with the last known shadow mark."
                    ),
                    "reentry_plan": (
                        "Start the next session only from a fresh signal; do not treat "
                        "yesterday's intraday idea as an overnight holding."
                    ),
                    "shadow_only": True,
                    "no_order_placement": True,
                },
            )
            closed += 1
        if closed:
            self._record_risk_event(
                session,
                market,
                "stale_intraday_shadow_closed",
                f"{closed} stale intraday shadow observations closed before new session scanning.",
                "WARN",
                context={"closed": closed, "day_start": day_start.isoformat()},
            )
        return closed

    def _active_reentry_cooldown(
        self,
        session: Session,
        market: Market,
        symbol: str,
        now: datetime,
    ) -> datetime | None:
        if self.settings.intraday_reentry_cooldown_minutes <= 0:
            return None
        latest_closed = session.scalar(
            select(ShadowObservation)
            .where(
                ShadowObservation.strategy_name == self.strategy_name,
                ShadowObservation.market == market,
                ShadowObservation.symbol == symbol,
                ShadowObservation.status != "OPEN_OBSERVATION",
            )
            .order_by(ShadowObservation.last_marked_at.desc())
            .limit(1)
        )
        if latest_closed is None:
            return None
        metadata = latest_closed.metadata_json or {}
        blocked_until_raw = metadata.get("reentry_blocked_until")
        if not blocked_until_raw:
            return None
        try:
            blocked_until = datetime.fromisoformat(str(blocked_until_raw))
        except ValueError:
            return None
        if blocked_until.tzinfo is None:
            blocked_until = blocked_until.replace(tzinfo=UTC)
        return blocked_until if blocked_until > now else None

    def _active_loss_discipline_pause(
        self,
        session: Session,
        market: Market,
        symbol: str,
        now: datetime,
    ) -> dict[str, Any] | None:
        if not self.settings.intraday_loss_discipline_enabled:
            return None

        market_pause = self._market_loss_pause(session, market, now)
        if market_pause is not None:
            return market_pause
        previous_session_pause = self._previous_session_symbol_loss_pause(
            session, market, symbol, now
        )
        if previous_session_pause is not None:
            return previous_session_pause
        return self._symbol_loss_pause(session, market, symbol, now)

    def _previous_session_symbol_loss_pause(
        self,
        session: Session,
        market: Market,
        symbol: str,
        now: datetime,
    ) -> dict[str, Any] | None:
        if not self.settings.intraday_previous_session_loss_pause_enabled:
            return None
        start_today = self._market_day_start_utc(market, now)
        cutoff = start_today - timedelta(
            days=self.settings.intraday_previous_session_loss_pause_lookback_days
        )
        sample = session.scalar(
            select(ShadowTrainingSample)
            .where(
                ShadowTrainingSample.strategy_name == self.strategy_name,
                ShadowTrainingSample.market == market,
                ShadowTrainingSample.symbol == symbol,
                ShadowTrainingSample.sample_at >= cutoff,
                ShadowTrainingSample.sample_at < start_today,
                ShadowTrainingSample.hypothetical_quantity > 0,
                ShadowTrainingSample.hypothetical_notional_inr > 0,
            )
            .order_by(ShadowTrainingSample.sample_at.desc())
            .limit(1)
        )
        if sample is None:
            return None

        pnl = float(sample.hypothetical_pnl_inr or 0)
        notional = float(sample.hypothetical_notional_inr or 0)
        pnl_pct = pnl / notional if notional > 0 else 0.0
        threshold_hit = (
            pnl <= -self.settings.intraday_previous_session_loss_pause_inr
            or pnl_pct <= -self.settings.intraday_previous_session_loss_pause_pct
        )
        if not threshold_hit:
            return None

        return {
            "scope": "PREVIOUS_SESSION_SYMBOL",
            "reason": (
                f"Latest previous-session mark for {market.value} {symbol} ended at "
                f"{pnl:.2f} INR ({pnl_pct:.2%}). Pause fresh entry today until a "
                "new high-quality setup appears; do not blindly retry yesterday's loser."
            ),
            "sample_at": sample.sample_at.isoformat(),
            "total_pnl_inr": pnl,
            "pnl_pct": pnl_pct,
            "shadow_only": True,
            "no_order_placement": True,
        }

    def _market_day_start_utc(self, market: Market, now: datetime) -> datetime:
        timezone_name = (
            self.settings.india_timezone if market == Market.INDIA else self.settings.us_timezone
        )
        local_now = as_timezone(ensure_utc(now), timezone_name)
        local_start = datetime.combine(local_now.date(), time.min, tzinfo=local_now.tzinfo)
        return ensure_utc(local_start)

    def _symbol_loss_pause(
        self,
        session: Session,
        market: Market,
        symbol: str,
        now: datetime,
    ) -> dict[str, Any] | None:
        samples = self._recent_training_samples(
            session,
            market=market,
            symbol=symbol,
            now=now,
            limit=max(self.settings.intraday_symbol_loss_pause_min_samples, 1),
        )
        sample_count = len(samples)
        if sample_count < self.settings.intraday_symbol_loss_pause_min_samples:
            return None

        losers = [sample for sample in samples if float(sample.hypothetical_pnl_inr or 0) < 0]
        loss_rate = len(losers) / sample_count
        total_pnl = sum(float(sample.hypothetical_pnl_inr or 0) for sample in samples)
        total_notional = sum(float(sample.hypothetical_notional_inr or 0) for sample in samples)
        pnl_pct = total_pnl / total_notional if total_notional > 0 else 0.0
        loss_threshold_hit = (
            total_pnl <= -self.settings.intraday_symbol_loss_pause_inr
            or pnl_pct <= -self.settings.intraday_symbol_loss_pause_pct
        )
        if loss_rate < self.settings.intraday_symbol_loss_pause_loss_rate or not loss_threshold_hit:
            return None

        return {
            "scope": "SYMBOL",
            "reason": (
                f"Recent {market.value} {symbol} samples show {loss_rate:.0%} losing marks, "
                f"{total_pnl:.2f} INR shadow P&L, and {pnl_pct:.2%} return over the "
                f"last {sample_count} samples. Wait for a cleaner setup instead of "
                "opening a fresh shadow entry."
            ),
            "sample_count": sample_count,
            "loss_rate": loss_rate,
            "total_pnl_inr": total_pnl,
            "pnl_pct": pnl_pct,
            "shadow_only": True,
            "no_order_placement": True,
        }

    def _market_loss_pause(
        self,
        session: Session,
        market: Market,
        now: datetime,
    ) -> dict[str, Any] | None:
        samples = self._recent_training_samples(
            session,
            market=market,
            symbol=None,
            now=now,
            limit=max(self.settings.intraday_market_loss_pause_min_samples, 1),
        )
        sample_count = len(samples)
        if sample_count < self.settings.intraday_market_loss_pause_min_samples:
            return None

        winners = [sample for sample in samples if float(sample.hypothetical_pnl_inr or 0) > 0]
        win_rate = len(winners) / sample_count
        total_pnl = sum(float(sample.hypothetical_pnl_inr or 0) for sample in samples)
        if (
            win_rate > self.settings.intraday_market_loss_pause_win_rate
            or total_pnl > -self.settings.intraday_market_loss_pause_inr
        ):
            return None

        return {
            "scope": "MARKET",
            "reason": (
                f"Recent {market.value} market samples show only {win_rate:.0%} winners "
                f"and {total_pnl:.2f} INR shadow P&L across the last {sample_count} "
                "samples. Pause new entries and keep only risk/profit-protection updates."
            ),
            "sample_count": sample_count,
            "win_rate": win_rate,
            "total_pnl_inr": total_pnl,
            "shadow_only": True,
            "no_order_placement": True,
        }

    def _recent_training_samples(
        self,
        session: Session,
        *,
        market: Market,
        symbol: str | None,
        now: datetime,
        limit: int,
    ) -> list[ShadowTrainingSample]:
        lookback_start = now - timedelta(minutes=self.settings.intraday_loss_discipline_lookback_minutes)
        query = (
            select(ShadowTrainingSample)
            .where(
                ShadowTrainingSample.strategy_name == self.strategy_name,
                ShadowTrainingSample.market == market,
                ShadowTrainingSample.sample_at >= lookback_start,
                ShadowTrainingSample.hypothetical_quantity > 0,
                ShadowTrainingSample.hypothetical_notional_inr > 0,
            )
            .order_by(ShadowTrainingSample.sample_at.desc())
            .limit(limit)
        )
        if symbol is not None:
            query = query.where(ShadowTrainingSample.symbol == symbol)
        return list(session.scalars(query).all())

    def _record_risk_event(
        self,
        session: Session,
        market: Market,
        event_type: str,
        message: str,
        severity: str = "INFO",
        context: dict[str, Any] | None = None,
    ) -> None:
        session.add(
            RiskEvent(
                market=market,
                event_type=event_type,
                severity=severity,
                message=message,
                context={"shadow_training": True, **(context or {})},
            )
        )

    def _run_intraday_model_training(self, session: Session) -> dict[str, Any]:
        try:
            return intraday_model_training_service.train_shadow_only(session)
        except Exception as exc:
            session.add(
                AuditLog(
                    actor="shadow_training_service",
                    action="intraday_shadow_model_training_failed",
                    entity_type="intraday_shadow_model",
                    message="Shadow model training report failed; order placement remains disabled.",
                    context={"error": str(exc), "shadow_only": True},
                )
            )
            return {
                "status": "TRAINING_REPORT_FAILED",
                "error": str(exc),
                "shadow_only": True,
                "no_order_placement": True,
            }

    @staticmethod
    def _assessment_dump(assessment: Any) -> dict[str, Any]:
        if hasattr(assessment, "model_dump"):
            return assessment.model_dump()
        return assessment if isinstance(assessment, dict) else {}

    @staticmethod
    def _metadata_float(value: object, *, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _extract_last_price(quote: dict[str, Any]) -> float | None:
        data = quote.get("data")
        if isinstance(data, dict) and data:
            first = next(iter(data.values()))
            if isinstance(first, dict) and first.get("last_price") is not None:
                return float(first["last_price"])
        return None


shadow_training_service = ShadowTrainingService()
