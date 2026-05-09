"""add shadow training samples

Revision ID: 20260506_0001
Revises:
Create Date: 2026-05-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260506_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shadow_training_samples",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("observation_id", sa.String(length=36), nullable=True),
        sa.Column("strategy_name", sa.String(length=128), nullable=False),
        sa.Column("market", sa.Enum("INDIA", "US", name="shadow_training_sample_market"), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=36), nullable=True),
        sa.Column("signal_id", sa.String(length=36), nullable=True),
        sa.Column("sample_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("current_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("hypothetical_quantity", sa.Integer(), nullable=False),
        sa.Column("hypothetical_notional_inr", sa.Numeric(18, 4), nullable=False),
        sa.Column("hypothetical_pnl_inr", sa.Numeric(18, 4), nullable=False),
        sa.Column("hypothetical_pnl_pct", sa.Numeric(10, 6), nullable=False),
        sa.Column("sample_kind", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.ForeignKeyConstraint(["observation_id"], ["shadow_observations.id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["agent_signals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shadow_training_samples_observation_id", "shadow_training_samples", ["observation_id"])
    op.create_index("ix_shadow_training_samples_sample_at", "shadow_training_samples", ["sample_at"])
    op.create_index("ix_shadow_training_samples_strategy_name", "shadow_training_samples", ["strategy_name"])
    op.create_index("ix_shadow_training_samples_symbol", "shadow_training_samples", ["symbol"])


def downgrade() -> None:
    op.drop_index("ix_shadow_training_samples_symbol", table_name="shadow_training_samples")
    op.drop_index("ix_shadow_training_samples_strategy_name", table_name="shadow_training_samples")
    op.drop_index("ix_shadow_training_samples_sample_at", table_name="shadow_training_samples")
    op.drop_index("ix_shadow_training_samples_observation_id", table_name="shadow_training_samples")
    op.drop_table("shadow_training_samples")
    op.execute("DROP TYPE IF EXISTS shadow_training_sample_market")
