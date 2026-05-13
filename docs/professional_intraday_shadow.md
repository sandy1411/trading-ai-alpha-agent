# Professional Intraday Shadow Core

This is a research-only intraday pipeline. It uses live or replayed market snapshots, but it never calls Zerodha or Alpaca order placement.

## Flow

`MarketDataSnapshot -> DataQualityMonitor -> UniverseFilter -> MarketRegimeClassifier -> Strategy -> SignalScoringEngine -> RiskManager -> ShadowExecutionSimulator -> VirtualPositionManager -> CostModel -> TradeJournal -> DailyReviewEngine -> LiveReadinessEvaluator`

## Default Safety

- `TRADING_MODE=SHADOW_LIVE`
- `LIVE_TRADING_ENABLED=false`
- `LIVE_ORDERS_ENABLED=false`
- `KILL_SWITCH=true`

The professional shadow core has `can_place_live_orders = False` and does not import broker adapters.

## Run

Start the normal shadow stack:

```powershell
.\scripts\start_shadow_stack.ps1 -Port 8002
```

View API status:

```powershell
Invoke-RestMethod http://127.0.0.1:8002/shadow/professional/status
```

Dashboard data includes the same block at:

```powershell
Invoke-RestMethod http://127.0.0.1:8002/dashboard/data
```

## Journal

Journal rows are JSONL files under:

```text
.runtime/intraday_shadow/
```

Each row records signals, rejections, simulated fills, virtual position updates, exits, costs, and readiness blockers.

## Live Readiness

Live readiness remains blocked until at least:

- 30 shadow trading sessions
- 100 valid shadow trades
- positive net expectancy after costs
- profit factor above 1.3
- drawdown below threshold
- no unresolved execution/data-quality issues
- no overfitting warning
- manual approval flag

This implementation evaluates readiness only. It does not enable live trading.

