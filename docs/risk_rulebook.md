# Risk Rulebook

No-trade is valid. Cash is a valid position. Live-capable execution must pass:

1. Kill switch off.
2. Live-capable mode explicitly selected.
3. Live trading flag enabled.
4. India compliance approved where required.
5. Broker credentials, session, account, and trading status valid.
6. Provider health fresh.
7. Market open.
8. FX fresh for US trades.
9. Portfolio reconciliation complete.
10. Long-only rule satisfied.
11. Stop-loss present.
12. Cash available.
13. Daily, weekly, monthly, and total loss limits respected.
14. Exposure and open-position limits respected.
15. Liquidity, slippage, and reward/risk checks passed.
16. Position size above zero after all caps.

V1 blocks options, F&O, derivatives, leverage, crypto, margin, short selling, and leveraged ETFs.

## Research-only paper and backtest controls

The paper trading and backtesting layers are research accounting tools only. They are not broker
adapters, not a live-order fallback, and must never be wired into live execution as a substitute for
broker confirmation.

Paper/backtest results must include explicit transaction costs and slippage. Strategy callbacks in
the historical backtester receive only candles that were completed before the current execution bar,
so research cannot accidentally use future candle data.

Conservative defaults:

1. Entry requires a stop-loss.
2. Short selling is disabled.
3. Daily realized loss can block new paper entries.
4. Max entries per day can block over-trading.
5. If both stop-loss and profit target are inside one candle, stop-loss wins because intrabar path is
   unknown.
6. End-of-backtest closing is a research mark, not broker execution.
