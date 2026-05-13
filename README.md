# Sandy-Trading-AI

Sandy-Trading-AI is a safety-first foundation for an autonomous trading platform covering India and US markets. It is built for personal research and shadow-live validation first, with real provider and broker integration points guarded by deterministic risk controls.

It does not guarantee profit, returns, signal quality, or loss avoidance. Trading involves risk, autonomous systems can lose money, and cash/no-trade is always a valid outcome.

## Safety Philosophy

The platform starts fail-closed:

- `TRADING_MODE=SHADOW_LIVE`
- `LIVE_TRADING_ENABLED=false`
- `LIVE_ORDERS_ENABLED=false`
- `KILL_SWITCH=true`

LLM components may later generate analysis, signals, summaries, and hypotheses, but they must never place orders. Execution follows this path only:

`Signal -> deterministic RiskEngine -> RiskDecision -> OrderIntent -> ExecutionAgent -> BrokerAdapter`

## Architecture Overview

- `app/core`: config, enums, structured logging, errors, time, secret masking.
- `app/db`: SQLAlchemy models for instruments, FX, signals, risk decisions, orders, positions, portfolio snapshots, audit logs, health, system state, and compliance.
- `app/schemas`: strict Pydantic contracts used across risk, execution, brokers, providers, and API.
- `app/brokers`: real Zerodha Kite and Alpaca adapter skeletons. Missing credentials fail closed.
- `app/data_providers`: real data/news/FX provider skeletons.
- `app/risk`: deterministic risk engine, kill switch, long-only checks, market calendar, FX freshness, sizing, exposure, drawdown, slippage, liquidity.
- `app/execution`: idempotency, guarded execution, and order reconciliation.
- `app/api`: FastAPI status/control endpoints. No live order placement endpoint is exposed in this phase.

## Local Setup

Use Python 3.11+.

```powershell
cd "C:\Users\Sandeep.Pathak\Documents\New project\dalalwall-ai-alpha-agent"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .[dev]
copy .env.example .env
```

Do not commit `.env`.

For Windows-specific setup, see `docs/windows_setup.md`.
For database setup choices, see `docs/database_setup.md`.
For email setup, see `docs/email_setup.md`.
For the professional intraday shadow core, see `docs/professional_intraday_shadow.md`.

## Docker Setup

Docker is optional for this phase but recommended for PostgreSQL and Redis.

```powershell
docker compose up -d postgres redis mailpit
```

The compose file only contains local development credentials.

## Migrations

```powershell
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

For a quick local metadata create during early development:

```powershell
python scripts/init_db.py create-all
```

## Tests

```powershell
pytest
```

The mandatory tests verify defaults, kill switch behavior, stop-loss rejection, position sizing, shadow-mode execution blocking, long-only sell enforcement, FX freshness, broker/provider health gates, compliance gates, idempotency, reconciliation, secret masking, and `.env` ignore protection.

## FastAPI

```powershell
uvicorn app.main:app --reload
```

Useful endpoints:

- `GET /health`
- `GET /dashboard`
- `GET /dashboard/data`
- `GET /shadow/status`
- `GET /shadow/readiness`
- `GET /shadow/professional/status`
- `POST /shadow/professional/run-india-once`
- `POST /shadow/run-cycle`
- `GET /system/status`
- `POST /system/kill-switch/on`
- `POST /system/kill-switch/off`
- `GET /brokers/status`
- `GET /providers/status`
- `GET /risk/status`
- `GET /alerts/daily-summary`
- `POST /alerts/daily-summary/email`

## Emergency Kill Switch

```powershell
python scripts/emergency_kill_switch.py on
```

The kill switch blocks live entry orders. Turning it off is not enough to enable live trading.

## Zerodha Setup Notes

Zerodha integration is a Kite Connect adapter skeleton that uses the real Kite HTTP API. Configure:

- `ZERODHA_API_KEY`
- `ZERODHA_API_SECRET`
- `ZERODHA_ACCESS_TOKEN`

Phase 2 v1 is CNC equity/ETF only. F&O, derivatives, leverage, margin, and short selling are blocked by config and risk policy.

For the daily Zerodha shadow-live connection flow, see `docs/zerodha_shadow_live_setup.md`.

## Shadow Training

The shadow-training loop is observation-only. It may read real market/provider data and write signals, risk events, and audit records, but it never creates order intents and never places orders.

```powershell
python scripts/run_shadow_training.py once
python scripts/run_shadow_training.py loop --interval-seconds 900
python scripts/shadow_readiness.py check
.\scripts\start_shadow_stack.ps1
.\scripts\stop_shadow_stack.ps1
.\scripts\daily_zerodha_auth_assist.ps1
.\scripts\daily_summary.ps1
.\scripts\start_mailpit.ps1
.\scripts\install_windows_tasks.ps1
```

Runtime logs are written to `.runtime/shadow_training.log`.
The local dashboard stack standardizes on `http://127.0.0.1:8002/dashboard`.

