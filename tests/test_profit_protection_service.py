from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.enums import Market
from app.db.base import Base
from app.db.models.shadow import ShadowTrainingSample
from app.services.profit_protection_service import ProfitProtectionService


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def _sample(
    *,
    symbol: str,
    sample_at: datetime,
    pnl: float,
    current_price: float = 100,
    stop_loss: float = 98,
    take_profit: float = 108,
) -> ShadowTrainingSample:
    return ShadowTrainingSample(
        strategy_name="shadow_training_observation_v1",
        market=Market.INDIA,
        symbol=symbol,
        sample_at=sample_at,
        entry_price=100,
        current_price=current_price,
        hypothetical_quantity=100,
        hypothetical_notional_inr=50_000,
        hypothetical_pnl_inr=pnl,
        hypothetical_pnl_pct=pnl / 50_000,
        sample_kind="INTRADAY_MARK",
        metadata_json={"assessment": {"stop_loss": stop_loss, "take_profit": take_profit}},
    )


def test_profit_protection_flags_large_giveback_from_peak() -> None:
    now = datetime.now(UTC)
    service = ProfitProtectionService(
        Settings(
            _env_file=None,
            intraday_profit_giveback_exit_pct=0.35,
            intraday_min_profit_lock_inr=500,
        )
    )

    decisions = service.analyze_samples(
        [
            _sample(symbol="RELIANCE", sample_at=now, pnl=0),
            _sample(symbol="RELIANCE", sample_at=now + timedelta(minutes=1), pnl=6000),
            _sample(symbol="RELIANCE", sample_at=now + timedelta(minutes=2), pnl=1000),
        ]
    )

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.peak_pnl_inr == 6000
    assert decision.current_pnl_inr == 1000
    assert decision.giveback_inr == 5000
    assert decision.recommended_shadow_exit == "EXIT_PROFIT_GIVEBACK"
    assert decision.no_order_placement is True


def test_profit_protection_summary_totals_current_peak_and_giveback() -> None:
    now = datetime.now(UTC)
    service = ProfitProtectionService(Settings(_env_file=None, intraday_min_profit_lock_inr=500))

    with _session() as session:
        session.add_all(
            [
                _sample(symbol="RELIANCE", sample_at=now, pnl=0),
                _sample(symbol="RELIANCE", sample_at=now + timedelta(minutes=1), pnl=6000),
                _sample(symbol="RELIANCE", sample_at=now + timedelta(minutes=2), pnl=1000),
                _sample(symbol="TCS", sample_at=now + timedelta(minutes=2), pnl=500),
            ]
        )
        summary = service.summary(session)

    assert summary["mode"] == "SHADOW_ONLY_PROFIT_PROTECTION"
    assert summary["best_observed_total_pnl_inr"] == 6500
    assert summary["current_total_pnl_inr"] == 1500
    assert summary["giveback_from_best_observed_inr"] == 5000
    assert summary["safety"]["no_order_placement"] is True


def test_profit_protection_separates_profit_booking_and_stop_loss_booking() -> None:
    now = datetime.now(UTC)
    service = ProfitProtectionService(Settings(_env_file=None, intraday_min_profit_lock_inr=500))

    with _session() as session:
        session.add_all(
            [
                _sample(
                    symbol="RELIANCE",
                    sample_at=now,
                    pnl=900,
                    current_price=109,
                    take_profit=108,
                ),
                _sample(
                    symbol="TCS",
                    sample_at=now,
                    pnl=-400,
                    current_price=97,
                    stop_loss=98,
                ),
            ]
        )
        summary = service.summary(session)

    booking = summary["shadow_profit_booking"]
    assert booking["mode"] == "SHADOW_BOOKING_NOT_REAL_ORDER_EXECUTION"
    assert booking["booked_profit_count"] == 1
    assert booking["booked_profit_pnl_inr"] == 900
    assert booking["booked_profit_rows"][0]["symbol"] == "RELIANCE"
    assert booking["booked_loss_count"] == 1
    assert booking["booked_loss_pnl_inr"] == -400
    assert booking["booked_loss_rows"][0]["symbol"] == "TCS"
    assert booking["no_order_placement"] is True


def test_profit_protection_books_meaningful_profit_before_full_target() -> None:
    now = datetime.now(UTC)
    service = ProfitProtectionService(
        Settings(
            _env_file=None,
            intraday_profit_booking_enabled=True,
            intraday_profit_booking_target_progress_pct=0.50,
            intraday_profit_booking_min_pnl_inr=300,
        )
    )

    decisions = service.analyze_samples(
        [
            _sample(
                symbol="RELIANCE",
                sample_at=now,
                pnl=0,
                current_price=100,
                take_profit=108,
            ),
            _sample(
                symbol="RELIANCE",
                sample_at=now + timedelta(minutes=1),
                pnl=450,
                current_price=104.5,
                take_profit=108,
            ),
        ]
    )

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.recommended_shadow_exit == "EXIT_PROFIT_BOOKING"
    assert decision.label == "Book profit"
    assert decision.target_progress >= 0.50
    assert decision.no_order_placement is True
