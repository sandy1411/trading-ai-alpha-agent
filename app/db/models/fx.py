from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum as SAEnum, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import FreshnessStatus
from app.core.time_utils import utc_now
from app.db.base import Base, TimestampMixin


class FXRate(Base, TimestampMixin):
    __tablename__ = "fx_rates"
    __table_args__ = (
        UniqueConstraint("base_currency", "quote_currency", "source", "observed_at", name="uq_fx_quote"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    base_currency: Mapped[str] = mapped_column(String(8), default="USD")
    quote_currency: Mapped[str] = mapped_column(String(8), default="INR")
    rate: Mapped[float] = mapped_column(Numeric(18, 8))
    source: Mapped[str] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    freshness_status: Mapped[FreshnessStatus] = mapped_column(
        SAEnum(FreshnessStatus, name="freshness_status"), default=FreshnessStatus.MISSING
    )
