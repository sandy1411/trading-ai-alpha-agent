# Sandy-Trading-AI Agent Guide

## Architecture

Sandy-Trading-AI is a shadow-first intraday trading research platform.

Core deterministic flow:

`MarketDataSnapshot -> DataQualityMonitor -> UniverseFilter -> MarketRegimeClassifier -> Strategy -> SignalScoringEngine -> RiskManager -> ShadowExecutionSimulator -> VirtualPositionManager -> TradeJournal -> DailyReviewEngine -> LiveReadinessEvaluator`

Agentic review flow:

`AgenticOrchestrator -> MarketContextAgent / RegimeReviewAgent / SignalCriticAgent / RiskAuditorAgent / ExecutionSimulationAgent / PostTradeReviewAgent / BacktestValidationAgent / DriftDetectionAgent / StrategyImprovementAgent / ComplianceSafetyAgent / DailyReportAgent`

Agents review, criticize, block, reduce confidence, and report. They never trade.

## Safety Rules

- Default must remain `TRADING_MODE=SHADOW_LIVE`.
- `LIVE_TRADING_ENABLED=false` and `LIVE_ORDERS_ENABLED=false` by default.
- `KILL_SWITCH=true` by default.
- Strategies may only produce `Signal` objects.
- RiskManager must approve before any shadow execution.
- In `SHADOW_LIVE`, execution must go only to `ShadowExecutionSimulator`.
- No agent or LLM output may directly place orders, enable live trading, increase size, average down, martingale, modify journals, or change active strategy thresholds during market hours.
- Invalid, incomplete, delayed, or unsafe agent output must fail closed.

## Forbidden Actions

- Do not place live broker orders.
- Do not enable live trading.
- Do not expose or log API keys, access tokens, or secrets.
- Do not create dummy/fake production brokers or fake production fills.
- Do not let strategy code import broker adapters.
- Do not let agentic code import `ExecutionAgent`, `OrderRouter`, `ZerodhaBroker`, or `AlpacaBroker`.
- Do not rewrite trade history or delete logs.

## Tests And Validation

Run:

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests scripts alembic
.\.venv\Scripts\python.exe -m pytest -q
```

Runtime smoke checks:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_shadow_stack.ps1 -Port 8002
Invoke-RestMethod http://127.0.0.1:8002/system/status
Invoke-RestMethod http://127.0.0.1:8002/shadow/professional/status
Invoke-RestMethod http://127.0.0.1:8002/shadow/agentic/status
```

Confirm every response has `orders_placed=0` for shadow endpoints.

## Coding Standards

- Keep risk controls deterministic and typed.
- Prefer existing modules and local patterns.
- Add narrowly scoped tests for every safety change.
- Use JSON-safe schemas for journals and dashboards.
- All agent decisions must be journaled under `.runtime/agentic/`.
- Config thresholds belong in settings/config files, not hidden in strategy logic.

## Live Trading

Live trading is out of scope for this repository state. Any future live path must require explicit environment flags, durable database state, risk approval, broker health, provider health, market calendar, FX freshness where applicable, compliance gate, idempotency, reconciliation, and manual approval.
