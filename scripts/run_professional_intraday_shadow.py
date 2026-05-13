from __future__ import annotations

import json
import os
import time
from pathlib import Path
from types import TracebackType

import typer

from app.core.enums import Market, MarketCalendarState
from app.risk.market_calendar import MarketCalendar
from app.services.professional_intraday_shadow_service import professional_intraday_shadow_service

app = typer.Typer(help="Run the professional intraday shadow pipeline. This never places orders.")
RUNTIME_DIR = Path(".runtime")
LOG_FILE = RUNTIME_DIR / "professional_intraday_shadow.log"
LOOP_LOCK_FILE = RUNTIME_DIR / "professional_intraday_shadow.loop.lock"


class SingleLoopLock:
    """Best-effort cross-platform process lock for the long-running professional loop."""

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
            typer.echo("another_professional_intraday_shadow_loop_is_already_running")
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


def _symbols(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [symbol.strip().upper() for symbol in raw.split(",") if symbol.strip()]


def _run_once(symbols: list[str] | None = None) -> dict:
    calendar = MarketCalendar().status(Market.INDIA)
    if calendar.state != MarketCalendarState.OPEN:
        return {
            "status": "MARKET_CLOSED",
            "market": Market.INDIA.value,
            "calendar_reason": calendar.reason,
            "orders_placed": 0,
            "shadow_only": True,
        }
    return professional_intraday_shadow_service.run_india_once(symbols=symbols)


@app.command()
def once(symbols: str = "") -> None:
    result = _run_once(_symbols(symbols))
    _write_log(result)
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command()
def loop(interval_seconds: int = 180, symbols: str = "") -> None:
    selected_symbols = _symbols(symbols)
    with SingleLoopLock(LOOP_LOCK_FILE):
        while True:
            try:
                result = _run_once(selected_symbols)
                _write_log(result)
                typer.echo(json.dumps(result, default=str))
            except Exception as exc:
                payload = {
                    "status": "ERROR",
                    "error": str(exc),
                    "orders_placed": 0,
                    "shadow_only": True,
                }
                _write_log(payload)
                typer.echo(f"professional_intraday_shadow_error={exc}")
            time.sleep(interval_seconds)


if __name__ == "__main__":
    app()
