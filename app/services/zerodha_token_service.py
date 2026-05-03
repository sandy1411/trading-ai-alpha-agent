from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from dotenv import set_key

from app.core.config import Settings, get_settings
from app.core.errors import FailClosedError, MissingCredentialsError

RUNTIME_DIR = Path(".runtime")
REQUEST_TOKEN_FILE = RUNTIME_DIR / "zerodha_request_token.txt"
ACCESS_TOKEN_FILE = RUNTIME_DIR / "zerodha_access_token.txt"
ACCESS_TOKEN_META_FILE = RUNTIME_DIR / "zerodha_access_token_meta.json"


def build_login_url(settings: Settings | None = None) -> str:
    resolved = settings or get_settings()
    if not resolved.zerodha_api_key:
        raise MissingCredentialsError("ZERODHA_API_KEY is missing")
    query = urlencode({"v": "3", "api_key": resolved.zerodha_api_key})
    return f"https://kite.zerodha.com/connect/login?{query}"


def save_request_token(request_token: str) -> None:
    RUNTIME_DIR.mkdir(exist_ok=True)
    REQUEST_TOKEN_FILE.write_text(request_token.strip(), encoding="utf-8")


def load_request_token() -> str | None:
    if not REQUEST_TOKEN_FILE.exists():
        return None
    token = REQUEST_TOKEN_FILE.read_text(encoding="utf-8").strip()
    return token or None


def save_access_token(access_token: str, metadata: dict[str, Any] | None = None) -> None:
    RUNTIME_DIR.mkdir(exist_ok=True)
    ACCESS_TOKEN_FILE.write_text(access_token.strip(), encoding="utf-8")
    meta = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "zerodha_token_exchange",
        **(metadata or {}),
    }
    ACCESS_TOKEN_META_FILE.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def load_access_token() -> str | None:
    if ACCESS_TOKEN_FILE.exists():
        token = ACCESS_TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token
    settings = get_settings()
    return settings.zerodha_access_token or None


def access_token_metadata() -> dict[str, Any]:
    if not ACCESS_TOKEN_META_FILE.exists():
        return {}
    try:
        payload = json.loads(ACCESS_TOKEN_META_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"metadata_error": "unreadable_access_token_metadata"}
    return payload if isinstance(payload, dict) else {}


def zerodha_auth_status(settings: Settings | None = None) -> dict[str, Any]:
    resolved = settings or get_settings()
    token = load_access_token()
    request_token = load_request_token()
    metadata = access_token_metadata()
    return {
        "api_key_present": bool(resolved.zerodha_api_key),
        "api_secret_present": bool(resolved.zerodha_api_secret),
        "access_token_present": bool(token),
        "request_token_present": bool(request_token),
        "access_token_generated_at": metadata.get("generated_at"),
        "access_token_login_time": metadata.get("login_time"),
        "user_id_present": bool(metadata.get("user_id")),
        "auto_exchange_on_callback": resolved.zerodha_auto_exchange_on_callback,
        "manual_daily_login_required": True,
        "zero_intervention_possible": False,
        "automation_boundary": (
            "Kite requires a successful broker login to issue a request_token. "
            "This system can open the login flow and auto-exchange the callback token, "
            "but it must not bypass Zerodha authentication or 2FA."
        ),
    }


def exchange_request_token(
    request_token: str,
    settings: Settings | None = None,
    *,
    write_env: bool = True,
) -> dict[str, Any]:
    resolved = settings or get_settings()
    if not resolved.zerodha_api_key:
        raise MissingCredentialsError("ZERODHA_API_KEY is missing")
    if not resolved.zerodha_api_secret:
        raise MissingCredentialsError("ZERODHA_API_SECRET is missing")

    checksum = sha256(
        f"{resolved.zerodha_api_key}{request_token}{resolved.zerodha_api_secret}".encode("utf-8")
    ).hexdigest()
    response = httpx.post(
        "https://api.kite.trade/session/token",
        data={
            "api_key": resolved.zerodha_api_key,
            "request_token": request_token,
            "checksum": checksum,
        },
        timeout=15,
    )
    if response.status_code >= 400:
        raise FailClosedError(f"zerodha_token_exchange_failed:{response.status_code}")

    payload = response.json()
    data = payload.get("data", {})
    access_token = data.get("access_token")
    if not access_token:
        raise FailClosedError("zerodha_access_token_missing_in_response")

    save_access_token(
        access_token,
        {
            "user_id": data.get("user_id", ""),
            "login_time": data.get("login_time", ""),
        },
    )
    if write_env:
        env_path = Path(".env")
        if not env_path.exists():
            env_path.write_text(Path(".env.example").read_text(encoding="utf-8"), encoding="utf-8")
        set_key(str(env_path), "ZERODHA_ACCESS_TOKEN", access_token)
    get_settings.cache_clear()
    return {"user_id": data.get("user_id", ""), "login_time": data.get("login_time", "")}
