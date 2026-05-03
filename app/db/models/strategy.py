from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONBType, TimestampMixin


class Strategy(Base, TimestampMixin):
    __tablename__ = "strategies"
    __table_args__ = (UniqueConstraint("name", name="uq_strategies_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(String(1000), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    allocation_limits: Mapped[dict] = mapped_column(JSONBType, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSONBType, default=dict)
