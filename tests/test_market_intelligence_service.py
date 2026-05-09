from __future__ import annotations

from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.enums import Market
from app.core.time_utils import utc_now
from app.db.base import Base
from app.db.models.order import Order
from app.db.models.shadow import ShadowTrainingSample
from app.services.market_intelligence_service import MarketIntelligenceService


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def _profit_protection_stub() -> dict:
    return {
        "alerts_count": 0,
        "high_urgency_count": 0,
        "giveback_from_best_observed_inr": 0,
        "shadow_profit_booking": {
            "booked_profit_count": 0,
            "booked_loss_count": 0,
        },
    }


def test_market_intelligence_agents_are_shadow_only_and_do_not_order() -> None:
    service = MarketIntelligenceService(Settings(_env_file=None))

    with _session() as session:
        summary = service.summary(
            session,
            brokers=[],
            providers=[],
            readiness={
                "ready_for_india_shadow_now": False,
                "ready_for_us_shadow_now": False,
                "checks": [],
            },
            profit_protection=_profit_protection_stub(),
            include_external_health=False,
        )

    news_agent = next(
        agent for agent in summary["agents"] if agent["agent_name"] == "NewsSentimentAgent"
    )

    assert summary["mode"] == "SHADOW_ONLY_MARKET_INTELLIGENCE"
    assert summary["shadow_only"] is True
    assert summary["no_order_placement"] is True
    assert summary["orders_placed"] == 0
    assert all(agent["orders_placed"] == 0 for agent in summary["agents"])
    assert all(agent["no_order_placement"] is True for agent in summary["agents"])
    assert news_agent["status"] == "UNAVAILABLE"
    assert news_agent["metrics"]["sentiment_used_for_buy"] is False
    assert "fresh_news_sentiment_unavailable" in news_agent["risks"]


def test_market_intelligence_reads_real_shadow_samples_without_creating_orders() -> None:
    service = MarketIntelligenceService(
        Settings(
            _env_file=None,
            shadow_hypothesis_notional_inr=10_000,
            intraday_min_total_samples=2,
        )
    )

    with _session() as session:
        session.add_all(
            [
                ShadowTrainingSample(
                    strategy_name="shadow_training_observation_v1",
                    market=Market.INDIA,
                    symbol="RELIANCE",
                    sample_at=utc_now(),
                    entry_price=100,
                    current_price=103,
                    hypothetical_quantity=100,
                    hypothetical_notional_inr=10_000,
                    hypothetical_pnl_inr=300,
                    hypothetical_pnl_pct=0.03,
                    metadata_json={
                        "assessment": {
                            "stop_loss": 98,
                            "take_profit": 106,
                            "reward_risk_ratio": 3,
                        }
                    },
                ),
                ShadowTrainingSample(
                    strategy_name="shadow_training_observation_v1",
                    market=Market.US,
                    symbol="SPY",
                    sample_at=utc_now(),
                    entry_price=100,
                    current_price=99,
                    hypothetical_quantity=1,
                    hypothetical_notional_inr=8_300,
                    hypothetical_pnl_inr=-83,
                    hypothetical_pnl_pct=-0.01,
                    metadata_json={
                        "assessment": {
                            "stop_loss": 98,
                            "take_profit": 106,
                            "reward_risk_ratio": 3,
                        }
                    },
                ),
            ]
        )
        summary = service.summary(
            session,
            brokers=[],
            providers=[],
            readiness={
                "ready_for_india_shadow_now": True,
                "ready_for_us_shadow_now": True,
                "checks": [],
            },
            profit_protection=_profit_protection_stub(),
            include_external_health=False,
        )
        order_count = session.query(Order).count()

    price_agent = next(
        agent for agent in summary["agents"] if agent["agent_name"] == "PriceActionAgent"
    )
    learning_agent = next(
        agent for agent in summary["agents"] if agent["agent_name"] == "LearningVelocityAgent"
    )

    assert price_agent["metrics"]["total_samples"] == 2
    assert price_agent["metrics"]["markets"]["INDIA"]["winners"] == 1
    assert price_agent["metrics"]["markets"]["US"]["losers"] == 1
    assert learning_agent["metrics"]["latest_window_trainable"] == 2
    assert order_count == 0


def test_market_intelligence_pnl_uses_latest_mark_per_shadow_idea() -> None:
    service = MarketIntelligenceService(Settings(_env_file=None))
    now = utc_now()

    with _session() as session:
        session.add_all(
            [
                ShadowTrainingSample(
                    observation_id="idea-1",
                    strategy_name="shadow_training_observation_v1",
                    market=Market.INDIA,
                    symbol="RELIANCE",
                    sample_at=now,
                    entry_price=100,
                    current_price=101,
                    hypothetical_quantity=100,
                    hypothetical_notional_inr=10_000,
                    hypothetical_pnl_inr=100,
                    hypothetical_pnl_pct=0.01,
                    metadata_json={"assessment": {"stop_loss": 98, "reward_risk_ratio": 2}},
                ),
                ShadowTrainingSample(
                    observation_id="idea-1",
                    strategy_name="shadow_training_observation_v1",
                    market=Market.INDIA,
                    symbol="RELIANCE",
                    sample_at=now + timedelta(seconds=1),
                    entry_price=100,
                    current_price=103,
                    hypothetical_quantity=100,
                    hypothetical_notional_inr=10_000,
                    hypothetical_pnl_inr=300,
                    hypothetical_pnl_pct=0.03,
                    metadata_json={"assessment": {"stop_loss": 98, "reward_risk_ratio": 2}},
                ),
                ShadowTrainingSample(
                    observation_id="idea-2",
                    strategy_name="shadow_training_observation_v1",
                    market=Market.INDIA,
                    symbol="TCS",
                    sample_at=now,
                    entry_price=100,
                    current_price=99,
                    hypothetical_quantity=100,
                    hypothetical_notional_inr=10_000,
                    hypothetical_pnl_inr=-100,
                    hypothetical_pnl_pct=-0.01,
                    metadata_json={"assessment": {"stop_loss": 98, "reward_risk_ratio": 2}},
                ),
            ]
        )
        summary = service.summary(
            session,
            brokers=[],
            providers=[],
            readiness={
                "ready_for_india_shadow_now": True,
                "ready_for_us_shadow_now": False,
                "checks": [],
            },
            profit_protection=_profit_protection_stub(),
            include_external_health=False,
        )

    price_agent = next(
        agent for agent in summary["agents"] if agent["agent_name"] == "PriceActionAgent"
    )

    assert price_agent["metrics"]["total_samples"] == 3
    assert price_agent["metrics"]["unique_shadow_ideas"] == 2
    assert price_agent["metrics"]["latest_mark_hypothetical_pnl_inr"] == 200
    assert price_agent["metrics"]["markets"]["INDIA"]["unique_shadow_ideas"] == 2
    assert price_agent["metrics"]["markets"]["INDIA"]["winners"] == 1
    assert price_agent["metrics"]["markets"]["INDIA"]["losers"] == 1
