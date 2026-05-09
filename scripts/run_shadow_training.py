from __future__ import annotations

import json
import os
import time
from pathlib import Path
from types import TracebackType

import typer

from app.core.config import get_settings
from app.services.shadow_training_service import shadow_training_service

app = typer.Typer(help="Run safe shadow-training cycles. This never places orders.")
RUNTIME_DIR = Path(".runtime")
LOG_FILE = RUNTIME_DIR / "shadow_training.log"
LOOP_LOCK_FILE = RUNTIME_DIR / "shadow_training.loop.lock"


class SingleLoopLock:
    """Best-effort cross-platform process lock for the long-running shadow loop."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self) -> "SingleLoopLock":
        RUNTIME_DIR.mkdir(exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        try:
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            self.handle = None
            typer.echo("another_shadow_training_loop_is_already_running")
            raise typer.Exit(code=75) from exc

        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(str(os.getpid()))
        self.handle.flush()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


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
    with SingleLoopLock(LOOP_LOCK_FILE):
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
