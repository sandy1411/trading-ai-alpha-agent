from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time_utils import utc_now
from app.db.base import Base, JSONBType, TimestampMixin


class PortfolioSnapshot(Base, TimestampMixin):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    base_currency: Mapped[str] = mapped_column(String(8), default="INR")
    total_value_inr: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    cash_inr: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    equity_exposure_inr: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    india_exposure_inr: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    us_exposure_inr: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    daily_pnl_inr: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    weekly_pnl_inr: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    monthly_drawdown_pct: Mapped[float] = mapped_column(Numeric(8, 6), default=0)
    total_drawdown_pct: Mapped[float] = mapped_column(Numeric(8, 6), default=0)
    positions: Mapped[list] = mapped_column(JSONBType, default=list)
    exposures: Mapped[dict] = mapped_column(JSONBType, default=dict)
