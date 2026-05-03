# TODO For Next Codex Session

This list is ordered for safety. Do not start with new strategies or live trading.

## P0 - Protect Capital And Repository Integrity

### 1. Generate Initial Alembic Migration

- Priority: P0
- Description: Create the first real Alembic migration for all current SQLAlchemy models.
- Files likely involved: `alembic/versions/*.py`, `alembic/env.py`, `app/db/models/*.py`.
- Why it matters: Production-like database changes must be versioned; `create_all` is not enough.
- Acceptance criteria:
  - `alembic revision --autogenerate -m "initial schema"` creates a migration.
  - `alembic upgrade head` works on a clean PostgreSQL database.
  - Migration includes system state, order idempotency, shadow observations, and compliance tables.
- Testing required:
  - Run migration on clean local Postgres.
  - Run `pytest -q`.
  - Run `ruff check .`.

### 2. Persist Full Order Lifecycle From ExecutionAgent

- Priority: P0
- Description: When `ExecutionAgent.execute()` is ever used, persist a real `orders` row transactionally with idempotency.
- Files likely involved: `app/execution/order_manager.py`, `app/execution/idempotency.py`, `app/db/models/order.py`, `tests/test_order_idempotency.py`, `tests/test_order_reconciliation.py`.
- Why it matters: Idempotency payload exists, but the main order ledger is not fully written by the execution path.
- Acceptance criteria:
  - Reserving an idempotency key and creating an order record happen in one durable transaction.
  - Unknown broker status blocks duplicate orders after restart.
  - Reconciled broker response and final reconciliation state are stored.
- Testing required:
  - Unit tests using SQLite/Postgres test DB.
  - Duplicate submission restart simulation.
  - Unknown status reconciliation test.

### 3. Add Adapter-Level Live Order Guard

- Priority: P0
- Description: Prevent accidental direct calls to `ZerodhaBroker.place_order()` or `AlpacaBroker.place_order()` unless an explicit guarded execution context is supplied.
- Files likely involved: `app/brokers/base.py`, `app/brokers/zerodha_broker.py`, `app/brokers/alpaca_broker.py`, `app/execution/order_manager.py`, broker tests.
- Why it matters: Broker adapter methods are real order methods. They should not be casually callable by scripts or new code.
- Acceptance criteria:
  - Direct adapter `place_order()` calls fail closed unless called from approved execution path/context.
  - `ExecutionAgent` can still call adapters after all safety gates pass in tests.
  - No API order placement endpoint is added.
- Testing required:
  - Direct adapter call rejection test.
  - Guarded execution test with stubbed broker.

### 4. Add API Auth Before Exposing Control Endpoints

- Priority: P0
- Description: Protect `/system/*`, `/shadow/run-cycle`, `/alerts/daily-summary/email`, and future control routes with local auth or token protection before any network exposure.
- Files likely involved: `app/main.py`, `app/api/routes/*.py`, `app/core/config.py`, `tests/test_dashboard_and_alerts.py`.
- Why it matters: Kill switch and mode endpoints are sensitive controls.
- Acceptance criteria:
  - Local development remains ergonomic.
  - Control endpoints reject unauthenticated requests when auth is enabled.
  - `/health` remains public.
- Testing required:
  - Auth-on and auth-off route tests.

## P1 - Zerodha And Data Foundation

### 5. Implement Zerodha Instrument Master Download

- Priority: P1
- Description: Download, normalize, and store Zerodha instruments with tokens, segment, exchange, tick size, and tradability flags.
- Files likely involved: `app/data_providers/zerodha_data.py`, `app/db/models/instrument.py`, new script under `scripts/`, tests.
- Why it matters: Reliable market data and order placement need correct instrument tokens and metadata.
- Acceptance criteria:
  - NSE equity/ETF universe can be loaded.
  - Existing instruments are upserted.
  - F&O instruments are explicitly ignored or blocked for v1.
- Testing required:
  - Parser tests with small fixture.
  - Upsert tests.

### 6. Add Historical Candle Ingestion

- Priority: P1
- Description: Fetch and store historical candles for configured symbols using real provider APIs.
- Files likely involved: `app/data_providers/zerodha_data.py`, `app/data_providers/alpaca_data.py`, `app/db/models/market_data.py`, `scripts/`, tests.
- Why it matters: Backtesting, strategy validation, and intraday research need reproducible data.
- Acceptance criteria:
  - Stores candles with source, timeframe, UTC timestamps, OHLCV.
  - Rejects stale/missing/partial data.
  - Does not invent prices.
