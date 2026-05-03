from __future__ import annotations

import typer

app = typer.Typer(help="Manual order reconciliation entrypoint.")


@app.command()
def run() -> None:
    typer.echo("Order reconciliation skeleton ready. Configure broker-backed order lookup before use.")


if __name__ == "__main__":
    app()
