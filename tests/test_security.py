from __future__ import annotations

from app.core.security import mask_sensitive_mapping


def test_secrets_are_masked_in_logs() -> None:
    masked = mask_sensitive_mapping(
        {
            "alpaca_secret_key": "supersecret",
            "nested": {"zerodha_access_token": "abcd1234"},
            "normal": "visible",
        }
    )

    assert masked["alpaca_secret_key"] == "su****et"
    assert masked["nested"]["zerodha_access_token"] == "ab****34"
    assert masked["normal"] == "visible"
