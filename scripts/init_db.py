from __future__ import annotations

import typer
from sqlalchemy import text

from app.core.enums import TradingMode
from app.db.base import Base
from app.db.session import engine

app = typer.Typer(help="Initialize local database objects for development.")


@app.callback()
def callback() -> None:
    """Database initialization commands."""


@app.command()
def create_all() -> None:
    Base.metadata.create_all(bind=engine)
    sync_postgres_enums()
    typer.echo("Database tables created from SQLAlchemy metadata.")


def sync_postgres_enums() -> None:
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as connection:
        for mode in TradingMode:
            connection.execute(
                text(f"ALTER TYPE system_trading_mode ADD VALUE IF NOT EXISTS '{mode.value}'")
            )


if __name__ == "__main__":
    app()
