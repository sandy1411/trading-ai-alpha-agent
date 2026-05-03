# Sandy-Trading-AI Project Handover

Last reviewed: 2026-05-03
Repository: https://github.com/sandy1411/trading-ai-alpha-agent
Local branch: `main`
Latest reviewed commit before this handover: `5a34484 Initial safety-first shadow trading platform`

## Executive Summary

Sandy-Trading-AI is a Python 3.11 FastAPI trading-platform foundation for India and US market research. The project is intentionally safety-first. It starts in `SHADOW_LIVE_REAL_DATA`, keeps `LIVE_TRADING_ENABLED=false`, and keeps `KILL_SWITCH=true`.

The current codebase is not a profit engine and is not ready for autonomous live trading. It is a shadow-live research and control-plane foundation with real-provider integration skeletons, deterministic risk checks, durable system state/idempotency models, dashboard visibility, local email summary support, and tests around fail-closed behavior.

The app can run locally, tests pass, and the dashboard/API boot successfully. The next developer should stabilize migrations, persistence, Zerodha data/session handling, and shadow observation quality before adding any new strategy or live-trading capability.

Important safety status:

- No live order placement endpoint is exposed.
- Shadow training records observations and hypothetical P&L only.
- `ExecutionAgent` requires a valid risk decision, live-capable mode, live flag enabled, kill switch off, broker health, compliance where needed, and idempotency.
- Low-level broker adapters contain real `place_order` implementations and must only be called through guarded execution paths.
- `.env` exists locally and contains sensitive values, but it is ignored by Git and was not committed.

## Project Overview

The system is intended to become a low-risk trading automation platform for personal use with Zerodha/Kite Connect and Alpaca/US market-data support. Current emphasis is on:

- Real provider/broker integration points.
- Fail-closed configuration.
- Shadow-live validation.
- Auditability.
- Risk controls.
- Compliance-readiness for Indian algo/API trading.
- Human review before any live progression.

The project explicitly does not guarantee profits, CAGR, win rate, or loss avoidance.

## Technology Stack

- Language: Python 3.11+
- API framework: FastAPI
- Validation/settings: Pydantic v2 and pydantic-settings
- ORM/database: SQLAlchemy 2.x, PostgreSQL target, SQLite used in tests
- Migrations: Alembic configured, but no real migration revision has been generated yet
- HTTP clients: httpx
- Data/science libs: pandas, numpy
- Logging: structlog
- Retry support dependency: tenacity
- CLI scripts: typer and PowerShell wrappers
- Test framework: pytest and pytest-asyncio
- Local services: Docker Compose for PostgreSQL, Redis, and Mailpit
- Optional external providers: Zerodha/Kite, Alpaca, Alpha Vantage, Finnhub, Benzinga placeholders

## Repository Structure Summary

Top-level files:

- `.env.example`: safe documented configuration defaults.
- `.gitignore`: ignores `.env`, `.env.*`, `.venv/`, `.runtime/`, logs, caches, and build artifacts.
- `Dockerfile`: builds a Python 3.11 app image and starts `uvicorn app.main:app`.
- `docker-compose.yml`: local PostgreSQL, Redis, and Mailpit services. App service is commented out.
- `pyproject.toml`: package metadata, dependencies, optional dev dependencies, pytest and ruff config.
- `alembic.ini`: Alembic config pointing at PostgreSQL default URL.
- `README.md`: main setup, safety, Zerodha, Alpaca, shadow-training, dashboard, and checklist docs.

Main folders:

- `app/`: application package.
- `app/api/routes/`: FastAPI routes and dashboard HTML/WebSocket code.
- `app/brokers/`: broker abstraction plus Zerodha and Alpaca adapters.
- `app/core/`: settings, enums, logging, errors, time helpers, secret masking.
- `app/data_providers/`: real data provider abstraction and provider skeletons.
- `app/db/`: SQLAlchemy base, session, and models.
- `app/execution/`: execution guardrails, idempotency, router, reconciliation.
- `app/portfolio/`: early P&L, FX, allocation helpers.
- `app/risk/`: deterministic risk engine and risk-rule helper modules.
- `app/schemas/`: strict Pydantic contracts.
- `app/services/`: app services for state, readiness, dashboard data, broker/provider status, email, shadow training, and Zerodha token handling.
- `app/strategies/`: conservative shadow strategy and intraday shadow playbook.
- `scripts/`: local setup, auth, readiness, database, shadow loop, email, and task automation scripts.
- `tests/`: pytest suite covering config, risk, brokers, providers, dashboard, shadow training, idempotency, market calendar, and security.
- `docs/`: architecture, risk, compliance, setup, live checklist, Zerodha/US/email/database notes.

