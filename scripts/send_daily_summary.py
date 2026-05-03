from __future__ import annotations

from datetime import date
from pathlib import Path

import typer

from app.core.errors import FailClosedError
from app.services.email_service import email_summary_service

app = typer.Typer(help="Preview or send the daily performance summary.")


@app.command()
def preview() -> None:
    typer.echo(email_summary_service.build_daily_summary_text())


@app.command()
def draft() -> None:
    runtime = Path(".runtime")
    runtime.mkdir(exist_ok=True)
    path = runtime / f"daily_summary_{date.today().isoformat()}.txt"
    path.write_text(email_summary_service.build_daily_summary_text(), encoding="utf-8")
    typer.echo(f"Daily summary draft written to {path}")


@app.command()
def email() -> None:
    try:
        result = email_summary_service.send_daily_summary()
    except FailClosedError as exc:
        raise typer.Exit(f"Email summary blocked: {exc}") from exc
    typer.echo(result["message"])


if __name__ == "__main__":
    app()
