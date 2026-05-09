from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, Enum as SAEnum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import Market
from app.core.time_utils import utc_now
from app.db.base import Base, JSONBType, TimestampMixin


class ShadowObservation(Base, TimestampMixin):
    __tablename__ = "shadow_observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    strategy_name: Mapped[str] = mapped_column(String(128), index=True)
    market: Mapped[Market] = mapped_column(SAEnum(Market, name="shadow_observation_market"))
    symbol: Mapped[str] = mapped_column(String(64), index=True)
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("instruments.id"), nullable=True)
    signal_id: Mapped[str | None] = mapped_column(ForeignKey("agent_signals.id"), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    last_marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    entry_price: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    current_price: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    hypothetical_quantity: Mapped[int] = mapped_column(default=0)
    hypothetical_notional_inr: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    hypothetical_pnl_inr: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    hypothetical_pnl_pct: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    status: Mapped[str] = mapped_column(String(64), default="OPEN_OBSERVATION", index=True)
    notes: Mapped[list] = mapped_column(JSONBType, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSONBType, default=dict)


class ShadowTrainingSample(Base, TimestampMixin):
    __tablename__ = "shadow_training_samples"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    observation_id: Mapped[str | None] = mapped_column(
        ForeignKey("shadow_observations.id"), nullable=True, index=True
    )
    strategy_name: Mapped[str] = mapped_column(String(128), index=True)
    market: Mapped[Market] = mapped_column(SAEnum(Market, name="shadow_training_sample_market"))
    symbol: Mapped[str] = mapped_column(String(64), index=True)
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("instruments.id"), nullable=True)
    signal_id: Mapped[str | None] = mapped_column(ForeignKey("agent_signals.id"), nullable=True)
    sample_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    entry_price: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    current_price: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    hypothetical_quantity: Mapped[int] = mapped_column(default=0)
    hypothetical_notional_inr: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    hypothetical_pnl_inr: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    hypothetical_pnl_pct: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    sample_kind: Mapped[str] = mapped_column(String(64), default="INTRADAY_MARK")
    metadata_json: Mapped[dict] = mapped_column(JSONBType, default=dict)


class DailyMarketReviewSnapshot(Base, TimestampMixin):
    __tablename__ = "daily_market_review_snapshots"
    __table_args__ = (
        UniqueConstraint("market", "review_date", name="uq_daily_market_review_market_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    market: Mapped[Market] = mapped_column(SAEnum(Market, name="daily_review_market"), index=True)
    review_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(64), default="NO_DATA")
    signals: Mapped[int] = mapped_column(default=0)
    shadow_hypotheses: Mapped[int] = mapped_column(default=0)
    real_orders: Mapped[int] = mapped_column(default=0)
    buy_hypotheses: Mapped[int] = mapped_column(default=0)
    no_trade_signals: Mapped[int] = mapped_column(default=0)
    winners: Mapped[int] = mapped_column(default=0)
    losers: Mapped[int] = mapped_column(default=0)
    flat: Mapped[int] = mapped_column(default=0)
    hypothetical_notional_inr: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    hypothetical_pnl_inr: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    hypothetical_pnl_pct: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    payload: Mapped[dict] = mapped_column(JSONBType, default=dict)