## Main Application Entry Points

- `app/main.py`: creates FastAPI app, configures logging, registers route modules.
- `uvicorn app.main:app --reload`: local API startup.
- `scripts/run_api.ps1`: PowerShell API helper.
- `scripts/start_shadow_stack.ps1`: starts Docker PostgreSQL/Redis, initializes metadata tables, starts FastAPI, and starts the shadow loop.
- `scripts/run_shadow_training.py once|loop`: observation-only shadow training.
- `scripts/shadow_readiness.py check`: readiness report for shadow mode.
- `scripts/zerodha_login_url.py`: creates Kite login URL.
- `scripts/zerodha_exchange_token.py`: exchanges Kite request token for access token.
- `scripts/daily_summary.ps1`: drafts and optionally sends daily summary email.

## Configuration And Secrets

Important safe defaults in `.env.example`:

- `TRADING_MODE=SHADOW_LIVE_REAL_DATA`
- `LIVE_TRADING_ENABLED=false`
- `KILL_SWITCH=true`
- `REAL_PROVIDER_REQUIRED=true`
- `BROKER_RECONCILIATION_REQUIRED=true`
- `RISK_ENGINE_REQUIRED=true`
- `ALLOW_DUMMY_BROKER=false`
- `ALLOW_MOCK_BROKER=false`
- `ALLOW_FAKE_MARKET_DATA=false`
- `ALLOW_FAKE_ORDER_FILLS=false`
- `LONG_ONLY_MODE=true`
- `ALLOW_MARGIN=false`
- `ALLOW_SHORT_SELLING=false`
- `ALLOW_OPTIONS=false`
- `ALLOW_DERIVATIVES=false`
- `ALLOW_CRYPTO=false`
- `ALLOW_LEVERAGED_ETFS=false`

Required local secrets, if using providers:

