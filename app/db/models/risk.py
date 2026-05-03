from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Enum as SAEnum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import Market, RiskDecisionType
from app.db.base import Base, JSONBType, TimestampMixin


class RiskDecisionModel(Base, TimestampMixin):
    __tablename__ = "risk_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    signal_id: Mapped[str | None] = mapped_column(ForeignKey("agent_signals.id"), nullable=True)
    decision: Mapped[RiskDecisionType] = mapped_column(
        SAEnum(RiskDecisionType, name="risk_decision_type"), index=True
    )
    approved_quantity: Mapped[int] = mapped_column(default=0)
    approved_capital: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    approved_risk: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    rejection_reasons: Mapped[list] = mapped_column(JSONBType, default=list)
    required_actions: Mapped[list] = mapped_column(JSONBType, default=list)
    risk_metrics: Mapped[dict] = mapped_column(JSONBType, default=dict)


class RiskEvent(Base, TimestampMixin):
    __tablename__ = "risk_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    market: Mapped[Market | None] = mapped_column(SAEnum(Market, name="risk_event_market"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    severity: Mapped[str] = mapped_column(String(32), default="INFO")
    message: Mapped[str] = mapped_column(String(1000))
    context: Mapped[dict] = mapped_column(JSONBType, default=dict)


class RiskConfigRecord(Base, TimestampMixin):
    __tablename__ = "risk_config"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(128), unique=True)
    config: Mapped[dict] = mapped_column(JSONBType, default=dict)
