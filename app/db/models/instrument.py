from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Boolean, Enum as SAEnum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import AssetClass, Market
from app.db.base import Base, TimestampMixin


class Instrument(Base, TimestampMixin):
    __tablename__ = "instruments"
    __table_args__ = (UniqueConstraint("market", "symbol", name="uq_instruments_market_symbol"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    market: Mapped[Market] = mapped_column(SAEnum(Market, name="market"), index=True)
    symbol: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    asset_class: Mapped[AssetClass] = mapped_column(SAEnum(AssetClass, name="asset_class"))
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    exchange: Mapped[str] = mapped_column(String(64), default="")
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
