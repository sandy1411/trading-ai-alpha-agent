from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.routes import alerts, dashboard, zerodha
from app.core.config import Settings
from app.core.enums import Market
from app.main import app
from app.services.email_service import EmailSummaryService
from app.services.performance_service import PerformanceService


def test_dashboard_html_loads() -> None:
    client = TestClient(app)

    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "Sandy-Trading-AI" in response.text
    assert "Daily Review" in response.text
    assert "Daily Shadow Review" in response.text
    assert "Market Comparison" in response.text
    assert "Everyday P&L History" in response.text
    assert "Shadow Ledger" in response.text
    assert "Shadow transactions only" in response.text
    assert "Risk & Safety" in response.text
    assert "Email Status" in response.text
    assert "Delivery mode" in response.text
    assert "Run Shadow Cycle" in response.text
    assert "Live Feed" in response.text
    assert "India / US Markets" in response.text
    assert "Training" in response.text
    assert "Intraday Model Training" in response.text
    assert "Stop-Loss Coverage" in response.text
    assert "Model Feature Diagnostics" in response.text
    assert "Strategy Lab" in response.text
    assert "Zerodha Daily Auth" in response.text
    assert "Open Zerodha Login" in response.text
    assert "US Shadow Book" in response.text
    assert "Algorithm Diagnostics" in response.text
    assert "Intraday Strategy Playbook" in response.text
    assert "Pause Dashboard" in response.text
    assert "/dashboard/ws" in response.text


def test_dashboard_data_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        dashboard.performance_service,
        "daily_summary",
        lambda: {
            "system": {
                "trading_mode": "SHADOW_LIVE_REAL_DATA",
                "live_trading_enabled": False,
                "kill_switch": True,
                "safety_errors": ["kill_switch_enabled"],
            },
            "portfolio": {
                "total_value_inr": 500000,
                "cash_inr": 500000,
                "daily_pnl_inr": 0,
                "total_drawdown_pct": 0,
            },
            "risk": {},
            "orders": {},
            "brokers": [],
            "providers": [],
        },
    )
    client = TestClient(app)

    response = client.get("/dashboard/data")

    assert response.status_code == 200
    assert response.json()["system"]["kill_switch"] is True


def test_zerodha_auth_status_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        zerodha,
        "zerodha_auth_status",
        lambda: {
            "api_key_present": True,
            "api_secret_present": True,
            "access_token_present": False,
            "manual_daily_login_required": True,
            "zero_intervention_possible": False,
        },
    )
    client = TestClient(app)

    response = client.get("/zerodha/auth/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["manual_daily_login_required"] is True
    assert payload["zero_intervention_possible"] is False


def test_daily_review_empty_market_stays_shadow_safe() -> None:
    review = PerformanceService._daily_market_review(
        market=Market.INDIA,
        review_date="2026-04-29",
        observations=[],
        signals=[],
        orders=[],
        risk_events=[],
    )

    assert review["status"] == "NO_DATA"
    assert review["real_orders"] == 0
    assert review["hypothetical_pnl_inr"] == 0
    assert "no shadow samples" in review["brief"].lower()


def test_dashboard_websocket_stream(monkeypatch) -> None:
    monkeypatch.setattr(
        dashboard.performance_service,
        "daily_summary",
        lambda: {
            "generated_at": "2026-04-29T00:00:00Z",
            "system": {
                "trading_mode": "SHADOW_LIVE_REAL_DATA",
                "live_trading_enabled": False,
                "kill_switch": True,
                "safety_errors": ["kill_switch_enabled"],
            },
            "portfolio": {
                "total_value_inr": 500000,
                "cash_inr": 500000,
                "daily_pnl_inr": 0,
                "total_drawdown_pct": 0,
            },
            "risk": {"decisions_today": 0, "risk_events_today": 0},
            "orders": {},
            "shadow": {
                "active_observations": 0,
                "hypothetical_notional_inr": 0,
                "hypothetical_pnl_inr": 0,
                "hypothetical_pnl_pct": 0,
                "winners": 0,
                "losers": 0,
                "recent_observations": [],
            },
            "bot_activity": {
                "current_action": "standing by",
                "studied_symbols_today": [],
                "improvement_actions": [],
            },
            "readiness": {
                "ready_for_india_shadow_now": True,
                "next_india_session_date": "2026-04-30",
                "checks": [],
            },
            "recent_orders": [],
            "recent_signals": [],
            "recent_risk_events": [],
            "recent_audit_logs": [],
            "email": {},
            "brokers": [],
            "providers": [],
        },
    )
    client = TestClient(app)

    with client.websocket_connect("/dashboard/ws") as websocket:
        payload = websocket.receive_json()

    assert payload["type"] == "snapshot"
    assert payload["stream_interval_seconds"] == dashboard.STREAM_INTERVAL_SECONDS
    assert payload["data"]["system"]["trading_mode"] == "SHADOW_LIVE_REAL_DATA"


def test_daily_summary_preview_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        alerts.email_summary_service,
        "build_daily_summary_text",
        lambda: "safe daily summary",
    )
    client = TestClient(app)

    response = client.get("/alerts/daily-summary")

    assert response.status_code == 200
    assert response.json()["summary"] == "safe daily summary"


def test_email_summary_can_use_local_smtp_without_auth(monkeypatch) -> None:
    calls = {"starttls": 0, "login": 0, "send": 0}

    class SMTPStub:
        def __init__(self, host, port) -> None:
            self.host = host
            self.port = port

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def starttls(self) -> None:
            calls["starttls"] += 1

        def login(self, username, password) -> None:
            calls["login"] += 1

        def send_message(self, message) -> None:
            calls["send"] += 1

    monkeypatch.setattr("app.services.email_service.smtplib.SMTP", SMTPStub)
    monkeypatch.setattr(
        "app.services.email_service.performance_service.daily_summary",
        lambda: {
            "app_name": "Sandy-Trading-AI",
            "generated_at": "2026-04-29T00:00:00Z",
            "portfolio": {"total_value_inr": 0, "cash_inr": 0, "daily_pnl_inr": 0, "total_drawdown_pct": 0},
            "system": {"trading_mode": "SHADOW_LIVE_REAL_DATA", "live_trading_enabled": False, "kill_switch": True, "safety_errors": []},
            "risk": {"decisions_today": 0, "risk_events_today": 0, "max_risk_per_trade_pct": 0.005},
            "shadow": {"hypothetical_notional_inr": 0, "hypothetical_pnl_inr": 0, "hypothetical_pnl_pct": 0, "winners": 0, "losers": 0, "flat": 0, "recent_observations": []},
            "bot_activity": {"live_trading_status": "DISABLED", "shadow_status": "RUNNING_OR_RECENT", "current_action": "idle", "studied_symbols_today": [], "improvement_actions": []},
            "readiness": {"next_india_session_date": "2026-04-30", "checks": []},
            "brokers": [],
            "providers": [],
        },
    )
    service = EmailSummaryService(
        Settings(
            _env_file=None,
            enable_email_summary=True,
            email_smtp_host="localhost",
            email_smtp_port=1025,
            email_smtp_use_tls=False,
            email_smtp_require_auth=False,
            email_to="recipient@example.com",
        )
    )

    result = service.send_daily_summary()

    assert result["sent"] is True
    assert calls == {"starttls": 0, "login": 0, "send": 1}
