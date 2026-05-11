from __future__ import annotations

from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.enums import Market
from app.core.time_utils import utc_now
from app.db.base import Base
from app.db.models.news import NewsItem
from app.services.news_sentiment_service import NewsSentimentService


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_gold_negative_news_blocks_gold_sensitive_shadow_symbol_only() -> None:
    service = NewsSentimentService(
        Settings(_env_file=None, news_ingestion_enabled=False, news_staleness_minutes=120)
    )
    session_factory = _session_factory()

    with session_factory() as session:
        session.add(
            NewsItem(
                market=None,
                symbol=None,
                provider="TEST_NEWS",
                headline="Gold import duty shock hits jewellery demand",
                published_at=utc_now(),
                raw_payload={},
            )
        )
        session.commit()

        titan = service.assess(session, market=Market.INDIA, symbol="TITAN")
        reliance = service.assess(session, market=Market.INDIA, symbol="RELIANCE")

    assert titan.blocks_new_entries is True
    assert titan.reason == "negative_news_keyword_risk"
    assert reliance.blocks_new_entries is False


def test_negative_provider_sentiment_score_blocks_market_entries() -> None:
    service = NewsSentimentService(
        Settings(_env_file=None, news_ingestion_enabled=False, news_negative_score_threshold=-0.15)
    )
    session_factory = _session_factory()

    with session_factory() as session:
        session.add(
            NewsItem(
                market=Market.INDIA,
                symbol=None,
                provider="ALPHA_VANTAGE_NEWS",
                headline="India markets face broad risk-off sentiment",
                published_at=utc_now(),
                raw_payload={"overall_sentiment_score": "-0.42"},
            )
        )
        session.commit()

        risk = service.assess(session, market=Market.INDIA, symbol="RELIANCE")

    assert risk.blocks_new_entries is True
    assert risk.reason == "negative_news_sentiment_score:-0.420"
    assert risk.sentiment_score == -0.42


def test_overnight_negative_news_inside_risk_window_blocks_next_session() -> None:
    service = NewsSentimentService(
        Settings(
            _env_file=None,
            news_ingestion_enabled=False,
            news_staleness_minutes=60,
            news_sentiment_risk_window_hours=36,
        )
    )
    session_factory = _session_factory()

    with session_factory() as session:
        session.add(
            NewsItem(
                market=None,
                symbol=None,
                provider="TEST_NEWS",
                headline="Stop buying gold warning hits jewellery sentiment",
                published_at=utc_now() - timedelta(hours=18),
                raw_payload={},
            )
        )
        session.commit()

        risk = service.assess(session, market=Market.INDIA, symbol="TITAN")

    assert risk.blocks_new_entries is True
    assert risk.reason == "negative_news_keyword_risk"


def test_keyword_guard_does_not_match_substrings_like_bank_for_ban() -> None:
    service = NewsSentimentService(Settings(_env_file=None, news_ingestion_enabled=False))
    session_factory = _session_factory()

    with session_factory() as session:
        session.add(
            NewsItem(
                market=Market.US,
                symbol=None,
                provider="TEST_NEWS",
                headline="Bank earnings momentum improves after analyst upgrade",
                published_at=utc_now(),
                raw_payload={},
            )
        )
        session.commit()

        risk = service.assess(session, market=Market.US, symbol=None)

    assert risk.blocks_new_entries is False
    assert risk.reason == "no_blocking_news_sentiment_detected"


def test_missing_fresh_news_is_caution_not_a_buy_signal() -> None:
    service = NewsSentimentService(Settings(_env_file=None, news_ingestion_enabled=False))
    session_factory = _session_factory()

    with session_factory() as session:
        risk = service.assess(session, market=Market.INDIA, symbol="RELIANCE")

    assert risk.action == "CAUTION"
    assert risk.blocks_new_entries is False
    assert risk.reason == "fresh_news_sentiment_unavailable"
