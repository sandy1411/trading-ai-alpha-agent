from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time_utils import utc_now
from app.db.base import Base, JSONBType, TimestampMixin


class MacroObservation(Base, TimestampMixin):
    __tablename__ = "macro_observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    indicator: Mapped[str] = mapped_column(String(128), index=True)
    country: Mapped[str] = mapped_column(String(64), default="")
    value: Mapped[float] = mapped_column(Numeric(18, 6))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    source: Mapped[str] = mapped_column(String(128))
    metadata_json: Mapped[dict] = mapped_column(JSONBType, default=dict)
