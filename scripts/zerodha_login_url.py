from __future__ import annotations

import webbrowser

import typer

from app.services.zerodha_token_service import build_login_url

app = typer.Typer(help="Print the Zerodha Kite Connect login URL.")


@app.command()
def main(open_browser: bool = typer.Option(False, help="Open the login URL in the default browser.")) -> None:
    login_url = build_login_url()
    typer.echo(login_url)
    if open_browser:
        webbrowser.open(login_url)
    typer.echo(
        "After you complete Zerodha login, the local /zerodha/callback endpoint exchanges "
        "the request token automatically when ZERODHA_AUTO_EXCHANGE_ON_CALLBACK=true."
    )


if __name__ == "__main__":
    app()
