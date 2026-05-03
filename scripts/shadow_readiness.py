from __future__ import annotations

import json

import typer

from app.services.shadow_readiness_service import shadow_readiness_service

app = typer.Typer(help="Check whether safe shadow trading is ready.")


@app.callback()
def callback() -> None:
    """Shadow readiness commands."""


@app.command()
def check() -> None:
    typer.echo(json.dumps(shadow_readiness_service.status(), indent=2, default=str))


if __name__ == "__main__":
    app()
