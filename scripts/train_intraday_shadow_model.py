from __future__ import annotations

import json

import typer

from app.services.intraday_model_training_service import intraday_model_training_service

app = typer.Typer(help="Build the shadow-only intraday model training report.")


@app.command()
def run() -> None:
    """Generate a stop-loss-aware intraday training report.

    This command reads shadow observations and writes a JSON artifact. It never
    places orders and cannot change live trading flags.
    """

    report = intraday_model_training_service.train_shadow_only()
    typer.echo(json.dumps(report, indent=2, default=str))


@app.command()
def status() -> None:
    report = intraday_model_training_service.status()
    typer.echo(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    app()
