from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.core.security import mask_sensitive_mapping

logger = get_logger(__name__)


class AuditService:
    def record(
        self,
        action: str,
        actor: str = "system",
        entity_type: str = "",
        entity_id: str = "",
        message: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        logger.info(
            "audit_event",
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            message=message,
            context=mask_sensitive_mapping(context or {}),
        )
