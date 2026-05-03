from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Enum as SAEnum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import AssetClass, Market, TradeAction
from app.db.base import Base, JSONBType, TimestampMixin


class AgentSignal(Base, TimestampMixin):
    __tablename__ = "agent_signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    strategy_id: Mapped[str | None] = mapped_column(ForeignKey("strategies.id"), nullable=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"))
    market: Mapped[Market] = mapped_column(SAEnum(Market, name="signal_market"))
    symbol: Mapped[str] = mapped_column(String(64), index=True)
    asset_class: Mapped[AssetClass] = mapped_column(SAEnum(AssetClass, name="signal_asset_class"))
    action: Mapped[TradeAction] = mapped_column(SAEnum(TradeAction, name="trade_action"))
    confidence: Mapped[float] = mapped_column(Numeric(6, 5))
    strategy_name: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSONBType, default=dict)
    data_sources: Mapped[list] = mapped_column(JSONBType, default=list)
