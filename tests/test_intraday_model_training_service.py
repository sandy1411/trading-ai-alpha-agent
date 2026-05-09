from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.enums import AssetClass, Market, TradeAction
from app.core.time_utils import utc_now
from app.db.base import Base
from app.db.models.instrument import Instrument
from app.db.models.order import Order
from app.db.models.shadow import ShadowObservation, ShadowTrainingSample
from app.db.models.signal import AgentSignal
from app.services.intraday_model_training_service import IntradayModelTrainingService


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def _observation(
    *,
    market: Market = Market.INDIA,
    symbol: str = "RELIANCE",
    entry_price: float = 100.0,
    current_price: float = 103.0,
    pnl_inr: float = 300.0,
    stop_loss: float | None = 98.0,
    take_profit: float | None = 106.0,
    reward_risk_ratio: float | None = 3.0,
) -> ShadowObservation:
    return ShadowObservation(
        strategy_name="shadow_training_observation_v1",
        market=market,
        symbol=symbol,
        opened_at=utc_now(),
        last_marked_at=utc_now(),
        entry_price=entry_price,
        current_price=current_price,
        hypothetical_quantity=100,
        hypothetical_notional_inr=10_000,
        hypothetical_pnl_inr=pnl_inr,
        hypothetical_pnl_pct=pnl_inr / 10_000,
        metadata_json={
            "assessment": {
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "confidence": 0.7,
                "reward_risk_ratio": reward_risk_ratio,
                "expected_risk": 2.0,
                "expected_reward": 6.0,
            }
        },
    )


def test_intraday_training_waits_for_real_shadow_samples(tmp_path: Path) -> None:
    service = IntradayModelTrainingService(
        artifact_path=tmp_path / "report.json",
        min_total_samples=3,
        min_samples_per_market=1,
    )

    with _session() as session:
        report = service.train_shadow_only(session)
        order_count = session.scalar(select(func.count()).select_from(Order))

    assert report["status"] == "WAITING_FOR_MARKET_DATA"
    assert report["shadow_only"] is True
    assert report["no_order_placement"] is True
    assert order_count == 0
    assert (tmp_path / "report.json").exists()


def test_intraday_training_default_uses_high_shadow_evidence_target(tmp_path: Path) -> None:
    service = IntradayModelTrainingService(
        artifact_path=tmp_path / "report.json",
        settings=Settings(_env_file=None),
    )

    with _session() as session:
        report = service.train_shadow_only(session)

    assert report["min_total_samples_required"] == 100_000
    assert report["min_samples_per_market_required"] == 25_000
    assert report["sample_goal"]["purpose"] == "long_run_shadow_evidence_gate"


def test_intraday_training_builds_stop_aware_shadow_report(tmp_path: Path) -> None:
    service = IntradayModelTrainingService(
        artifact_path=tmp_path / "report.json",
        min_total_samples=4,
        min_samples_per_market=2,
    )

    with _session() as session:
        session.add_all(
            [
                _observation(market=Market.INDIA, symbol="RELIANCE", pnl_inr=300, current_price=103),
                _observation(market=Market.INDIA, symbol="TCS", pnl_inr=-200, current_price=97),
                _observation(market=Market.US, symbol="SPY", pnl_inr=250, current_price=103),
                _observation(market=Market.US, symbol="QQQ", pnl_inr=-100, current_price=99),
            ]
        )
        report = service.train_shadow_only(session)

    assert report["status"] == "CALIBRATED_SHADOW_ONLY"
    assert report["trainable_samples"] == 4
    assert report["stop_loss_coverage"] == 1
    assert report["labels"]["POSITIVE"] == 2
    assert report["labels"]["NEGATIVE"] == 2
    assert report["markets"]["INDIA"]["trainable_samples"] == 2
    assert report["markets"]["US"]["trainable_samples"] == 2
    assert report["promotion_status"] == "LIVE_BLOCKED_BY_DESIGN"


