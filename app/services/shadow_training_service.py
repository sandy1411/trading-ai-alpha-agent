from __future__ import annotations

from datetime import UTC, datetime
from math import floor
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import AssetClass, Market, RiskDecisionType
from app.core.errors import TradingAlphaError
from app.data_providers.alpaca_data import AlpacaDataProvider
from app.data_providers.fx_provider import FXProvider
from app.data_providers.zerodha_data import ZerodhaDataProvider
from app.db.models.audit import AuditLog
from app.db.models.instrument import Instrument
from app.db.models.risk import RiskDecisionModel, RiskEvent
from app.db.models.shadow import ShadowObservation
from app.db.models.signal import AgentSignal
from app.db.models.strategy import Strategy
from app.db.session import SessionLocal
from app.risk.market_calendar import MarketCalendar
from app.services.intraday_model_training_service import intraday_model_training_service
from app.strategies.conservative_shadow import ConservativeShadowStrategy


class ShadowTrainingService:
    strategy_name = "shadow_training_observation_v1"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.calendar = MarketCalendar(self.settings)
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
            self._run_india_cycle(session, strategy, result)
            self._run_us_cycle(session, strategy, result)
            result["intraday_model_training"] = self._run_intraday_model_training(session)
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
                    self._record_shadow_observation(
                        session, instrument, symbol, signal.id, last_price, assessment
                    )
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
                    self._record_shadow_observation(
                        session,
                        instrument,
                        symbol,
                        signal.id,
                        last_price,
                        assessment,
                        market=Market.US,
                        fx_rate=fx_status.rate,
                    )
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
    ) -> None:
        observation = session.scalar(
            select(ShadowObservation).where(
                ShadowObservation.strategy_name == self.strategy_name,
                ShadowObservation.market == market,
                ShadowObservation.symbol == symbol,
                ShadowObservation.status == "OPEN_OBSERVATION",
            )
        )
        now = datetime.now(UTC)
        if observation is None:
            price_inr = last_price * fx_rate
            quantity = floor(self.settings.shadow_hypothesis_notional_inr / price_inr)
            notional = quantity * last_price * fx_rate
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
                    "assessment": assessment.model_dump(),
                },
            )
            session.add(observation)
            return

        entry_price = float(observation.entry_price)
        quantity = observation.hypothetical_quantity
        pnl = (last_price - entry_price) * quantity * fx_rate
        pnl_pct = pnl / float(observation.hypothetical_notional_inr or 1)
        observation.signal_id = signal_id
        observation.current_price = last_price
        observation.last_marked_at = now
        observation.hypothetical_pnl_inr = pnl
        observation.hypothetical_pnl_pct = pnl_pct
        observation.metadata_json = {
            **(observation.metadata_json or {}),
            "source": "ALPACA_DATA" if market == Market.US else "ZERODHA_KITE_QUOTE",
            "price_currency": "USD" if market == Market.US else "INR",
            "usd_inr": fx_rate,
            "assessment": assessment.model_dump(),
        }

    def _record_risk_event(
        self,
        session: Session,
        market: Market,
        event_type: str,
        message: str,
        severity: str = "INFO",
    ) -> None:
        session.add(
            RiskEvent(
                market=market,
                event_type=event_type,
                severity=severity,
                message=message,
                context={"shadow_training": True},
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
    def _extract_last_price(quote: dict[str, Any]) -> float | None:
        data = quote.get("data")
        if isinstance(data, dict) and data:
            first = next(iter(data.values()))
            if isinstance(first, dict) and first.get("last_price") is not None:
                return float(first["last_price"])
        return None


shadow_training_service = ShadowTrainingService()