The Windows task installer creates weekday tasks for Zerodha auth assistance, stack start, and daily summary generation. It also starts Mailpit and the shadow dashboard stack at Windows logon so the dashboard comes back after a laptop restart. It does not bypass Zerodha login/2FA, and it does not send emails unless SMTP is configured and email sending is explicitly enabled.
If Task Scheduler cannot be updated due Windows permissions, copy `scripts\Sandy-Trading-AI-AutoStart.cmd` into the current user's Startup folder. It starts Docker Desktop if needed, waits for PostgreSQL, then starts the dashboard on port `8002`.

Shadow mode creates shadow transactions in the shadow ledger only. It does not place Zerodha broker orders.

Daily email summaries require:

- `EMAIL_TO`
- `ENABLE_EMAIL_SUMMARY=true`
- `EMAIL_SMTP_HOST`
- `EMAIL_SMTP_PORT`
- `EMAIL_USERNAME`
- `EMAIL_PASSWORD`

For local preview without external delivery:

```powershell
docker compose up -d mailpit
.\scripts\daily_summary.ps1 -SendEmail
```

Then open `http://127.0.0.1:8025`.

## Alpaca Setup Notes

Alpaca integration uses the real Alpaca API. The default base URL is paper:

`ALPACA_BASE_URL=https://paper-api.alpaca.markets`

Configure:

- `ALPACA_API_KEY`
- `ALPACA_SECRET_KEY`

Crypto, options, margin, shorting, and leverage paths are out of scope for v1.

## Risk Rulebook Summary

RiskEngine checks include kill switch, trading mode, live flag, India compliance, broker credentials/session/account health, provider availability, market calendar, data freshness, FX freshness for US trades, reconciliation, long-only rules, stop-loss requirement, cash, loss/drawdown limits, exposure limits, max open positions, liquidity, slippage, reward/risk, and position sizing.

Position sizing begins with:

`risk_amount = portfolio_value_inr * max_risk_per_trade_pct`

`quantity_by_risk = floor(risk_amount / abs(entry_price - stop_loss))`

Then it is capped by position value, cash, market exposure, sector exposure, strategy exposure, and liquidity placeholders.

## India Compliance Warning

India algo/API trading must comply with current SEBI, exchange, and broker rules. LIVE_AUTONOMOUS for India is blocked unless compliance state is approved or explicitly configured as compliant for the user's broker/API flow.

See `docs/compliance_notes.md`.

## Why Shadow-Live First

Shadow-live with real data validates provider freshness, broker sessions, risk decisions, audit events, and reconciliation logic without placing real orders. This is the right first mile for real-money software.

## Moving From Shadow To Micro-Live

Before `MICRO_LIVE_AUTONOMOUS`, all of the following must be true:

- `.env` explicitly enables live trading.
- Kill switch is off.
- Broker and provider health are valid.
- Market calendar is open.
- FX is fresh for US trades.
- India compliance is approved where required.
- RiskEngine approves the trade.
- ExecutionAgent receives a valid `risk_decision_id`.
- Idempotency and reconciliation are functioning.

## Live Trading Checklist

Use `docs/live_trading_checklist.md`. Do not bypass it.

## Known Limitations

- Calendar is a simple weekday/session-hours service and does not yet include exchange holidays.
- Alembic migration revision is not generated yet; local setup currently uses metadata create-all.
- Broker adapters are skeletons and require credentialed real-provider testing.
- No production order placement API endpoint exists in this phase.
- Shadow training creates observation-only shadow transactions; no real broker orders, strategy engine, or LLM execution loop is implemented yet.

## Future Roadmap

- Real migrations and seed scripts.
- Exchange holiday calendars.
- Full order reconciliation workers.
- Provider-specific market data normalization.
- Shadow-live dashboards.
- Strategy registry and deterministic signal validation.
- Optional LLM analysis layer after deterministic core hardening.
