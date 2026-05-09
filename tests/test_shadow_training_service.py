from __future__ import annotations

from datetime import timedelta

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.errors import FailClosedError
from app.core.enums import FreshnessStatus, Market, MarketCalendarState, TradeAction
from app.db.base import Base
from app.db.models.order import Order
from app.db.models.risk import RiskEvent
from app.db.models.shadow import ShadowObservation, ShadowTrainingSample
from app.schemas.fx import FXRateStatus
from app.risk.market_calendar import MarketCalendarStatus
from app.core.time_utils import utc_now
from app.services import shadow_training_service as shadow_module
from app.services.shadow_training_service import ShadowTrainingService


class _Assessment:
    def __init__(
        self,
        *,
        stop_loss: float = 98.0,
        take_profit: float = 110.0,
    ) -> None:
        self.action = TradeAction.BUY
        self.confidence = 0.72
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.expected_risk = 2.0
        self.expected_reward = 10.0
        self.reward_risk_ratio = 5.0
        self.reasons = ["test_shadow_buy_hypothesis"]
        self.risk_flags = ["observation_only_no_order_intent"]
        self.metrics = {"last_price": 0.0}

    def model_dump(self) -> dict:
        return {
            "action": self.action.value,
            "confidence": self.confidence,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "expected_risk": self.expected_risk,
            "expected_reward": self.expected_reward,
            "reward_risk_ratio": self.reward_risk_ratio,
            "reasons": self.reasons,
            "risk_flags": self.risk_flags,
            "metrics": self.metrics,
        }


class _FixedExitStrategy:
    def __init__(self, assessments: list[_Assessment] | None = None) -> None:
        self.assessments = assessments or [_Assessment()]
        self.calls = 0

    def assess(self, quote: dict, last_price: float | None) -> _Assessment:
        index = min(self.calls, len(self.assessments) - 1)
        self.calls += 1
        assessment = self.assessments[index]
        assessment.metrics = {"last_price": float(last_price or 0)}
        return assessment


class _SequenceProvider:
    prices: list[float] = []
    calls = 0

    def __init__(self, settings) -> None:
        self.settings = settings

    def latest(self, symbol: str, market: Market) -> dict:
        index = min(self.__class__.calls, len(self.__class__.prices) - 1)
        self.__class__.calls += 1
        price = self.__class__.prices[index]
        return {
            "data": {
                f"NSE:{symbol}": {
                    "last_price": price,
                    "average_price": price,
                    "volume": 100000,
                    "ohlc": {
                        "open": price,
                        "high": price,
                        "low": price,
                        "close": price,
                    },
                }
            }
        }


