from __future__ import annotations

from uuid import uuid4

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONBType, TimestampMixin


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor: Mapped[str] = mapped_column(String(128), default="system")
    action: Mapped[str] = mapped_column(String(128), index=True)
    entity_type: Mapped[str] = mapped_column(String(128), default="")
    entity_id: Mapped[str] = mapped_column(String(128), default="")
    message: Mapped[str] = mapped_column(String(1000), default="")
    before: Mapped[dict] = mapped_column(JSONBType, default=dict)
    after: Mapped[dict] = mapped_column(JSONBType, default=dict)
    context: Mapped[dict] = mapped_column(JSONBType, default=dict)
