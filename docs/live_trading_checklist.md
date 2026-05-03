# Live Trading Checklist

Before any micro-live or live-autonomous run:

- `.env` reviewed and real secrets kept local.
- `TRADING_MODE` intentionally set.
- `LIVE_TRADING_ENABLED=true`.
- `KILL_SWITCH=false`.
- Broker credentials verified.
- Broker account active and trading enabled.
- Positions reconciled.
- Provider health fresh.
- USD/INR FX fresh for US trades.
- Market calendar open.
- India compliance state approved where required.
- RiskEngine tests passing.
- Idempotency storage verified.
- Order reconciliation tested with real broker sandbox/paper where available.
- Emergency kill-switch command tested.

Do not proceed if any item is inconclusive.
