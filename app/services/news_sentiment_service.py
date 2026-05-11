from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import Market
from app.core.errors import TradingAlphaError
from app.data_providers.alpha_vantage import AlphaVantageProvider
from app.db.models.news import NewsItem
from app.db.models.risk import RiskEvent
from app.db.session import SessionLocal


@dataclass(frozen=True)
class NewsSentimentRisk:
    market: Market
    symbol: str | None
    action: str
    severity: str
    reason: str
    headline_count: int
    matched_headlines: list[str]
    sentiment_score: float | None = None
    provider: str | None = None
    shadow_only: bool = True
    no_order_placement: bool = True

    @property
    def blocks_new_entries(self) -> bool:
        return self.action == "BLOCK_NEW_ENTRIES"

    def model_dump(self) -> dict[str, Any]:
        data = asdict(self)
        data["market"] = self.market.value
        return data


class NewsSentimentService:
    """Deterministic news-risk reducer.

    News can block or slow new entries, but it can never create a BUY decision.
    """

    market_negative_keywords = {
        "crash",
        "selloff",
        "sell-off",
        "panic",
        "war",
        "attack",
        "conflict",
        "sanction",
        "inflation",
        "recession",
        "downgrade",
        "default",
        "rate hike",
        "currency crisis",
        "rupee falls",
        "oil shock",
        "tariff",
        "ban",
        "curb",
        "avoid buying",
        "stop buying",
        "do not buy",
        "unstable",
    }
    gold_risk_keywords = {
        "gold",
        "bullion",
        "jewellery",
        "jewelry",
        "import duty",
        "gold import",
        "stop buying gold",
    }
    gold_sensitive_symbols = {
        "TITAN",
        "KALYANKJIL",
        "SENCO",
        "TBZ",
        "THANGAMAYL",
        "RAJESHEXPO",
        "GOLD",
        "GOLDBEES",
    }

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def ingest_if_due(self, db: Session | None = None) -> dict[str, Any]:
        if not self.settings.news_ingestion_enabled:
            return {"status": "disabled", "inserted": 0}
        if not self.settings.alpha_vantage_api_key:
            return {"status": "missing_alpha_vantage_key", "inserted": 0}

        close_session = db is None
        session = db or SessionLocal()
        try:
            cutoff = datetime.now(UTC) - timedelta(seconds=self.settings.news_ingestion_min_interval_seconds)
            latest_alpha = session.scalar(
                select(NewsItem)
                .where(NewsItem.provider == "ALPHA_VANTAGE_NEWS")
                .order_by(NewsItem.created_at.desc())
                .limit(1)
            )
            if latest_alpha and latest_alpha.created_at >= cutoff:
                return {"status": "fresh_enough", "inserted": 0}

            provider = AlphaVantageProvider(self.settings)
            feed = provider.news_sentiment(
                topics=["financial_markets", "economy_macro", "economy_monetary"]
            )
            inserted = self._store_alpha_vantage_feed(session, feed)
            session.add(
                RiskEvent(
                    market=None,
                    event_type="news_sentiment_ingested",
                    severity="INFO",
                    message=f"Ingested {inserted} Alpha Vantage news sentiment rows.",
                    context={"provider": "ALPHA_VANTAGE_NEWS", "inserted": inserted},
                )
            )
            if close_session:
                session.commit()
            return {"status": "completed", "inserted": inserted}
        except TradingAlphaError as exc:
            session.add(
                RiskEvent(
                    market=None,
                    event_type="news_sentiment_ingestion_failed",
                    severity="WARN",
                    message=str(exc),
                    context={"provider": "ALPHA_VANTAGE_NEWS"},
                )
            )
            if close_session:
                session.commit()
            return {"status": "failed", "inserted": 0, "error": str(exc)}
        finally:
            if close_session:
                session.close()

    def assess(
        self,
        session: Session,
        *,
        market: Market,
        symbol: str | None = None,
    ) -> NewsSentimentRisk:
        if not self.settings.news_sentiment_guard_enabled:
            return self._clear(market, symbol, "news_sentiment_guard_disabled")

        cutoff = datetime.now(UTC) - timedelta(hours=self.settings.news_sentiment_risk_window_hours)
        query = (
            select(NewsItem)
            .where(NewsItem.published_at >= cutoff)
            .order_by(NewsItem.published_at.desc())
            .limit(100)
        )
        items = list(session.scalars(query).all())
        if not items:
            return NewsSentimentRisk(
                market=market,
                symbol=symbol,
                action="CAUTION",
                severity="WARN",
                reason="fresh_news_sentiment_unavailable",
                headline_count=0,
                matched_headlines=[],
            )

        score_risk = self._score_based_risk(market, symbol, items)
        if score_risk is not None:
            return score_risk

        keyword_risk = self._keyword_based_risk(market, symbol, items)
        if keyword_risk is not None:
            return keyword_risk

        return self._clear(market, symbol, "no_blocking_news_sentiment_detected", len(items))

    def _store_alpha_vantage_feed(self, session: Session, feed: list[dict[str, Any]]) -> int:
        inserted = 0
        for item in feed:
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            url = str(item.get("url") or "")
            if self._news_exists(session, title, url):
                continue
            ticker_sentiment = item.get("ticker_sentiment")
            symbol = None
            if isinstance(ticker_sentiment, list) and ticker_sentiment:
                first = ticker_sentiment[0]
                if isinstance(first, dict):
                    symbol = str(first.get("ticker") or "")[:64] or None
            session.add(
                NewsItem(
                    market=self._infer_market(symbol),
                    symbol=symbol,
                    provider="ALPHA_VANTAGE_NEWS",
                    headline=title[:500],
                    url=url[:1000],
                    published_at=AlphaVantageProvider.parse_news_time(item.get("time_published")),
                    raw_payload=item,
                )
            )
            inserted += 1
        return inserted

    @staticmethod
    def _news_exists(session: Session, headline: str, url: str) -> bool:
        return bool(
            session.scalar(
                select(func.count())
                .select_from(NewsItem)
                .where(NewsItem.headline == headline[:500], NewsItem.url == url[:1000])
            )
        )

    @staticmethod
    def _infer_market(symbol: str | None) -> Market | None:
        if not symbol:
            return None
        return Market.US if "." not in symbol else Market.INDIA

    def _score_based_risk(
        self,
        market: Market,
        symbol: str | None,
        items: list[NewsItem],
    ) -> NewsSentimentRisk | None:
        scored: list[tuple[NewsItem, float]] = []
        for item in items:
            score = self._sentiment_score(item)
            if score is None:
                continue
            if score <= self.settings.news_negative_score_threshold and self._headline_applies(
                item, market, symbol
            ):
                scored.append((item, score))
        if not scored:
            return None
        worst_item, worst_score = min(scored, key=lambda row: row[1])
        return NewsSentimentRisk(
            market=market,
            symbol=symbol,
            action="BLOCK_NEW_ENTRIES",
            severity="WARN",
            reason=f"negative_news_sentiment_score:{worst_score:.3f}",
            headline_count=len(items),
            matched_headlines=[item.headline for item, _score in scored[:5]],
            sentiment_score=worst_score,
            provider=worst_item.provider,
        )

    def _keyword_based_risk(
        self,
        market: Market,
        symbol: str | None,
        items: list[NewsItem],
    ) -> NewsSentimentRisk | None:
        symbol_upper = (symbol or "").upper()
        matches: list[str] = []
        for item in items:
            headline = item.headline.lower()
            market_hit = any(keyword in headline for keyword in self.market_negative_keywords)
            gold_hit = any(keyword in headline for keyword in self.gold_risk_keywords)
            symbol_hit = bool(symbol_upper and symbol_upper.lower() in headline)
            applies_to_gold_symbol = gold_hit and symbol_upper in self.gold_sensitive_symbols
            applies_market_wide = market_hit and self._headline_applies(item, market, symbol)
            if applies_market_wide or symbol_hit or applies_to_gold_symbol:
                matches.append(item.headline)
        if not matches:
            return None
        return NewsSentimentRisk(
            market=market,
            symbol=symbol,
            action="BLOCK_NEW_ENTRIES",
            severity="WARN",
            reason="negative_news_keyword_risk",
            headline_count=len(items),
            matched_headlines=matches[:5],
        )

    @staticmethod
    def _headline_applies(item: NewsItem, market: Market, symbol: str | None) -> bool:
        if item.symbol and symbol:
            return item.symbol.upper() == symbol.upper()
        if item.market is not None:
            return item.market == market
        return True

    @staticmethod
    def _sentiment_score(item: NewsItem) -> float | None:
        payload = item.raw_payload or {}
        raw_score = payload.get("overall_sentiment_score")
        try:
            return float(raw_score)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _clear(
        market: Market,
        symbol: str | None,
        reason: str,
        headline_count: int = 0,
    ) -> NewsSentimentRisk:
        return NewsSentimentRisk(
            market=market,
            symbol=symbol,
            action="ALLOW",
            severity="INFO",
            reason=reason,
            headline_count=headline_count,
            matched_headlines=[],
        )


news_sentiment_service = NewsSentimentService()
