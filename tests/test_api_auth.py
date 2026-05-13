from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import auth
from app.api.routes import alerts, shadow
from app.core.config import Settings
from app.main import app


def test_control_auth_is_off_by_default_for_local_sensitive_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        alerts.email_summary_service,
        "send_daily_summary",
        lambda: {"sent": True, "mode": "test"},
    )
    monkeypatch.setattr(auth, "get_settings", lambda: Settings(_env_file=None))
    client = TestClient(app)

    response = client.post("/alerts/daily-summary/email")

    assert response.status_code == 200
    assert response.json()["sent"] is True


def test_control_auth_blocks_sensitive_endpoint_without_token(monkeypatch) -> None:
    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            api_control_auth_enabled=True,
            api_control_token="local-test-token",
        ),
    )
    client = TestClient(app)

    response = client.post("/shadow/run-cycle")

    assert response.status_code == 401
    assert response.json()["detail"] == "api_control_auth_required"


def test_control_auth_fails_closed_when_enabled_without_configured_token(monkeypatch) -> None:
    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: Settings(_env_file=None, api_control_auth_enabled=True, api_control_token=""),
    )
    client = TestClient(app)

    response = client.post("/shadow/run-cycle")

    assert response.status_code == 503
    assert response.json()["detail"] == "api_control_auth_enabled_but_token_missing"


def test_control_auth_allows_sensitive_endpoint_with_header_token(monkeypatch) -> None:
    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            api_control_auth_enabled=True,
            api_control_token="local-test-token",
        ),
    )
    monkeypatch.setattr(shadow.shadow_training_service, "run_cycle", lambda: {"orders_placed": 0})
    client = TestClient(app)

    response = client.post(
        "/shadow/run-cycle",
        headers={auth.CONTROL_TOKEN_HEADER: "local-test-token"},
    )

    assert response.status_code == 200
    assert response.json()["orders_placed"] == 0


def test_professional_shadow_run_endpoint_is_shadow_only(monkeypatch) -> None:
    monkeypatch.setattr(
        shadow.professional_intraday_shadow_service,
        "run_india_once",
        lambda symbols=None: {
            "symbols_requested": symbols,
            "shadow_only": True,
            "orders_placed": 0,
        },
    )
    client = TestClient(app)

    response = client.post("/shadow/professional/run-india-once", json={"symbols": ["RELIANCE"]})

    assert response.status_code == 200
    assert response.json() == {
        "symbols_requested": ["RELIANCE"],
        "shadow_only": True,
        "orders_placed": 0,
    }


def test_control_auth_allows_sensitive_endpoint_with_bearer_token(monkeypatch) -> None:
    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            api_control_auth_enabled=True,
            api_control_token="local-test-token",
        ),
    )
    monkeypatch.setattr(
        alerts.email_summary_service,
        "send_daily_summary",
        lambda: {"sent": True, "mode": "test"},
    )
    client = TestClient(app)

    response = client.post(
        "/alerts/daily-summary/email",
        headers={"Authorization": "Bearer local-test-token"},
    )

    assert response.status_code == 200
    assert response.json()["sent"] is True


def test_read_only_endpoints_remain_open_when_control_auth_enabled(monkeypatch) -> None:
    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            api_control_auth_enabled=True,
            api_control_token="local-test-token",
        ),
    )
    monkeypatch.setattr(
        alerts.email_summary_service,
        "build_daily_summary_text",
        lambda: "preview only",
    )
    client = TestClient(app)

    assert client.get("/health").status_code == 200
    preview = client.get("/alerts/daily-summary")
    assert preview.status_code == 200
    assert preview.json()["summary"] == "preview only"
