from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum as SAEnum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import Market
from app.core.time_utils import utc_now
from app.db.base import Base, JSONBType, TimestampMixin


class NewsItem(Base, TimestampMixin):
    __tablename__ = "news"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    market: Mapped[Market | None] = mapped_column(SAEnum(Market, name="news_market"), nullable=True)
    symbol: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(128))
    headline: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(1000), default="")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    raw_payload: Mapped[dict] = mapped_column(JSONBType, default=dict)
