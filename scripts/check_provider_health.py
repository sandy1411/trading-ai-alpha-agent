from __future__ import annotations

import json

import typer

from app.services.provider_service import provider_service

app = typer.Typer(help="Check configured provider health.")


@app.callback()
def callback() -> None:
    """Provider health commands."""


@app.command()
def run() -> None:
    statuses = [status.model_dump(mode="json") for status in provider_service.statuses()]
    typer.echo(json.dumps(statuses, indent=2))


if __name__ == "__main__":
    app()
