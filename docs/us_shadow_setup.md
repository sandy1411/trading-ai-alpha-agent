# US Shadow Market Setup

US market support is shadow-only in this phase. It can observe US equities and ETFs with
real Alpaca market data and convert hypothetical USD exposure/P&L to INR using fresh
USD/INR FX. It does not place live Alpaca orders.

## Required Accounts And Keys

1. Create or sign in to Alpaca.
2. Open the Paper Trading account area.
3. Generate paper API keys.
4. Create a free Alpha Vantage API key for USD/INR FX.

Configure only your local `.env`:

```env
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_DATA_FEED=iex
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key
```

Do not commit `.env`.

## Safety Defaults

Keep:

```env
TRADING_MODE=SHADOW_LIVE_REAL_DATA
LIVE_TRADING_ENABLED=false
KILL_SWITCH=true
ALLOW_MARGIN=false
ALLOW_SHORT_SELLING=false
ALLOW_OPTIONS=false
ALLOW_DERIVATIVES=false
ALLOW_CRYPTO=false
ALLOW_LEVERAGED_ETFS=false
```

## What Runs

- US calendar gate: regular US session only.
- Alpaca market data gate: credentials required.
- USD/INR FX gate: Alpha Vantage FX required and fresh.
- Long-only equities/ETFs only.
- Shadow observations only; no order intent is created.
- Hypothetical notional and P&L are reported in INR.

## Checks

```powershell
.\.venv\Scripts\python.exe scripts\shadow_readiness.py check
```

The dashboard `Live Feed` tab shows `US shadow ready`, `Alpaca data`, and `USD/INR FX`.

## Provider Notes

Alpaca's free US equities market data plan uses IEX coverage. Broader exchange coverage
requires an Alpaca market-data subscription. Alpha Vantage's currency endpoint is used
for USD/INR.
