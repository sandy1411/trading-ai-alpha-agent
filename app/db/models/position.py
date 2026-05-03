from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Enum as SAEnum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import AssetClass, Market
from app.db.base import Base, JSONBType, TimestampMixin


class Position(Base, TimestampMixin):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("market", "symbol", name="uq_positions_market_symbol"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("instruments.id"), nullable=True)
    market: Mapped[Market] = mapped_column(SAEnum(Market, name="position_market"))
    symbol: Mapped[str] = mapped_column(String(64), index=True)
    asset_class: Mapped[AssetClass] = mapped_column(SAEnum(AssetClass, name="position_asset_class"))
    quantity: Mapped[int] = mapped_column(default=0)
    average_price: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    market_value_inr: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    broker: Mapped[str] = mapped_column(String(64), default="")
    metadata_json: Mapped[dict] = mapped_column(JSONBType, default=dict)
