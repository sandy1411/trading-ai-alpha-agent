from __future__ import annotations

import json
import time
from pathlib import Path

import typer

from app.core.config import get_settings
from app.services.market_intelligence_service import market_intelligence_service

app = typer.Typer(help="Run shadow-only market intelligence agents. This never places orders.")
RUNTIME_DIR = Path(".runtime")
LOG_FILE = RUNTIME_DIR / "market_intelligence.log"


def _write_log(payload: dict) -> None:
    RUNTIME_DIR.mkdir(exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=str) + "\n")


@app.command()
def once() -> None:
    result = market_intelligence_service.summary()
    _write_log(result)
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command()
def loop(interval_seconds: int | None = None) -> None:
    settings = get_settings()
    interval = interval_seconds or settings.shadow_training_interval_seconds
    while True:
        try:
            result = market_intelligence_service.summary()
            _write_log(result)
            typer.echo(json.dumps(result, default=str))
        except Exception as exc:
            error = {"status": "error", "error": str(exc), "orders_placed": 0}
            _write_log(error)
            typer.echo(f"market_intelligence_error={exc}")
        time.sleep(interval)


if __name__ == "__main__":
    app()
