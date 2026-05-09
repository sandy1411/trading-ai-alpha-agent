from __future__ import annotations

from app.core.config import Settings
from app.core.enums import Market
from app.db.models.shadow import ShadowObservation
from app.services.shadow_exit_service import ShadowExitService


def _observation(
    *,
    entry_price: float = 100.0,
    current_price: float = 104.0,
    stop_loss: float = 98.0,
    take_profit: float = 106.0,
    quantity: int = 100,
) -> ShadowObservation:
    return ShadowObservation(
        strategy_name="shadow_training_observation_v1",
        market=Market.INDIA,
        symbol="RELIANCE",
        entry_price=entry_price,
        current_price=current_price,
        hypothetical_quantity=quantity,
        hypothetical_notional_inr=10_000,
        hypothetical_pnl_inr=(current_price - entry_price) * quantity,
        hypothetical_pnl_pct=(current_price - entry_price) * quantity / 10_000,
        metadata_json={
            "assessment": {
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "reward_risk_ratio": 3.0,
            }
        },
    )


def test_shadow_exit_service_take_profit_is_shadow_only() -> None:
    service = ShadowExitService(Settings(_env_file=None))

    decision = service.evaluate_observation(_observation(current_price=106.5))

    assert decision.action == "EXIT_TAKE_PROFIT"
    assert decision.no_order_placement is True
    assert "wait for a fresh" in decision.reentry_plan.lower()


def test_shadow_exit_service_stop_loss_blocks_averaging_down() -> None:
    service = ShadowExitService(Settings(_env_file=None))

    decision = service.evaluate_observation(_observation(current_price=97.5))

    assert decision.action == "EXIT_STOP_LOSS"
    assert decision.urgency == "HIGH"
    assert "do not average down" in decision.reentry_plan.lower()


def test_shadow_exit_service_books_profit_before_target() -> None:
    service = ShadowExitService(
        Settings(
            _env_file=None,
            intraday_profit_booking_enabled=True,
            intraday_profit_booking_target_progress_pct=0.50,
            intraday_profit_booking_min_pnl_inr=300,
        )
    )

    decision = service.evaluate_observation(_observation(current_price=104.5))

    assert decision.action == "EXIT_PROFIT_BOOKING"
    assert decision.urgency == "HIGH"
    assert decision.shadow_only is True
    assert decision.no_order_placement is True
    assert "book" in decision.label.lower()


def test_shadow_exit_service_profit_lock_before_target_when_booking_disabled() -> None:
    service = ShadowExitService(
        Settings(
            _env_file=None,
            intraday_exit_profit_lock_pct=0.70,
            intraday_profit_booking_enabled=False,
        )
    )

    decision = service.evaluate_observation(_observation(current_price=104.5))

    assert decision.action == "LOCK_PROFIT_OR_TRAIL"
    assert decision.shadow_only is True
