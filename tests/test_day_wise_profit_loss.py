from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.enums import Market
from app.db.base import Base
from app.db.models.shadow import ShadowTrainingSample
from app.services.performance_service import PerformanceService


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def _sample(
    *,
    market: Market,
    symbol: str,
    sample_at: datetime,
    pnl: float,
) -> ShadowTrainingSample:
    return ShadowTrainingSample(
        strategy_name="shadow_training_observation_v1",
        market=market,
        symbol=symbol,
        sample_at=sample_at,
        entry_price=100,
        current_price=100 + pnl / 100,
        hypothetical_quantity=100,
        hypothetical_notional_inr=10_000,
        hypothetical_pnl_inr=pnl,
        hypothetical_pnl_pct=pnl / 10_000,
        sample_kind="INTRADAY_MARK",
        metadata_json={"assessment": {"stop_loss": 98, "take_profit": 106}},
    )


def test_day_wise_profit_loss_uses_latest_stock_mark_per_day() -> None:
    settings = Settings(_env_file=None)
    now = datetime(2026, 5, 8, 15, 0, tzinfo=UTC)

    with _session() as session:
        session.add_all(
            [
                _sample(
                    market=Market.INDIA,
                    symbol="RELIANCE",
                    sample_at=now - timedelta(minutes=10),
                    pnl=100,
                ),
                _sample(
                    market=Market.INDIA,
                    symbol="RELIANCE",
                    sample_at=now,
                    pnl=250,
                ),
                _sample(
                    market=Market.INDIA,
                    symbol="TCS",
                    sample_at=now,
                    pnl=-125,
                ),
                _sample(
                    market=Market.US,
                    symbol="AAPL",
                    sample_at=now,
                    pnl=75,
                ),
            ]
        )

        payload = PerformanceService._day_wise_profit_loss_summary(session, settings)

    latest = payload["latest_day"]
    assert latest["shadow_invested_count"] == 3
    assert latest["hypothetical_pnl_inr"] == 200
    assert latest["winners"] == 2
    assert latest["losers"] == 1
    assert latest["markets"]["INDIA"]["hypothetical_pnl_inr"] == 125
    assert latest["markets"]["US"]["hypothetical_pnl_inr"] == 75
    assert latest["good_stocks"][0]["symbol"] == "RELIANCE"
    assert latest["loss_stocks"][0]["symbol"] == "TCS"