- Testing required:
  - Provider response parser tests.
  - Database write/read tests.

### 7. Implement Live Feed/WebSocket Skeleton

- Priority: P1
- Description: Add Zerodha ticker and Alpaca stream clients for market data ingestion only.
- Files likely involved: `app/data_providers/`, `app/services/`, `scripts/`.
- Why it matters: Intraday shadow training needs stable live data.
- Acceptance criteria:
  - Reconnect/backoff behavior exists.
  - Dropped/stale feed marks provider stale.
  - No order path exists in feed code.
- Testing required:
  - Unit tests for reconnect state machine.
  - Stale feed tests.

### 8. Persist Broker And Provider Health

- Priority: P1
- Description: Write health checks into `broker_health` and `provider_health` tables.
- Files likely involved: `app/services/broker_service.py`, `app/services/provider_service.py`, `app/db/models/system_state.py`.
- Why it matters: Live gates and audits should not depend only on in-process cache.
- Acceptance criteria:
  - Latest status is stored with timestamps.
  - Dashboard reads latest persisted status where appropriate.
  - Health degradation is auditable.
- Testing required:
  - Service tests with DB session.

## P1 - Shadow And Paper Trading

### 9. Add Shadow Observation Close-Out Rules

- Priority: P1
- Description: Close shadow hypotheses when stop, target, timeout, or session close is reached.
- Files likely involved: `app/services/shadow_training_service.py`, `app/db/models/shadow.py`, `app/services/performance_service.py`, tests.
- Why it matters: Open observations alone do not produce trustworthy performance evidence.
- Acceptance criteria:
  - Each shadow observation has final status and exit reason.
  - Daily review distinguishes open marks from closed hypotheses.
  - Stop and target outcomes are tracked.
- Testing required:
  - Stop hit, target hit, timeout, session close tests.

### 10. Add Paper Trading Engine Separate From Broker Adapters

- Priority: P1
- Description: Build a research-only paper engine with conservative costs, slippage, and brokerage assumptions. Do not make it a production broker adapter or live fallback.
- Files likely involved: new `app/paper/` or `app/backtesting/`, `app/db/models/`, tests.
- Why it matters: Strategy evidence must pass paper validation before live discussion.
- Acceptance criteria:
  - Paper fills are clearly marked as paper/research.
  - No paper class is selectable by production `OrderRouter`.
  - Costs/slippage are explicit and conservative.
  - Daily loss and max-trade limits are enforced.
- Testing required:
  - Fill simulation tests.
  - Cost model tests.
  - Risk limit tests.

### 11. Add Trade Journal And P&L Ledger

- Priority: P1
- Description: Store journal rows for shadow/paper/real modes with lifecycle states and P&L.
- Files likely involved: `app/db/models/`, `app/services/performance_service.py`, dashboard route/assets.
- Why it matters: Daily reviews need reliable realized and hypothetical accounting.
- Acceptance criteria:
  - Journal records entry, stop, target, exit, costs, gross/net P&L.
  - Dashboard separates real P&L from shadow/paper P&L.
  - Email summary clearly labels each P&L type.
- Testing required:
  - Journal aggregation tests.
  - Dashboard summary tests.

## P1 - Risk Engine Hardening

### 12. Add Market Calendar Library Or Daily Exchange Calendar Feed

- Priority: P1
- Description: Replace/static-augment 2026 holiday constants with a trusted calendar source.
- Files likely involved: `app/risk/market_calendar.py`, tests, dependencies if needed.
- Why it matters: Holidays, special sessions, and early closes must fail closed.
- Acceptance criteria:
  - Calendar unavailable returns closed/unknown, not open.
  - India and US holiday/special-session tests pass.
- Testing required:
  - Holiday, weekend, early close, unavailable source tests.

### 13. Add Daily Loss, Max Trades, Cooldown, And No-Trade Windows

