from __future__ import annotations

import typer

from app.services.system_state_service import system_state_service

app = typer.Typer(help="Emergency controls.")


@app.command()
def on() -> None:
    state = system_state_service.enable_kill_switch()
    typer.echo(f"KILL_SWITCH={str(state.kill_switch).lower()}")


if __name__ == "__main__":
    app()
