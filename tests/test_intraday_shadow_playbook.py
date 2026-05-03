from __future__ import annotations

from app.strategies.intraday_shadow import IntradayShadowPlaybook


def test_intraday_playbook_is_shadow_only_and_stop_first() -> None:
    summary = IntradayShadowPlaybook().dashboard_summary()

    assert summary["mode"] == "SHADOW_ONLY_INTRADAY_RESEARCH"
    assert summary["capital_posture"] == "PROTECT_CAPITAL_FIRST"
    assert summary["min_reward_risk_ratio"] >= 2.0
    assert any("Stop-loss must exist" in item for item in summary["intraday_guardrails"])
    assert any(
        profile["status"] == "DISABLED_HIGH_RISK"
        for profile in summary["profiles"]
    )


def test_intraday_playbook_does_not_claim_live_readiness() -> None:
    summary = IntradayShadowPlaybook().dashboard_summary()

    assert "orders" not in summary
    assert all("live" not in profile["status"].lower() for profile in summary["profiles"])
    assert summary["max_hypothesis_risk_per_trade_pct"] <= 0.0025