- Priority: P1
- Description: Enforce daily realized loss, max trades/day, losing streak cooldown, and market-specific no-trade windows.
- Files likely involved: `app/risk/risk_engine.py`, `app/risk/drawdown.py`, new risk modules, tests.
- Why it matters: Intraday strategies can overtrade when conditions degrade.
- Acceptance criteria:
  - Risk engine rejects after configured thresholds.
  - Dashboard shows active lockouts.
  - Lockouts are auditable.
- Testing required:
  - Each threshold and reset-window test.

### 14. Improve Liquidity And Slippage Checks

- Priority: P1
- Description: Replace placeholder checks with symbol-level liquidity/spread/volume constraints.
- Files likely involved: `app/risk/liquidity.py`, `app/risk/slippage.py`, provider data models, tests.
- Why it matters: Intraday results are meaningless without spread and impact constraints.
- Acceptance criteria:
  - Missing spread/liquidity data fails closed.
  - Candidate quantity is capped by liquidity.
  - Slippage estimate is included in risk metrics.
- Testing required:
  - Missing data, low liquidity, high spread, normal case tests.

## P2 - Backtesting And Strategy Research

### 15. Build Backtesting Engine

- Priority: P2
- Description: Replay stored candles through strategy logic with conservative costs and risk rules.
- Files likely involved: new `app/backtesting/`, `app/db/models/backtest.py`, tests.
- Why it matters: Strategy changes need reproducible evidence before shadow/paper/live.
- Acceptance criteria:
  - Backtests produce trades, equity curve, drawdown, win rate, expectancy, profit factor.
  - Uses only historical data available at that timestamp.
  - No lookahead.
- Testing required:
  - Deterministic fixture backtests.
  - Lookahead guard tests.

### 16. Strategy Registry And Versioning

- Priority: P2
- Description: Register strategies with version, parameters, enabled markets, and promotion status.
- Files likely involved: `app/db/models/strategy.py`, `app/strategies/`, services, dashboard.
- Why it matters: Strategy behavior must be auditable and reproducible.
- Acceptance criteria:
  - Every signal includes strategy version and parameter hash.
  - Disabled strategies cannot emit live candidates.
- Testing required:
  - Registry tests.

### 17. Split Dashboard Into Static Assets

- Priority: P2
- Description: Move embedded dashboard HTML/CSS/JS out of `app/api/routes/dashboard.py`.
- Files likely involved: `app/static/`, `app/templates/`, `app/main.py`, dashboard tests.
- Why it matters: The dashboard is now too large for maintainable Python route code.
- Acceptance criteria:
  - Dashboard still loads.
  - WebSocket updates still work.
  - Tests pass.
- Testing required:
  - API and dashboard route tests.

## P2 - Operations And Deployment

### 18. Add CI

- Priority: P2
- Description: Add GitHub Actions for pytest, ruff, and secret scanning.
- Files likely involved: `.github/workflows/*.yml`.
- Why it matters: Prevent unsafe regressions.
- Acceptance criteria:
  - PRs run tests and lint.
  - CI fails if `.env` or known secret patterns are committed.
- Testing required:
  - Validate workflow on GitHub.

### 19. Add Structured Runtime Runbook

- Priority: P2
- Description: Document exact daily operations, failure handling, token refresh, shadow loop, email summary, and shutdown.
- Files likely involved: `docs/runbook.md`, `README.md`.
- Why it matters: Trading systems need repeatable operations.
- Acceptance criteria:
  - A new operator can start/stop/check the system safely.
  - Emergency kill-switch path is clear.
- Testing required:
  - Walk through locally in shadow mode.

### 20. Add Secrets Management Plan

- Priority: P2
- Description: Decide how secrets move from local `.env` to a safer store for any deployment.
- Files likely involved: docs and config.
- Why it matters: Broker/API credentials are sensitive.
- Acceptance criteria:
  - `.env` remains ignored.
  - Deployment docs do not expose secrets.
  - Logs mask secrets.
- Testing required:
  - Secret masking tests.
  - Repo secret scan.

## Hard Stop Rules For Next Session

- Do not enable `LIVE_TRADING_ENABLED=true`.
- Do not set `KILL_SWITCH=false` as a committed default.
- Do not add a public order placement API.
- Do not add a production `DummyBroker`, `MockBroker`, `FakeBroker`, or live fallback to simulated fills.
- Do not let LLM-generated text place orders.
- Do not bypass Zerodha login/2FA.
- Do not claim profit or "best in class" performance without evidence.
