from __future__ import annotations

import json

import typer

from app.services.broker_service import broker_service

app = typer.Typer(help="Check configured broker health.")


@app.callback()
def callback() -> None:
    """Broker health commands."""


@app.command()
def run() -> None:
    statuses = [status.model_dump(mode="json") for status in broker_service.statuses()]
    typer.echo(json.dumps(statuses, indent=2))


if __name__ == "__main__":
    app()
