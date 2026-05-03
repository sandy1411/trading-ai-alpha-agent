from __future__ import annotations

import typer

from app.db.base import Base
from app.db.session import engine

app = typer.Typer(help="Initialize local database objects for development.")


@app.callback()
def callback() -> None:
    """Database initialization commands."""


@app.command()
def create_all() -> None:
    Base.metadata.create_all(bind=engine)
    typer.echo("Database tables created from SQLAlchemy metadata.")


if __name__ == "__main__":
    app()
