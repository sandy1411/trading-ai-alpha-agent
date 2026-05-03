# Zerodha Shadow-Live Setup

Use this flow to connect Zerodha Kite Connect without enabling live autonomous trading.

## Safety Defaults

Keep:

```env
TRADING_MODE=SHADOW_LIVE_REAL_DATA
LIVE_TRADING_ENABLED=false
KILL_SWITCH=true
```

This lets the platform validate real credentials, session health, provider health, and risk decisions without placing real orders.

## Zerodha Requirements

You need:

- Active Zerodha trading account.
- Kite Connect app from the Zerodha developer console.
- `ZERODHA_API_KEY`
- `ZERODHA_API_SECRET`
- Daily `ZERODHA_ACCESS_TOKEN`

Official docs:

- https://kite.trade/docs/connect/v3/
- https://kite.trade/docs/connect/v3/user/
- https://kite.trade/docs/connect/v3/orders/

## Configure `.env`

```env
ZERODHA_API_KEY=your_api_key
ZERODHA_API_SECRET=your_api_secret
ZERODHA_ACCESS_TOKEN=
```

Do not commit `.env`.

## Create Kite Connect App

1. Go to https://developers.kite.trade/
2. Sign in with your Zerodha account.
3. Create a new Kite Connect app.
4. Use a local redirect URL:

```text
http://127.0.0.1:8000/zerodha/callback
```

5. Copy the generated `api_key` and `api_secret`.
6. Put them only in your local `.env`.

Never paste the API secret into chat or commit it to Git.

## Generate Login URL

```powershell
python scripts/zerodha_login_url.py
```

Open the URL and complete Zerodha login. If the FastAPI app is running and the Kite app redirect URL is:

```text
http://127.0.0.1:8000/zerodha/callback
```

the callback automatically saves the `request_token` and exchanges it for an access token when `ZERODHA_AUTO_EXCHANGE_ON_CALLBACK=true`.

You can also open the dashboard Ops tab and click **Open Zerodha Login**.

## Exchange Request Token

```powershell
python scripts/zerodha_exchange_token.py --request-token "REQUEST_TOKEN_FROM_REDIRECT" --write-env
```

This manual exchange command is only a fallback if the local callback did not complete.

## Daily Automation Boundary

The system can automate everything after Zerodha returns a `request_token`:

- scheduled pre-market auth assist
- login URL generation
- local callback capture
- request-token exchange
- local access-token storage
- broker/provider health checks
- shadow training startup

It cannot safely or compliantly bypass Zerodha's broker login/2FA step. Official Kite Connect flow requires a successful login redirect before a `request_token` exists, and Zerodha forum guidance has historically stated that the user must log in manually at least once per day. Treat full zero-intervention Zerodha login as unsupported.

The Windows scheduled task `Sandy-Trading-AI Zerodha Auth Assist` opens this flow at 08:45 on weekdays.

## Check Broker Health

```powershell
python scripts/check_broker_health.py run
```

Expected for a healthy shadow-live connection:

- Zerodha auth status valid.
- Account active.
- Positions reconciled.

Even then, live orders remain blocked unless all live gates are deliberately enabled and approved.

## What V1 Allows

Only CNC long-only equity/ETF order intents are in scope. V1 blocks:

- Intraday leverage.
- Margin.
- Short selling.
- F&O.
- Options.
- Derivatives.
- Crypto.
- Unreconciled duplicate orders.