def test_intraday_training_counts_timestamped_samples_over_open_observation(tmp_path: Path) -> None:
    service = IntradayModelTrainingService(
        artifact_path=tmp_path / "report.json",
        min_total_samples=2,
        min_samples_per_market=1,
    )

    with _session() as session:
        observation = _observation(market=Market.INDIA, symbol="RELIANCE", pnl_inr=10)
        session.add(observation)
        session.flush()
        session.add_all(
            [
                ShadowTrainingSample(
                    observation_id=observation.id,
                    strategy_name=observation.strategy_name,
                    market=Market.INDIA,
                    symbol="RELIANCE",
                    sample_at=utc_now(),
                    entry_price=100,
                    current_price=101,
                    hypothetical_quantity=100,
                    hypothetical_notional_inr=10_000,
                    hypothetical_pnl_inr=100,
                    hypothetical_pnl_pct=0.01,
                    metadata_json=observation.metadata_json,
                ),
                ShadowTrainingSample(
                    observation_id=observation.id,
                    strategy_name=observation.strategy_name,
                    market=Market.INDIA,
                    symbol="RELIANCE",
                    sample_at=utc_now(),
                    entry_price=100,
                    current_price=102,
                    hypothetical_quantity=100,
                    hypothetical_notional_inr=10_000,
                    hypothetical_pnl_inr=200,
                    hypothetical_pnl_pct=0.02,
                    metadata_json=observation.metadata_json,
                ),
            ]
        )
        report = service.train_shadow_only(session)

    assert report["total_samples"] == 2
    assert report["trainable_samples"] == 2
    assert report["markets"]["INDIA"]["trainable_samples"] == 2


def test_intraday_training_uses_real_signal_snapshots_as_samples(tmp_path: Path) -> None:
    service = IntradayModelTrainingService(
        artifact_path=tmp_path / "report.json",
        min_total_samples=2,
        min_samples_per_market=0,
    )
    created_at = utc_now()

    with _session() as session:
        instrument = Instrument(
            market=Market.INDIA,
            symbol="RELIANCE",
            name="RELIANCE",
            asset_class=AssetClass.EQUITY,
            currency="INR",
            exchange="NSE",
            is_active=True,
        )
        session.add(instrument)
        session.flush()
        for index, price in enumerate([100.0, 102.0]):
            signal = AgentSignal(
                instrument_id=instrument.id,
                market=Market.INDIA,
                symbol="RELIANCE",
                asset_class=AssetClass.EQUITY,
                action=TradeAction.BUY,
                confidence=0.7,
                strategy_name="shadow_training_observation_v1",
                created_at=created_at + timedelta(minutes=index),
                payload={
                    "last_price": price,
                    "assessment": {
                        "stop_loss": 98.0,
                        "take_profit": 106.0,
                        "confidence": 0.7,
                        "reward_risk_ratio": 3.0,
                        "expected_risk": 2.0,
                        "expected_reward": 6.0,
                    },
                },
                data_sources=["ZERODHA_KITE"],
            )
            session.add(signal)
        report = service.train_shadow_only(session)

    assert report["total_samples"] == 2
    assert report["trainable_samples"] == 2
    assert report["markets"]["INDIA"]["hypothetical_pnl_inr"] > 0
    assert report["outcome_summary"]["ideas"] == 1
    assert report["outcome_summary"]["counts"]["TIME_EXIT_POSITIVE"] == 1


def test_intraday_training_rejects_missing_stop_loss_metadata(tmp_path: Path) -> None:
    service = IntradayModelTrainingService(
        artifact_path=tmp_path / "report.json",
        min_total_samples=1,
        min_samples_per_market=0,
    )

    with _session() as session:
        session.add(
            _observation(
                market=Market.INDIA,
                symbol="RELIANCE",
                stop_loss=None,
                reward_risk_ratio=2.5,
            )
        )
        report = service.train_shadow_only(session)

    assert report["status"] == "INSUFFICIENT_DATA"
    assert report["trainable_samples"] == 0
    assert report["stop_loss_coverage"] == 0
    assert "Reject or repair observations missing stop-loss" in " ".join(report["next_actions"])
