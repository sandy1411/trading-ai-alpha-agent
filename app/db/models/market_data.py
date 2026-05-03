from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum as SAEnum, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import Market
from app.core.time_utils import utc_now
from app.db.base import Base, JSONBType, TimestampMixin


class MarketDataBar(Base, TimestampMixin):
    __tablename__ = "market_data_bars"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    market: Mapped[Market] = mapped_column(SAEnum(Market, name="market_data_market"))
    symbol: Mapped[str] = mapped_column(String(64), index=True)
    interval: Mapped[str] = mapped_column(String(32), default="1d")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    open: Mapped[float] = mapped_column(Numeric(18, 4))
    high: Mapped[float] = mapped_column(Numeric(18, 4))
    low: Mapped[float] = mapped_column(Numeric(18, 4))
    close: Mapped[float] = mapped_column(Numeric(18, 4))
    volume: Mapped[float] = mapped_column(Numeric(24, 4), default=0)
    source: Mapped[str] = mapped_column(String(128))
    metadata_json: Mapped[dict] = mapped_column(JSONBType, default=dict)
