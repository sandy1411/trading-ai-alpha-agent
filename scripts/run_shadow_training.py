from __future__ import annotations

import json
import time
from pathlib import Path

import typer

from app.core.config import get_settings
from app.services.shadow_training_service import shadow_training_service

app = typer.Typer(help="Run safe shadow-training cycles. This never places orders.")
RUNTIME_DIR = Path(".runtime")
LOG_FILE = RUNTIME_DIR / "shadow_training.log"


def _write_log(payload: dict) -> None:
    RUNTIME_DIR.mkdir(exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=str) + "\n")


@app.command()
def once() -> None:
    result = shadow_training_service.run_cycle()
    _write_log(result)
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command()
def loop(interval_seconds: int | None = None) -> None:
    settings = get_settings()
    interval = interval_seconds or settings.shadow_training_interval_seconds
    while True:
        try:
            result = shadow_training_service.run_cycle()
            _write_log(result)
            typer.echo(json.dumps(result, default=str))
        except Exception as exc:
            _write_log({"status": "error", "error": str(exc)})
            typer.echo(f"shadow_training_error={exc}")
        time.sleep(interval)


if __name__ == "__main__":
    app()
