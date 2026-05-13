from __future__ import annotations

import typer

from app.core.errors import TradingAlphaError
from app.core.security import mask_secret
from app.services.zerodha_token_service import exchange_request_token, load_request_token, load_access_token

app = typer.Typer(help="Exchange a Zerodha request_token for an access_token.")


@app.command()
def main(
    request_token: str | None = typer.Option(
        None,
        help="request_token from the Kite redirect URL. If omitted, uses .runtime/zerodha_request_token.txt.",
    ),
    write_env: bool = typer.Option(True, help="Write ZERODHA_ACCESS_TOKEN into local .env."),
) -> None:
    resolved_request_token = request_token or load_request_token()
    if not resolved_request_token:
        raise typer.BadParameter("request_token missing. Complete Zerodha login first.")

    try:
        result = exchange_request_token(resolved_request_token, write_env=write_env)
    except TradingAlphaError as exc:
        raise typer.Exit(f"Token exchange failed: {exc}") from exc

    access_token = load_access_token()
    typer.echo(f"Access token stored locally: {mask_secret(access_token)}")
    typer.echo(f"user_id={result.get('user_id', '')}")
    typer.echo("Keep TRADING_MODE=SHADOW_LIVE, LIVE_TRADING_ENABLED=false, LIVE_ORDERS_ENABLED=false, KILL_SWITCH=true.")


if __name__ == "__main__":
    app()
