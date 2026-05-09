from __future__ import annotations

from secrets import compare_digest
from typing import Annotated

from fastapi import Header, HTTPException, status

from app.core.config import get_settings

CONTROL_TOKEN_HEADER = "X-Sandy-Control-Token"


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def require_control_auth(
    control_token: Annotated[str | None, Header(alias=CONTROL_TOKEN_HEADER)] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> None:
    settings = get_settings()
    if not settings.api_control_auth_enabled:
        return

    expected_token = settings.api_control_token.strip()
    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="api_control_auth_enabled_but_token_missing",
        )

    supplied_token = (control_token or _bearer_token(authorization) or "").strip()
    if not supplied_token or not compare_digest(supplied_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="api_control_auth_required",
            headers={"WWW-Authenticate": "Bearer"},
        )