def test_shadow_training_cycle_never_creates_orders(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    settings = Settings(
        _env_file=None,
        shadow_training_enabled=True,
        shadow_india_symbols="RELIANCE",
        shadow_us_symbols="SPY",
    )
    service = ShadowTrainingService(settings)
    monkeypatch.setattr(
        service.calendar,
        "status",
        lambda market: MarketCalendarStatus(
            market=market,
            state=MarketCalendarState.CLOSED,
            reason="test_market_closed",
        ),
    )

    with session_factory() as session:
        result = service.run_cycle(session)
        order_count = session.scalar(select(func.count()).select_from(Order))

    assert result["status"] == "completed"
    assert result["orders_placed"] == 0
    assert result["india"]["blocked"] == ["india_market_not_open:test_market_closed"]
    assert result["us"]["blocked"] == ["us_market_not_open:test_market_closed"]
    assert order_count == 0


def test_shadow_training_records_hypothesis_without_order(monkeypatch) -> None:
    class ProviderStub:
        def __init__(self, settings) -> None:
            self.settings = settings

        def latest(self, symbol: str, market: Market) -> dict:
            return {
                "data": {
                    f"NSE:{symbol}": {
                        "last_price": 2500.0,
                        "average_price": 2480.0,
                        "volume": 100000,
                        "ohlc": {
                            "open": 2475.0,
                            "high": 2525.0,
                            "low": 2460.0,
                            "close": 2465.0,
                        },
                    }
                }
            }

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    settings = Settings(
        _env_file=None,
        shadow_training_enabled=True,
        shadow_hypothesis_notional_inr=10000,
        shadow_india_symbols="RELIANCE",
        shadow_us_symbols="",
    )
    service = ShadowTrainingService(settings)
    monkeypatch.setattr(
        service.calendar,
        "status",
        lambda market: MarketCalendarStatus(
            market=market,
            state=MarketCalendarState.OPEN,
            reason="regular_session_open",
        ),
    )
    monkeypatch.setattr(shadow_module, "ZerodhaDataProvider", ProviderStub)

    with session_factory() as session:
        result = service.run_cycle(session)
        observation = session.scalar(select(ShadowObservation))
        sample = session.scalar(select(ShadowTrainingSample))
        order_count = session.scalar(select(func.count()).select_from(Order))

    assert result["orders_placed"] == 0
    assert result["shadow_observations_updated"] == 1
    assert observation is not None
    assert observation.hypothetical_quantity == 4
    assert float(observation.hypothetical_notional_inr) == 10000
    assert observation.metadata_json["assessment"]["stop_loss"] < 2500
    assert observation.metadata_json["assessment"]["take_profit"] > 2500
    assert observation.metadata_json["assessment"]["reward_risk_ratio"] >= 1.8
    assert sample is not None
    assert sample.observation_id == observation.id
    assert sample.sample_kind == "INTRADAY_MARK"
    assert order_count == 0


def test_shadow_training_does_not_open_new_observation_for_no_trade_signal(monkeypatch) -> None:
    class ProviderStub:
        def __init__(self, settings) -> None:
            self.settings = settings

        def latest(self, symbol: str, market: Market) -> dict:
            return {
                "data": {
                    f"NSE:{symbol}": {
                        "last_price": 100.0,
                        "average_price": 101.0,
                        "volume": 100000,
                        "ohlc": {
                            "open": 102.0,
                            "high": 103.0,
                            "low": 99.0,
                            "close": 101.0,
                        },
                    }
                }
            }

    class NoTradeStrategy:
        def assess(self, quote: dict, last_price: float | None) -> _Assessment:
            assessment = _Assessment(stop_loss=98, take_profit=110)
            assessment.action = TradeAction.NO_TRADE
            assessment.confidence = 0.25
            assessment.risk_flags = [
                "observation_only_no_order_intent",
                "quality_filter_did_not_clear_buy_threshold",
            ]
            assessment.reasons = ["test_no_trade_quality_block"]
            return assessment

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    settings = Settings(
        _env_file=None,
        shadow_training_enabled=True,
        shadow_hypothesis_notional_inr=10000,
        shadow_india_symbols="RELIANCE",
        shadow_us_symbols="",
    )
    service = ShadowTrainingService(settings)
    service.strategy = NoTradeStrategy()
    monkeypatch.setattr(
        service.calendar,
        "status",
        lambda market: MarketCalendarStatus(
            market=market,
            state=MarketCalendarState.OPEN,
            reason="regular_session_open",
        ),
    )
    monkeypatch.setattr(shadow_module, "ZerodhaDataProvider", ProviderStub)

    with session_factory() as session:
        result = service.run_cycle(session)
        observation_count = session.scalar(select(func.count()).select_from(ShadowObservation))
        sample_count = session.scalar(select(func.count()).select_from(ShadowTrainingSample))
        quality_event = session.scalar(
            select(RiskEvent).where(RiskEvent.event_type == "shadow_entry_quality_blocked")
        )
        order_count = session.scalar(select(func.count()).select_from(Order))

    assert result["orders_placed"] == 0
    assert result["india"]["observed"] == 1
    assert result["shadow_observations_updated"] == 0
    assert observation_count == 0
    assert sample_count == 0
    assert quality_event is not None
    assert "NO_TRADE" in quality_event.message
    assert order_count == 0


def test_shadow_training_appends_timestamped_samples_without_duplicate_open_observations(monkeypatch) -> None:
    class ProviderStub:
        calls = 0

        def __init__(self, settings) -> None:
            self.settings = settings

        def latest(self, symbol: str, market: Market) -> dict:
            self.__class__.calls += 1
            last_price = 2500.0 + self.__class__.calls * 10
            return {
                "data": {
                    f"NSE:{symbol}": {
                        "last_price": last_price,
                        "average_price": 2480.0,
                        "volume": 100000,
                        "ohlc": {
                            "open": 2475.0,
                            "high": last_price + 25.0,
                            "low": 2460.0,
                            "close": 2465.0,
                        },
                    }
                }
            }

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    settings = Settings(
        _env_file=None,
        shadow_training_enabled=True,
        shadow_hypothesis_notional_inr=10000,
        shadow_india_symbols="RELIANCE",
        shadow_us_symbols="",
    )
    service = ShadowTrainingService(settings)
    monkeypatch.setattr(
        service.calendar,
        "status",
        lambda market: MarketCalendarStatus(
            market=market,
            state=MarketCalendarState.OPEN,
            reason="regular_session_open",
        ),
    )
    monkeypatch.setattr(shadow_module, "ZerodhaDataProvider", ProviderStub)

    with session_factory() as session:
        first = service.run_cycle(session)
        second = service.run_cycle(session)
        observation_count = session.scalar(select(func.count()).select_from(ShadowObservation))
        sample_count = session.scalar(select(func.count()).select_from(ShadowTrainingSample))
        order_count = session.scalar(select(func.count()).select_from(Order))

    assert first["shadow_observations_updated"] == 1
    assert second["shadow_observations_updated"] == 1
    assert observation_count == 1
    assert sample_count == 2
    assert order_count == 0


def test_shadow_training_books_profit_and_blocks_immediate_reentry(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    settings = Settings(
        _env_file=None,
        shadow_training_enabled=True,
        shadow_hypothesis_notional_inr=10000,
        shadow_india_symbols="RELIANCE",
        shadow_us_symbols="",
        intraday_profit_booking_enabled=True,
        intraday_profit_booking_target_progress_pct=0.45,
        intraday_profit_booking_min_pnl_inr=250,
        intraday_reentry_cooldown_minutes=20,
    )
    service = ShadowTrainingService(settings)
    service.strategy = _FixedExitStrategy(
        [
            _Assessment(stop_loss=98, take_profit=110),
            _Assessment(stop_loss=98, take_profit=200),
            _Assessment(stop_loss=98, take_profit=200),
        ]
    )
    _SequenceProvider.prices = [100.0, 104.6, 105.0]
    _SequenceProvider.calls = 0
    monkeypatch.setattr(
        service.calendar,
        "status",
        lambda market: MarketCalendarStatus(
            market=market,
            state=MarketCalendarState.OPEN,
            reason="regular_session_open",
        ),
    )
    monkeypatch.setattr(shadow_module, "ZerodhaDataProvider", _SequenceProvider)

    with session_factory() as session:
        first = service.run_cycle(session)
        second = service.run_cycle(session)
        third = service.run_cycle(session)
        observations = session.scalars(select(ShadowObservation)).all()
        samples = session.scalars(
            select(ShadowTrainingSample).order_by(ShadowTrainingSample.sample_at.asc())
        ).all()
        order_count = session.scalar(select(func.count()).select_from(Order))

    assert first["shadow_observations_updated"] == 1
    assert second["shadow_observations_updated"] == 1
    assert third["shadow_observations_updated"] == 0
    assert len(observations) == 1
    assert observations[0].status == "CLOSED_SHADOW_PROFIT_BOOKED"
    assert observations[0].metadata_json["shadow_exit"]["action"] == "EXIT_PROFIT_BOOKING"
    assert observations[0].metadata_json["shadow_exit"]["no_order_placement"] is True
    assert observations[0].metadata_json["assessment"]["take_profit"] == 110
    assert observations[0].metadata_json["latest_assessment"]["take_profit"] == 200
    assert [sample.sample_kind for sample in samples] == [
        "INTRADAY_MARK",
        "INTRADAY_MARK",
        "SHADOW_EXIT",
    ]
    assert samples[-1].metadata_json["shadow_exit"]["action"] == "EXIT_PROFIT_BOOKING"
    assert order_count == 0


def test_shadow_training_exits_on_profit_giveback_from_peak(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    settings = Settings(
        _env_file=None,
        shadow_training_enabled=True,
        shadow_hypothesis_notional_inr=10000,
        shadow_india_symbols="RELIANCE",
        shadow_us_symbols="",
        intraday_profit_giveback_exit_pct=0.25,
        intraday_min_profit_lock_inr=300,
        intraday_profit_booking_enabled=True,
        intraday_profit_booking_target_progress_pct=0.90,
    )
    service = ShadowTrainingService(settings)
    service.strategy = _FixedExitStrategy([_Assessment(stop_loss=95, take_profit=120)])
    _SequenceProvider.prices = [100.0, 108.0, 103.0]
    _SequenceProvider.calls = 0
    monkeypatch.setattr(
        service.calendar,
        "status",
        lambda market: MarketCalendarStatus(
            market=market,
            state=MarketCalendarState.OPEN,
            reason="regular_session_open",
        ),
    )
    monkeypatch.setattr(shadow_module, "ZerodhaDataProvider", _SequenceProvider)

    with session_factory() as session:
        first = service.run_cycle(session)
        second = service.run_cycle(session)
        third = service.run_cycle(session)
        observation = session.scalar(select(ShadowObservation))
        exit_sample = session.scalar(
            select(ShadowTrainingSample).where(ShadowTrainingSample.sample_kind == "SHADOW_EXIT")
        )
        order_count = session.scalar(select(func.count()).select_from(Order))

    assert first["shadow_observations_updated"] == 1
    assert second["shadow_observations_updated"] == 1
    assert third["shadow_observations_updated"] == 1
    assert observation is not None
    assert observation.status == "CLOSED_SHADOW_PROFIT_GIVEBACK"
    assert observation.metadata_json["shadow_exit"]["action"] == "EXIT_PROFIT_GIVEBACK"
    assert observation.metadata_json["shadow_exit"]["peak_pnl_inr"] == 800
    assert observation.metadata_json["shadow_exit"]["giveback_inr"] == 500
    assert exit_sample is not None
    assert exit_sample.metadata_json["shadow_exit"]["action"] == "EXIT_PROFIT_GIVEBACK"
    assert order_count == 0


def test_us_shadow_training_requires_real_data_and_fx_but_never_orders(monkeypatch) -> None:
    class AlpacaProviderStub:
        def __init__(self, settings) -> None:
            self.settings = settings

        def latest(self, symbol: str, market: Market) -> dict:
            return {
                "data": {
                    f"US:{symbol}": {
                        "last_price": 100.0,
                        "average_price": 99.5,
                        "volume": 100000,
                        "ohlc": {
                            "open": 98.0,
                            "high": 101.0,
                            "low": 97.5,
                            "close": 97.0,
                        },
                    }
                }
            }

    class FXProviderStub:
        def __init__(self, settings) -> None:
            self.settings = settings

        def get_usd_inr(self) -> FXRateStatus:
            return FXRateStatus(
                rate=83.0,
                freshness_status=FreshnessStatus.FRESH,
                last_success_at=utc_now(),
                source="ALPHA_VANTAGE_FX",
            )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    settings = Settings(
        _env_file=None,
        alpaca_api_key="key",
        alpaca_secret_key="secret",
        alpha_vantage_api_key="fx",
        shadow_training_enabled=True,
        shadow_hypothesis_notional_inr=10000,
        shadow_india_symbols="",
        shadow_us_symbols="SPY",
    )
    service = ShadowTrainingService(settings)
    monkeypatch.setattr(
        service.calendar,
        "status",
        lambda market: MarketCalendarStatus(
            market=market,
            state=MarketCalendarState.OPEN,
            reason="regular_session_open",
        ),
    )
    monkeypatch.setattr(shadow_module, "AlpacaDataProvider", AlpacaProviderStub)
    monkeypatch.setattr(shadow_module, "FXProvider", FXProviderStub)

    with session_factory() as session:
        result = service.run_cycle(session)
        observation = session.scalar(select(ShadowObservation))
        sample = session.scalar(select(ShadowTrainingSample))
        order_count = session.scalar(select(func.count()).select_from(Order))

    assert result["orders_placed"] == 0
    assert result["us"]["observed"] == 1
    assert observation is not None
    assert observation.market == Market.US
    assert observation.hypothetical_quantity == 1
    assert float(observation.hypothetical_notional_inr) == 8300
    assert observation.metadata_json["price_currency"] == "USD"
    assert observation.metadata_json["usd_inr"] == 83.0
    assert sample is not None
    assert sample.market == Market.US
    assert order_count == 0


def test_us_symbol_failure_blocks_symbol_without_aborting_india(monkeypatch) -> None:
    class ZerodhaProviderStub:
        def __init__(self, settings) -> None:
            self.settings = settings

        def latest(self, symbol: str, market: Market) -> dict:
            return {
                "data": {
                    f"NSE:{symbol}": {
                        "last_price": 2500.0,
                        "average_price": 2480.0,
                        "volume": 100000,
                        "ohlc": {
                            "open": 2475.0,
                            "high": 2525.0,
                            "low": 2460.0,
                            "close": 2465.0,
                        },
                    }
                }
            }

    class AlpacaProviderFailureStub:
        def __init__(self, settings) -> None:
            self.settings = settings

        def latest(self, symbol: str, market: Market) -> dict:
            raise FailClosedError("alpaca_bar_request_failed")

    class FXProviderStub:
        def __init__(self, settings) -> None:
            self.settings = settings

        def get_usd_inr(self) -> FXRateStatus:
            return FXRateStatus(
                rate=83.0,
                freshness_status=FreshnessStatus.FRESH,
                last_success_at=utc_now(),
                source="ALPHA_VANTAGE_FX",
            )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    settings = Settings(
        _env_file=None,
        alpaca_api_key="key",
        alpaca_secret_key="secret",
        alpha_vantage_api_key="fx",
        shadow_training_enabled=True,
        shadow_hypothesis_notional_inr=10000,
        shadow_india_symbols="RELIANCE",
        shadow_us_symbols="SPY",
    )
    service = ShadowTrainingService(settings)
    monkeypatch.setattr(
        service.calendar,
        "status",
        lambda market: MarketCalendarStatus(
            market=market,
            state=MarketCalendarState.OPEN,
            reason="regular_session_open",
        ),
    )
    monkeypatch.setattr(shadow_module, "ZerodhaDataProvider", ZerodhaProviderStub)
    monkeypatch.setattr(shadow_module, "AlpacaDataProvider", AlpacaProviderFailureStub)
    monkeypatch.setattr(shadow_module, "FXProvider", FXProviderStub)

    with session_factory() as session:
        result = service.run_cycle(session)

    assert result["status"] == "completed"
    assert result["india"]["observed"] == 1
    assert result["us"]["observed"] == 0
    assert result["us"]["blocked"] == ["SPY:alpaca_bar_request_failed"]
    assert result["orders_placed"] == 0


def test_loss_discipline_pauses_fresh_symbol_entry_after_repeated_losing_samples(monkeypatch) -> None:
    class ProviderStub:
        def __init__(self, settings) -> None:
            self.settings = settings

        def latest(self, symbol: str, market: Market) -> dict:
            return {
                "data": {
                    f"NSE:{symbol}": {
                        "last_price": 100.0,
                        "average_price": 100.0,
                        "volume": 100000,
                        "ohlc": {
                            "open": 100.0,
                            "high": 101.0,
                            "low": 99.0,
                            "close": 99.5,
                        },
                    }
                }
            }

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    settings = Settings(
        _env_file=None,
        shadow_training_enabled=True,
        shadow_hypothesis_notional_inr=10000,
        shadow_india_symbols="RELIANCE",
        shadow_us_symbols="",
        intraday_loss_discipline_enabled=True,
        intraday_symbol_loss_pause_min_samples=3,
        intraday_symbol_loss_pause_loss_rate=0.60,
        intraday_symbol_loss_pause_inr=100,
        intraday_symbol_loss_pause_pct=0.001,
        intraday_market_loss_pause_min_samples=20,
    )
    service = ShadowTrainingService(settings)
    service.strategy = _FixedExitStrategy([_Assessment()])
    monkeypatch.setattr(
        service.calendar,
        "status",
        lambda market: MarketCalendarStatus(
            market=market,
            state=MarketCalendarState.OPEN,
            reason="regular_session_open",
        ),
    )
    monkeypatch.setattr(shadow_module, "ZerodhaDataProvider", ProviderStub)

    with session_factory() as session:
        for index in range(3):
            session.add(
                ShadowTrainingSample(
                    strategy_name=service.strategy_name,
                    market=Market.INDIA,
                    symbol="RELIANCE",
                    sample_at=utc_now(),
                    entry_price=100,
                    current_price=98 - index,
                    hypothetical_quantity=100,
                    hypothetical_notional_inr=10000,
                    hypothetical_pnl_inr=-200 - index,
                    hypothetical_pnl_pct=-0.02,
                    sample_kind="INTRADAY_MARK",
                    metadata_json={"shadow_only": True},
                )
            )
        session.commit()

        result = service.run_cycle(session)
        observation_count = session.scalar(select(func.count()).select_from(ShadowObservation))
        pause_event = session.scalar(
            select(RiskEvent).where(RiskEvent.event_type == "shadow_loss_discipline_pause")
        )
        order_count = session.scalar(select(func.count()).select_from(Order))

    assert result["orders_placed"] == 0
    assert result["india"]["observed"] == 1
    assert result["shadow_observations_updated"] == 0
    assert observation_count == 0
    assert pause_event is not None
    assert "new shadow entry paused" in pause_event.message
    assert order_count == 0


def test_previous_session_loss_pauses_next_day_fresh_entry(monkeypatch) -> None:
    class ProviderStub:
        def __init__(self, settings) -> None:
            self.settings = settings

        def latest(self, symbol: str, market: Market) -> dict:
            return {
                "data": {
                    f"NSE:{symbol}": {
                        "last_price": 100.0,
                        "average_price": 100.0,
                        "volume": 100000,
                        "ohlc": {
                            "open": 99.0,
                            "high": 101.0,
                            "low": 98.0,
                            "close": 98.0,
                        },
                    }
                }
            }

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    settings = Settings(
        _env_file=None,
        shadow_training_enabled=True,
        shadow_hypothesis_notional_inr=10000,
        shadow_india_symbols="TCS",
        shadow_us_symbols="",
        intraday_previous_session_loss_pause_enabled=True,
        intraday_previous_session_loss_pause_lookback_days=3,
        intraday_previous_session_loss_pause_inr=750,
        intraday_previous_session_loss_pause_pct=0.0075,
        intraday_market_loss_pause_min_samples=20,
    )
    service = ShadowTrainingService(settings)
    monkeypatch.setattr(
        service.calendar,
        "status",
        lambda market: MarketCalendarStatus(
            market=market,
            state=MarketCalendarState.OPEN,
            reason="regular_session_open",
        ),
    )
    monkeypatch.setattr(shadow_module, "ZerodhaDataProvider", ProviderStub)

    with session_factory() as session:
        session.add(
            ShadowTrainingSample(
                strategy_name=service.strategy_name,
                market=Market.INDIA,
                symbol="TCS",
                sample_at=utc_now() - timedelta(days=1),
                entry_price=100,
                current_price=88,
                hypothetical_quantity=100,
                hypothetical_notional_inr=10000,
                hypothetical_pnl_inr=-1200,
                hypothetical_pnl_pct=-0.12,
                sample_kind="INTRADAY_MARK",
                metadata_json={"shadow_only": True},
            )
        )
        session.commit()

        result = service.run_cycle(session)
        observation_count = session.scalar(select(func.count()).select_from(ShadowObservation))
        pause_event = session.scalar(
            select(RiskEvent).where(RiskEvent.event_type == "shadow_loss_discipline_pause")
        )
        order_count = session.scalar(select(func.count()).select_from(Order))

    assert result["orders_placed"] == 0
    assert result["india"]["observed"] == 1
    assert result["shadow_observations_updated"] == 0
    assert observation_count == 0
    assert pause_event is not None
    assert "previous-session" in pause_event.message
    assert order_count == 0
