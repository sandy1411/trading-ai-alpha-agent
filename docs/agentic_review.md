# Agentic Review Layer

The agentic layer is a research, criticism, safety, and reporting layer. It is not the trader.

## Authority

Agents may:

- block unsafe shadow trades
- reduce confidence
- recommend risk reduction
- flag uncertainty
- write review reports
- propose strategy changes for backtesting

Agents must not:

- place orders
- enable live trading
- increase risk
- force trades
- modify journals
- change active strategy thresholds during market hours
- promote untested changes

## Flow

- Pre-market: `MarketContextAgent`, `ComplianceSafetyAgent`, `DriftDetectionAgent`
- Regime review: `RegimeReviewAgent`
- Signal review: `SignalCriticAgent`
- Pre-shadow-execution: `RiskAuditorAgent`
- Post-shadow-execution: `ExecutionSimulationAgent`
- Post-trade: `PostTradeReviewAgent`
- End of day: `DailyReportAgent`, `StrategyImprovementAgent`, `DriftDetectionAgent`
- Promotion gate: `BacktestValidationAgent`, `ComplianceSafetyAgent`, `LiveReadinessEvaluator`

## Journals

Agent decisions are JSONL files under:

```text
.runtime/agentic/
```

Each row stores prompt version, prompt checksum, input hash, raw output, parsed output, schema status, confidence, severity, recommendation, final action, and related signal/trade identifiers.

## Endpoints

```powershell
Invoke-RestMethod http://127.0.0.1:8002/shadow/agentic/status
Invoke-RestMethod http://127.0.0.1:8002/shadow/agentic/decisions
```

The endpoints are read-only and report `orders_placed=0`.
