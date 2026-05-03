# Broker Setup

## Zerodha

Set `ZERODHA_API_KEY`, `ZERODHA_API_SECRET`, and `ZERODHA_ACCESS_TOKEN`. The adapter uses Kite Connect HTTP endpoints and supports CNC equity/ETF order intents only in v1.

## Alpaca

Set `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, and `ALPACA_BASE_URL`. The default base URL is Alpaca paper. The v1 safety policy blocks margin, shorting, options, crypto, and leverage.

Missing credentials fail closed. Unknown order status requires reconciliation and blocks duplicate placement by idempotency key.
