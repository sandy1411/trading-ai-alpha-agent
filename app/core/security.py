from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SENSITIVE_TOKENS = (
    "api_key",
    "secret",
    "token",
    "password",
    "authorization",
    "access",
    "refresh",
)


def is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return any(token in normalized for token in SENSITIVE_TOKENS)


def mask_secret(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if not text:
        return ""
    if len(text) <= 4:
        return "****"
    return f"{text[:2]}****{text[-2:]}"


def mask_sensitive_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    masked: dict[str, Any] = {}
    for key, value in values.items():
        if is_sensitive_key(key):
            masked[key] = mask_secret(value)
        elif isinstance(value, Mapping):
            masked[key] = mask_sensitive_mapping(value)
        else:
            masked[key] = value
    return masked
