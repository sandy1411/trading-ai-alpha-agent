"""extend system trading mode enum

Revision ID: 20260513_0000
Revises: 20260506_0001
Create Date: 2026-05-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "20260513_0000"
down_revision: str | Sequence[str] | None = "20260506_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for value in ("BACKTEST", "MARKET_REPLAY", "SHADOW_LIVE", "PAPER_TRADING", "LIVE_DISABLED"):
        op.execute(f"ALTER TYPE system_trading_mode ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely without rebuilding dependent columns.
    pass
