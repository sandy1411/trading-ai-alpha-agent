from __future__ import annotations

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.errors import FailClosedError
from app.core.enums import FreshnessStatus, Market, MarketCalendarState
from app.db.base import Base
from app.db.models.order import Order
from app.db.models.shadow import ShadowObservation
from app.schemas.fx import FXRateStatus
from app.risk.market_calendar import MarketCalendarStatus
from app.core.time_utils import utc_now
from app.services import shadow_training_service as shadow_module
from app.services.shadow_training_service import ShadowTrainingService


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
        order_count = session.scalar(select(func.count()).select_from(Order))

    assert result["orders_placed"] == 0
    assert result["shadow_observations_updated"] == 1
    assert observation is not None
    assert observation.hypothetical_quantity == 4
    assert float(observation.hypothetical_notional_inr) == 10000
    assert observation.metadata_json["assessment"]["stop_loss"] < 2500
    assert observation.metadata_json["assessment"]["take_profit"] > 2500
    assert observation.metadata_json["assessment"]["reward_risk_ratio"] >= 1.8
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
        order_count = session.scalar(select(func.count()).select_from(Order))

    assert result["orders_placed"] == 0
    assert result["us"]["observed"] == 1
    assert observation is not None
    assert observation.market == Market.US
    assert observation.hypothetical_quantity == 1
    assert float(observation.hypothetical_notional_inr) == 8300
    assert observation.metadata_json["price_currency"] == "USD"
    assert observation.metadata_json["usd_inr"] == 83.0
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