- Zerodha: `ZERODHA_API_KEY`, `ZERODHA_API_SECRET`, daily `ZERODHA_ACCESS_TOKEN`.
- Alpaca: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_BASE_URL`, `ALPACA_DATA_FEED`.
- FX: `ALPHA_VANTAGE_API_KEY`.
- Email: `EMAIL_SMTP_HOST`, `EMAIL_SMTP_PORT`, `EMAIL_USERNAME`, `EMAIL_PASSWORD`, `EMAIL_TO`, plus `ENABLE_EMAIL_SUMMARY=true`.

Observed local `.env` variable names were inspected without printing values. `.env` is ignored by Git.

## Current Architecture

Capital-sensitive path:

```text
Signal -> deterministic RiskEngine -> RiskDecision -> OrderIntent -> ExecutionAgent -> BrokerAdapter
```

Shadow path:

```text
Real provider quote -> ConservativeShadowStrategy -> AgentSignal -> RiskDecisionModel(NO_TRADE)
-> ShadowObservation -> PerformanceService -> Dashboard/Email summary
```

Dashboard path:

```text
FastAPI /dashboard -> embedded HTML/JS -> /dashboard/ws WebSocket -> PerformanceService.daily_summary()
```

State/persistence path:

```text
SQLAlchemy models -> PostgreSQL target -> SessionLocal -> services/scripts/API routes
```

## What Has Been Completed

### Foundation

Status: completed enough for Phase 0/1 skeleton.

Files:

- `app/core/config.py`
- `app/core/enums.py`
- `app/core/errors.py`
- `app/core/logging.py`
- `app/core/security.py`
- `app/core/time_utils.py`
- `pyproject.toml`
- `.env.example`
- `.gitignore`
- `Dockerfile`
- `docker-compose.yml`

What it does:

- Loads typed settings from `.env`.
- Defines trading, broker, provider, risk, order, compliance, and market enums.
- Provides fail-closed live-mode safety checks.
- Masks sensitive keys in structured mappings.
- Configures structured logging.

### Database Models

Status: partial foundation.

Files:

- `app/db/base.py`
- `app/db/session.py`
- `app/db/models/*.py`
- `alembic/env.py`
- `scripts/init_db.py`

Implemented tables/models:

- instruments
- market_data_bars
- news_items
- macro_observations
- fx_rates
- strategies
- agent_signals
- risk_decisions
- risk_events
- risk_config
- orders
- order_idempotency_keys
- positions
- portfolio_snapshots
- audit_logs
- system_state
- provider_health
- broker_health
- compliance_state
- backtest_runs
- shadow_observations
- daily_market_review_snapshots

Important limitation:

- Alembic is configured but only `.gitkeep` exists in `alembic/versions`. No generated migration is present. Current early setup uses `Base.metadata.create_all`.

### Pydantic Contracts

Status: implemented for current boundary objects.

Files:

- `app/schemas/signal.py`
- `app/schemas/risk.py`
- `app/schemas/order.py`
- `app/schemas/broker.py`
- `app/schemas/provider.py`
- `app/schemas/fx.py`
- `app/schemas/portfolio.py`
- `app/schemas/position.py`
- other read/status schema files

Important contracts:

- `TradeCandidate`
- `RiskDecision`
- `OrderIntent`
- `OrderRecord`
- `BrokerHealth`
- `ProviderHealth`
- `ComplianceStatus`
- `MarketCalendarStatus`
- `FXRateStatus`

### Zerodha/Kite Connect Integration

Status: partial real adapter and auth helper.

Files:

- `app/brokers/zerodha_broker.py`
- `app/data_providers/zerodha_data.py`
- `app/services/zerodha_token_service.py`
- `app/api/routes/zerodha.py`
- `scripts/zerodha_login_url.py`
- `scripts/zerodha_exchange_token.py`
- `docs/zerodha_shadow_live_setup.md`

What exists:

- Builds official Kite login URL.
- Stores request token locally.
- Exchanges request token for access token using Kite checksum flow.
- Saves access token to `.runtime/zerodha_access_token.txt` and `.env` if requested.
- Checks profile and margins for account health.
- Quote fetch uses `/quote`.
- Order placement implementation uses real Kite `/orders/regular`, CNC, NSE, DAY validity, and idempotency tag truncation.

Important limitations:

- Daily Zerodha login/2FA cannot be bypassed and remains manual.
- No WebSocket/ticker implementation exists.
- Historical candle fetch is not implemented.
- Instrument/token master download is not implemented.
- Adapter methods can place real orders if called directly. They must remain behind `ExecutionAgent`.

### Alpaca/US Integration

Status: partial real adapter and data provider.

Files:

- `app/brokers/alpaca_broker.py`
- `app/data_providers/alpaca_data.py`
- `docs/us_shadow_setup.md`

What exists:

- Account, positions, orders, order lookup.
- Real order placement method against configured Alpaca base URL.
- Latest bar fetch from Alpaca data API with configured feed.
- Default base URL is paper API.

Limitations:

- Shadow-only design currently.
- No historical data pipeline.
- No websocket feed.
- Broader US market data may require an Alpaca data subscription beyond IEX.

### Provider Integration

Status: partial skeletons.

Files:

- `app/data_providers/base.py`
- `app/data_providers/provider_health.py`
- `app/data_providers/alpha_vantage.py`
- `app/data_providers/finnhub.py`
- `app/data_providers/yahoo_research.py`
- `app/data_providers/fx_provider.py`

What exists:

- Provider health checker.
- Alpha Vantage quote and USD/INR FX.
- FX provider caches fresh USD/INR status in memory.
- Finnhub/Yahoo research placeholders or light implementations.

Limitations:

- No normalized market-data storage pipeline.
- No provider failover strategy.
- No websocket/live streaming provider.
- Provider health is cached in process only for 30 seconds.

### Risk Engine

Status: implemented deterministic v1, but still partial.

Files:

- `app/risk/risk_engine.py`
- `app/risk/position_sizing.py`
- `app/risk/long_only.py`
- `app/risk/market_calendar.py`
- `app/risk/data_freshness.py`
- `app/risk/drawdown.py`
- `app/risk/exposure.py`
- `app/risk/liquidity.py`
- `app/risk/slippage.py`
- `app/risk/rules.py`

Implemented controls:

- Kill switch rejection.
- Live flag rejection.
- Live-mode safety flag checks.
- India compliance gate for live-capable modes.
- Broker health checks.
- Provider health/freshness checks.
- Market calendar open check.
- US FX freshness check.
- Portfolio reconciliation requirement.
- Long-only sell restriction.
- Stop-loss required.
- Cash availability.
- Daily, weekly, monthly, and total drawdown checks.
- Open-position caps.
- Exposure caps.
- Reward/risk check.
- Position sizing by risk and caps.
- US price conversion through fresh USD/INR FX.

Limitations:

- Liquidity and slippage are placeholders/simple checks.
- Sector and strategy exposure are not fully enforced beyond basic fields.
- Market calendar uses static 2026 holidays and regular hours. It is not a production exchange calendar.
- No no-trade windows beyond session open/closed.
- No realized P&L risk lockouts from actual broker fills.

### Execution Guardrails

Status: partial guarded skeleton.

Files:

- `app/execution/order_manager.py`
- `app/execution/idempotency.py`
- `app/execution/reconciliation.py`
- `app/execution/order_router.py`

What exists:

- `ExecutionAgent.execute()` requires `risk_decision_id`.
- Requires `RiskDecision` approved/reduce-size.
- Requires live-capable mode.
- Requires `LIVE_TRADING_ENABLED=true`.
- Requires `KILL_SWITCH=false`.
- Requires live-ready broker health.
- Requires India compliance where applicable.
- Requires idempotency key.
- Reserves/upserts durable idempotency records.
- Unknown status blocks duplicates through idempotency state.

Limitations:

- `ExecutionAgent` does not currently persist a full `orders` table row; idempotency payload is durable but the main order lifecycle table is not fully wired into execution.
- No background reconciliation worker.
- No emergency square-off implementation.
- No manual approval workflow.
- Direct broker adapter calls remain possible by developers and must be avoided outside guarded execution.

### Shadow Training And Intraday Research

Status: shadow-only implemented, evidence collection still early.

Files:

- `app/services/shadow_training_service.py`
- `app/services/intraday_model_training_service.py`
- `app/strategies/conservative_shadow.py`
- `app/strategies/intraday_shadow.py`
- `scripts/run_shadow_training.py`
- `scripts/train_intraday_shadow_model.py`
- `docs/intraday_shadow_strategy.md`

What exists:

- India/US shadow observation cycles.
- Conservative quality filter using quote OHLC, average price, volume, range, gap, stop, target, reward/risk.
- Shadow observations with hypothetical quantity, notional, P&L.
- Intraday model report generator from shadow observations.
- Strategy playbook with opening range, VWAP pullback, gap-risk filter, and disabled fast mean reversion.

Important limitations:

- No learned predictive model exists yet.
- Current "training" is a diagnostic report, not ML training that can trade.
- No backtest/paper engine exists.
- Shadow observations can remain open; close-out rules need improvement.

### Dashboard/API Layer

Status: implemented operator dashboard and status APIs.

Files:

- `app/api/routes/dashboard.py`
- `app/services/performance_service.py`
- route files under `app/api/routes/`

Available endpoints:

- `GET /health`
- `GET /dashboard`
- `GET /dashboard/data`
- `GET /dashboard/ws`
- `GET /system/status`
- `POST /system/kill-switch/on`
- `POST /system/kill-switch/off`
- `GET /system/mode`
- `POST /system/mode`
- `GET /brokers/status`
- `GET /providers/status`
- `GET /risk/status`
- `GET /shadow/status`
- `GET /shadow/readiness`
- `POST /shadow/run-cycle`
- `GET /orders`
- `POST /orders/reconcile`
- `GET /portfolio/snapshot`
- `GET /zerodha/auth/status`
- `GET /zerodha/login`
- `GET /zerodha/callback`
- `GET /alerts/daily-summary`
- `POST /alerts/daily-summary/email`

No live order placement endpoint exists.

### Email Alerts

Status: local/external SMTP support implemented, disabled by default.

Files:

- `app/services/email_service.py`
- `app/api/routes/alerts.py`
- `scripts/send_daily_summary.py`
- `scripts/daily_summary.ps1`
- `docs/email_setup.md`

What exists:

- Plain-text daily shadow summary.
- Mailpit-compatible local preview.
- Optional SMTP send when explicitly enabled.

Important limitation:

- External email sends trading summaries outside the machine. Keep disabled until the user explicitly configures and accepts this data flow.

### Windows Automation

Status: helper scripts exist.

Files:

- `scripts/install_windows_tasks.ps1`
- `scripts/start_shadow_stack.ps1`
- `scripts/stop_shadow_stack.ps1`
- `scripts/daily_zerodha_auth_assist.ps1`
- `scripts/start_mailpit.ps1`

Tasks created by installer:

- Start Mailpit
- Zerodha Auth Assist
- Start Shadow Stack
- Start US Shadow Stack
- Daily Summary Email
- US Post-Market Summary Email

Important limitation:

- Zerodha auth assist can open the login flow and handle callback exchange, but it cannot bypass broker login/2FA.

### Tests

Status: present and passing.

Coverage areas:

- Safe config defaults.
- Live mode safety gating.
- Kill switch.
- Missing stop loss.
- Position sizing, including USD/INR conversion.
- Long-only sell restriction.
- Shadow mode cannot execute orders.
- Broker/session/provider health gates.
- India compliance gate.
- Market calendar.
- FX freshness.
- Idempotency and unknown status duplicate blocking.
- Durable idempotency store.
- System state persistence.
- Zerodha account/margin health behavior.
- Shadow training no-order behavior.
- Intraday model report safety.
- Dashboard/WebSocket/email summary behavior.
- Secret masking.
- `.env` ignore protection.
- No production fake/dummy broker/provider class names.

Latest verification:

- `56 passed in 1.53s`
- `ruff check .`: all checks passed
- API `/health` passed on a temporary local `uvicorn` run at port `8010`

## What Is Partially Completed

- Real broker adapters exist but need provider-credentialed integration tests in shadow/live-sandbox conditions.
- Zerodha auth flow exists, but daily login still requires user action.
- Shadow training exists, but is not a full paper trading or backtesting engine.
- Risk engine exists, but liquidity/slippage/sector/strategy constraints are not production-calibrated.
- Dashboard exists, but UI is embedded in one Python string and should be split into maintainable static assets later.
- Email exists, but real SMTP delivery remains user-configured and disabled by default.
- Database models exist, but migrations are missing.
- Order reconciliation endpoint is a placeholder.
- Redis exists in Compose but is not used by the application yet.

## What Is Missing

- Alembic initial migration and migration discipline.
- Instrument master download and token mapping for Zerodha.
- Historical candle ingestion and storage jobs.
- Live websocket/ticker ingestion for Zerodha and Alpaca.
- Backtesting engine.
- Paper-trading engine with clearly separated simulated fills and cost assumptions.
- Trade journal with lifecycle close-out, realized/unrealized P&L, and final outcome labels.
- Brokerage, taxes, slippage, and impact model.
- Robust market-calendar library integration.
- Background workers for provider polling, order reconciliation, and daily review.
- Real order table persistence from `ExecutionAgent`.
- Manual approval mode before live.
- Emergency square-off.
- CI/CD pipeline.
- Secrets manager integration.
- Formal deployment architecture.
- Broker/API compliance workflow UI and approval records.

## Current Gaps / Risks / Pending Work

### P0 Risks

- Direct `ZerodhaBroker.place_order()` and `AlpacaBroker.place_order()` are real order methods. They are not exposed through the API, but a developer could call them directly. Keep all order calls behind `ExecutionAgent` and consider adding an explicit execution context guard at adapter level.
- Alembic migrations are absent. Production-like use should not rely on `create_all`.
- `ExecutionAgent` writes durable idempotency data but does not insert/update the main `orders` table.
- Broker health and provider health records are modeled but status services currently cache in memory and return live checks, not persisted health rows.
- Zerodha daily auth cannot be fully automated without unsupported login/2FA bypass.
- No manual approval workflow exists for future live trading.
- India compliance approval must remain blocked unless broker/exchange/API flow is actually compliant.

### P1 Risks

- Market calendar is static/simple and can miss special sessions, half days, or future holiday changes.
- Shadow observations do not yet have robust close-out logic or final outcome labels.
- Liquidity/slippage checks are simple placeholders.
- No concurrency locking around shadow observation upserts beyond database transaction behavior.
- Provider rate limits and retry/backoff are not fully implemented.
- Dashboard data collection can call broker/provider health services and may be slow if providers degrade.
- External email can transmit trading summary data if enabled. Keep disabled unless explicitly intended.
- Alpaca paper account health does not mean live US trading readiness.

### P2 Risks

- Dashboard HTML/JS is embedded in `app/api/routes/dashboard.py`, making UI iteration clumsy.
- Redis is configured but unused.
- No coverage/reporting thresholds.
- No OpenAPI auth layer around control endpoints.
- No CI run currently visible in this repo.

## Setup Instructions

Create local environment:

```powershell
cd "C:\Users\Sandeep.Pathak\Documents\New project\dalalwall-ai-alpha-agent"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .[dev]
Copy-Item .env.example .env
```

Keep safe defaults:

```env
TRADING_MODE=SHADOW_LIVE_REAL_DATA
LIVE_TRADING_ENABLED=false
KILL_SWITCH=true
```

Start local infrastructure:

```powershell
docker compose up -d postgres redis mailpit
```

Initialize current metadata schema:

```powershell
.\.venv\Scripts\python.exe scripts\init_db.py create-all
```

Run API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open dashboard:

```text
http://127.0.0.1:8000/dashboard
```

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Run shadow readiness without placing orders:

```powershell
.\.venv\Scripts\python.exe scripts\shadow_readiness.py check
```

Run one shadow cycle without placing orders:

```powershell
.\.venv\Scripts\python.exe scripts\run_shadow_training.py once
```

## File-By-File Explanation

Top-level:

- `.env.example`: safe configuration template.
- `.gitignore`: prevents secrets/runtime files from being committed.
- `Dockerfile`: app image definition.
- `docker-compose.yml`: local Postgres/Redis/Mailpit.
- `pyproject.toml`: package/dependency/test/lint config.
- `alembic.ini`: Alembic configuration.
- `README.md`: user-facing setup and safety documentation.

Alembic:

- `alembic/env.py`: migration environment using `Base.metadata`.
- `alembic/versions/.gitkeep`: placeholder only. No migrations yet.

Core:

- `app/main.py`: FastAPI app factory/route registration.
- `app/core/config.py`: typed settings and live safety validation.
- `app/core/enums.py`: trading, broker, provider, order, risk, compliance enums.
- `app/core/errors.py`: domain exceptions.
- `app/core/logging.py`: structlog setup.
- `app/core/security.py`: secret masking helpers.
- `app/core/time_utils.py`: UTC/timezone helpers.

Database:

- `app/db/session.py`: SQLAlchemy engine and session factory.
- `app/db/base.py`: declarative base, timestamp mixin, JSONB variant.
- `app/db/models/instrument.py`: tradable instrument metadata.
- `app/db/models/market_data.py`: market bars.
- `app/db/models/news.py`: news records.
- `app/db/models/macro.py`: macro observations.
- `app/db/models/fx.py`: FX rates.
- `app/db/models/strategy.py`: strategy metadata.
- `app/db/models/signal.py`: agent/strategy signal records.
- `app/db/models/risk.py`: risk decisions, risk events, risk config.
- `app/db/models/order.py`: orders and durable idempotency keys.
- `app/db/models/position.py`: positions.
- `app/db/models/portfolio.py`: portfolio snapshots.
- `app/db/models/audit.py`: audit logs.
- `app/db/models/system_state.py`: system state, broker/provider health, compliance state.
- `app/db/models/backtest.py`: backtest run record.
- `app/db/models/shadow.py`: shadow observations and daily review snapshots.

Schemas:

- `app/schemas/common.py`: strict base schemas and ID helper.
- `app/schemas/signal.py`: `TradeCandidate`.
- `app/schemas/risk.py`: `RiskConfig`, `RiskDecision`, calendar and compliance schemas.
- `app/schemas/order.py`: `OrderIntent` and `OrderRecord`.
- `app/schemas/broker.py`: broker health contract.
- `app/schemas/provider.py`: provider health contract.
- `app/schemas/fx.py`: FX freshness/rate contract.
- `app/schemas/portfolio.py`: portfolio snapshot contract.
- `app/schemas/position.py`: open position contract.
- Other schema files are lightweight read/status placeholders.

Brokers/providers:

- `app/brokers/base.py`: abstract broker interface and broker result/account schemas.
- `app/brokers/zerodha_broker.py`: real Kite HTTP adapter.
- `app/brokers/alpaca_broker.py`: real Alpaca adapter.
- `app/brokers/broker_health.py`: broker health checker.
- `app/brokers/broker_session.py`: session validator.
- `app/data_providers/base.py`: abstract provider interface.
- `app/data_providers/zerodha_data.py`: Kite quote provider.
- `app/data_providers/alpaca_data.py`: Alpaca latest bar provider.
- `app/data_providers/alpha_vantage.py`: Alpha Vantage quote provider.
- `app/data_providers/fx_provider.py`: Alpha Vantage USD/INR provider with in-memory cache.
- `app/data_providers/finnhub.py`: Finnhub news/provider skeleton.
- `app/data_providers/yahoo_research.py`: Yahoo research placeholder.
- `app/data_providers/provider_health.py`: provider health checker.

Risk/execution:

- `app/risk/risk_engine.py`: deterministic risk engine.
- `app/risk/position_sizing.py`: risk sizing and caps.
- `app/risk/long_only.py`: sell/short protection.
- `app/risk/market_calendar.py`: v1 session/holiday calendar.
- `app/risk/kill_switch.py`: in-memory snapshot model and simple kill switch helper.
- `app/risk/data_freshness.py`: provider and FX freshness rejection reasons.
- `app/risk/drawdown.py`: loss/drawdown rejections.
- `app/risk/exposure.py`: exposure rejections.
- `app/risk/liquidity.py`: liquidity placeholder checks.
- `app/risk/slippage.py`: slippage placeholder checks.
- `app/risk/rules.py`: stop-loss and reward/risk checks.
- `app/execution/order_manager.py`: guarded `ExecutionAgent`.
- `app/execution/idempotency.py`: durable and test in-memory idempotency stores.
- `app/execution/reconciliation.py`: broker order reconciliation wrapper.
- `app/execution/order_router.py`: broker selector.

Services:

- `app/services/system_state_service.py`: durable global state and audit entries, fail-closed fallback.
- `app/services/audit_service.py`: masked structured audit logging.
- `app/services/broker_service.py`: cached broker health checks.
- `app/services/provider_service.py`: cached provider health checks.
- `app/services/shadow_readiness_service.py`: shadow readiness report.
- `app/services/shadow_training_service.py`: observation-only shadow loop.
- `app/services/intraday_model_training_service.py`: shadow model diagnostics/reporting.
- `app/services/performance_service.py`: dashboard and daily summary aggregation.
- `app/services/email_service.py`: daily summary text and SMTP send.
- `app/services/zerodha_token_service.py`: Kite login URL, token storage, token exchange.

API routes:

- `app/api/routes/health.py`: `/health`.
- `app/api/routes/dashboard.py`: dashboard page/data/WebSocket.
- `app/api/routes/system.py`: status, mode, kill switch.
- `app/api/routes/brokers.py`: broker health.
- `app/api/routes/providers.py`: provider health.
- `app/api/routes/risk.py`: risk status.
- `app/api/routes/shadow.py`: shadow status/readiness/run-cycle.
- `app/api/routes/orders.py`: read orders and placeholder reconciliation.
- `app/api/routes/portfolio.py`: portfolio snapshot.
- `app/api/routes/zerodha.py`: Zerodha auth status/login/callback.
- `app/api/routes/alerts.py`: daily summary preview/send.

Strategies:

- `app/strategies/conservative_shadow.py`: conservative stop-aware shadow assessment.
- `app/strategies/intraday_shadow.py`: intraday strategy playbook and promotion gates.

Scripts:

- `scripts/setup_check.ps1`: local environment check.
- `scripts/install_windows_prereqs.ps1/.cmd`: Windows prerequisite helper.
- `scripts/docker_up.ps1/.cmd`: start Docker services.
- `scripts/db_status.ps1/.cmd`: database/Redis status.
- `scripts/db_shell.ps1/.cmd`: database shell through Docker.
- `scripts/init_db.py`: metadata create-all.
- `scripts/run_api.ps1`: start API.
- `scripts/start_shadow_stack.ps1`: start local stack and shadow loop.
- `scripts/stop_shadow_stack.ps1`: stop local stack processes.
- `scripts/run_shadow_training.py`: shadow cycle runner.
- `scripts/shadow_readiness.py`: readiness CLI.
- `scripts/train_intraday_shadow_model.py`: shadow model report CLI.
- `scripts/check_broker_health.py`: broker health CLI.
- `scripts/check_provider_health.py`: provider health CLI.
- `scripts/reconcile_orders.py`: reconciliation placeholder.
- `scripts/emergency_kill_switch.py`: kill switch CLI.
- `scripts/zerodha_login_url.py`: Kite login URL CLI.
- `scripts/zerodha_exchange_token.py`: Kite request-token exchange CLI.
- `scripts/daily_zerodha_auth_assist.ps1`: daily auth helper.
- `scripts/send_daily_summary.py`: summary draft/email CLI.
- `scripts/daily_summary.ps1`: summary PowerShell wrapper.
- `scripts/start_mailpit.ps1`: local Mailpit helper.
- `scripts/install_windows_tasks.ps1`: Windows scheduled task installer.

Docs:

- `docs/architecture.md`: high-level deterministic architecture.
- `docs/risk_rulebook.md`: live gate checklist.
- `docs/compliance_notes.md`: India/US compliance warnings.
- `docs/live_trading_checklist.md`: pre-live checklist.
- `docs/development_plan.md`: current phase plan.
- `docs/broker_setup.md`: broker notes.
- `docs/zerodha_shadow_live_setup.md`: Kite setup and daily auth boundary.
- `docs/us_shadow_setup.md`: Alpaca/US setup.
- `docs/database_setup.md`: Docker/Postgres/Redis guide.
- `docs/email_setup.md`: Mailpit/external SMTP guide.
- `docs/windows_setup.md`: Windows setup.
- `docs/intraday_shadow_strategy.md`: shadow-only intraday research plan.

Tests:

- `tests/conftest.py`: fixtures.
- `tests/test_config_defaults.py`: safe defaults and live flag validation.
- `tests/test_kill_switch.py`: kill-switch rejection.
- `tests/test_risk_engine.py`: risk rejection gates.
- `tests/test_position_sizing.py`: sizing and US FX conversion.
- `tests/test_long_only_execution.py`: long-only and execution preconditions.
- `tests/test_shadow_live_no_order_placement.py`: shadow mode execution block.
- `tests/test_fx_conversion.py`: FX freshness and missing FX.
- `tests/test_fx_provider_cache.py`: FX cache behavior.
- `tests/test_market_calendar.py`: session/holiday checks.
- `tests/test_broker_session.py`: session validator.
- `tests/test_real_provider_config.py`: fake/dummy provider guard and `.env` ignore.
- `tests/test_order_idempotency.py`: duplicate prevention and durable store.
- `tests/test_order_reconciliation.py`: unknown status duplicate blocking.
- `tests/test_security.py`: secret masking.
- `tests/test_system_state_service.py`: persisted kill switch and live-mode block.
- `tests/test_zerodha_broker.py`: Zerodha account health/margins.
- `tests/test_conservative_shadow_strategy.py`: stop/target/RR and no-ohlc rejection.
- `tests/test_intraday_shadow_playbook.py`: playbook safety.
- `tests/test_intraday_model_training_service.py`: model report safety.
- `tests/test_shadow_training_service.py`: no-order shadow observations.
- `tests/test_dashboard_and_alerts.py`: dashboard, WebSocket, daily review, email preview.

## Recommended Next Development Plan

### Phase 1: Stabilize Project Foundation

- Generate first Alembic migration and remove reliance on `create_all`.
- Add CI that runs pytest and ruff.
- Split dashboard static assets from Python route file.
- Add API auth for control endpoints before any wider network exposure.
- Add stronger logging/audit persistence for all state changes.

### Phase 2: Zerodha Integration Hardening

- Implement instrument master download and token mapping.
- Implement historical candle fetch and normalized storage.
- Implement Zerodha ticker/WebSocket client with reconnect/backoff.
- Persist broker/provider health rows.
- Add integration tests that run only when explicit credentials/test flags are present.
- Keep daily login/2FA human-auth boundary documented and enforced.

### Phase 3: Paper Trading First

- Add a clearly separated paper/research execution engine, not a production broker adapter.
- Model brokerage, taxes, spread, slippage, and impact.
- Track trade lifecycle, journal, stop/target/time exits, and realized P&L.
- Enforce daily loss, max trades, and cooldowns in paper mode.
- Prevent paper objects from being used as live broker fallbacks.

### Phase 4: Backtesting

- Store candles with source and freshness metadata.
- Add deterministic strategy replay.
- Track metrics: expectancy, drawdown, win rate, profit factor, risk/reward, turnover, costs.
- Add walk-forward and out-of-sample validation.
- Compare strategies without optimizing only for returns.

### Phase 5: Risk Engine

- Add durable risk config loading and change audit.
- Add daily/weekly/monthly realized risk lockouts from broker/account data.
- Add max trades per day, max order quantity, no-trade windows, and circuit breaker.
- Add robust exchange calendar library.
- Add market-data freshness by symbol.
- Add order-level manual approval for any future live path.

### Phase 6: Controlled Live Trading

- Only after shadow and paper evidence passes review.
- Start with manual approval mode and tiny size.
- Require broker position/order reconciliation before and after every order.
- Require durable idempotency and order row writes transactionally.
- Add emergency square-off and stop-all entry controls.
- Keep India live blocked unless compliance state is genuinely approved for the user's broker/API flow.

## Commands Executed During This Handover

Inspection:

```powershell
git status --short --branch
git log --oneline --decorate --max-count=10
git remote -v
git ls-files
Get-ChildItem -Force
Get-Content -LiteralPath <selected files> -Raw
git grep -n "<patterns>" <paths>
git check-ignore -v .env .runtime .venv scripts/install_windows_prereqs.log
```

Verification:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Local run check:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
Invoke-RestMethod -Uri http://127.0.0.1:8010/health
```

Results:

- Tests: `56 passed in 1.53s`
- Lint: `All checks passed!`
- API health: `{"status":"ok"}` on temporary port `8010`

## Final Advice Before Continuing Development

Do not add aggressive strategies next. Build the boring safety infrastructure first: migrations, durable order lifecycle, broker/provider health persistence, instrument/candle data, shadow close-out labels, and paper trading with costs.

Do not enable live trading until there is enough shadow and paper evidence, the broker/session/provider/calendar/FX/compliance gates are proven, and a manual approval mode exists. No-trade and cash are valid outcomes.
