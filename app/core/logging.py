from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.core.security import mask_sensitive_mapping


def add_secret_masking(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    return mask_sensitive_mapping(event_dict)


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(stream=sys.stdout, level=level, format="%(message)s")
    structlog.configure(
        processors=[
            add_secret_masking,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
