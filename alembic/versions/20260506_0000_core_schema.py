"""create core trading schema

Revision ID: 20260506_0000
Revises:
Create Date: 2026-05-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260506_0000"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def json_type() -> sa.JSON:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=False),
        sa.Column("before", json_type(), nullable=False),
        sa.Column("after", json_type(), nullable=False),
        sa.Column("context", json_type(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])

    op.create_table(
        "fx_rates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("base_currency", sa.String(length=8), nullable=False),
        sa.Column("quote_currency", sa.String(length=8), nullable=False),
        sa.Column("rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "freshness_status",
            sa.Enum("FRESH", "STALE", "MISSING", name="freshness_status"),
            nullable=False,
        ),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "base_currency", "quote_currency", "source", "observed_at", name="uq_fx_quote"
        ),
    )

    op.create_table(
        "instruments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("market", sa.Enum("INDIA", "US", name="market"), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "asset_class",
            sa.Enum("EQUITY", "ETF", "CASH", name="asset_class"),
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("exchange", sa.String(length=64), nullable=False),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market", "symbol", name="uq_instruments_market_symbol"),
    )
    op.create_index("ix_instruments_market", "instruments", ["market"])
    op.create_index("ix_instruments_symbol", "instruments", ["symbol"])

    op.create_table(
        "macro_observations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("indicator", sa.String(length=128), nullable=False),
        sa.Column("country", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Numeric(18, 6), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("metadata_json", json_type(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_macro_observations_indicator", "macro_observations", ["indicator"])

    op.create_table(
        "market_data_bars",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("market", sa.Enum("INDIA", "US", name="market_data_market"), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("interval", sa.String(length=32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(18, 4), nullable=False),
        sa.Column("high", sa.Numeric(18, 4), nullable=False),
        sa.Column("low", sa.Numeric(18, 4), nullable=False),
        sa.Column("close", sa.Numeric(18, 4), nullable=False),
        sa.Column("volume", sa.Numeric(24, 4), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("metadata_json", json_type(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_market_data_bars_observed_at", "market_data_bars", ["observed_at"])
    op.create_index("ix_market_data_bars_symbol", "market_data_bars", ["symbol"])

    op.create_table(
        "news",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("market", sa.Enum("INDIA", "US", name="news_market"), nullable=True),
        sa.Column("symbol", sa.String(length=64), nullable=True),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("headline", sa.String(length=500), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", json_type(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_news_symbol", "news", ["symbol"])

    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("base_currency", sa.String(length=8), nullable=False),
        sa.Column("total_value_inr", sa.Numeric(18, 4), nullable=False),
        sa.Column("cash_inr", sa.Numeric(18, 4), nullable=False),
        sa.Column("equity_exposure_inr", sa.Numeric(18, 4), nullable=False),
        sa.Column("india_exposure_inr", sa.Numeric(18, 4), nullable=False),
        sa.Column("us_exposure_inr", sa.Numeric(18, 4), nullable=False),
        sa.Column("daily_pnl_inr", sa.Numeric(18, 4), nullable=False),
        sa.Column("weekly_pnl_inr", sa.Numeric(18, 4), nullable=False),
        sa.Column("monthly_drawdown_pct", sa.Numeric(8, 6), nullable=False),
        sa.Column("total_drawdown_pct", sa.Numeric(8, 6), nullable=False),
        sa.Column("positions", json_type(), nullable=False),
        sa.Column("exposures", json_type(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_portfolio_snapshots_snapshot_at", "portfolio_snapshots", ["snapshot_at"])

    op.create_table(
        "risk_config",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("config", json_type(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "risk_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("market", sa.Enum("INDIA", "US", name="risk_event_market"), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=False),
        sa.Column("context", json_type(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_risk_events_event_type", "risk_events", ["event_type"])

    op.create_table(
        "strategies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("allocation_limits", json_type(), nullable=False),
        sa.Column("metadata_json", json_type(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_strategies_name"),
    )

    op.create_table(
        "system_state",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column(
            "trading_mode",
            sa.Enum(
                "BACKTEST_REAL_HISTORICAL_DATA",
                "SHADOW_LIVE_REAL_DATA",
                "MICRO_LIVE_AUTONOMOUS",
                "LIVE_AUTONOMOUS",
                name="system_trading_mode",
            ),
            nullable=False,
        ),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.Column("kill_switch", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("state", json_type(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_system_state_key", "system_state", ["key"], unique=True)

    op.create_table(
        "provider_health",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider_name", sa.String(length=128), nullable=False),
        sa.Column(
            "provider_type",
            sa.Enum("MARKET_DATA", "NEWS", "FX", "BROKER_DATA", name="provider_type"),
            nullable=False,
        ),
        sa.Column("market", sa.Enum("INDIA", "US", name="provider_market"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("OK", "DEGRADED", "DOWN", "MISSING_CREDENTIALS", name="provider_status"),
            nullable=False,
        ),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=False),
        sa.Column(
            "freshness_status",
            sa.Enum("FRESH", "STALE", "MISSING", name="provider_freshness_status"),
            nullable=False,
        ),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_name", "provider_type", "market", name="uq_provider_health"),
    )

    op.create_table(
        "broker_health",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("broker_name", sa.String(length=128), nullable=False),
        sa.Column("market", sa.Enum("INDIA", "US", name="broker_market"), nullable=False),
        sa.Column(
            "auth_status",
            sa.Enum(
                "VALID",
                "INVALID",
                "MISSING_CREDENTIALS",
                "EXPIRED",
                "UNKNOWN",
                name="auth_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "account_status",
            sa.Enum("ACTIVE", "BLOCKED", "DISABLED", "UNKNOWN", name="account_status"),
            nullable=False,
        ),
        sa.Column("trading_enabled", sa.Boolean(), nullable=False),
        sa.Column("buying_power", sa.Numeric(18, 4), nullable=False),
        sa.Column("cash", sa.Numeric(18, 4), nullable=False),
        sa.Column("positions_reconciled", sa.Boolean(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("broker_name", "market", name="uq_broker_health"),
    )

    op.create_table(
        "compliance_state",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("market", sa.Enum("INDIA", "US", name="compliance_market"), nullable=False),
        sa.Column("broker", sa.String(length=128), nullable=False),
        sa.Column("algo_compliance_required", sa.Boolean(), nullable=False),
        sa.Column("algo_id", sa.String(length=128), nullable=False),
        sa.Column(
            "strategy_registration_status",
            sa.Enum(
                "APPROVED",
                "NOT_APPROVED",
                "PENDING",
                "NOT_REQUIRED",
                name="strategy_registration_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "broker_approval_status",
            sa.Enum(
                "APPROVED",
                "NOT_APPROVED",
                "PENDING",
                "NOT_REQUIRED",
                name="broker_approval_status",
            ),
            nullable=False,
        ),
        sa.Column("exchange_algo_identifier", sa.String(length=128), nullable=False),
        sa.Column("order_tag", sa.String(length=128), nullable=False),
        sa.Column("unique_order_identifier", sa.String(length=128), nullable=False),
        sa.Column("can_place_live_orders", sa.Boolean(), nullable=False),
        sa.Column("rejection_reasons", json_type(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market", "broker", name="uq_compliance_state"),
    )

    op.create_table(
        "positions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("instrument_id", sa.String(length=36), nullable=True),
        sa.Column("market", sa.Enum("INDIA", "US", name="position_market"), nullable=False),
        sa.Column(
            "asset_class",
            sa.Enum("EQUITY", "ETF", "CASH", name="position_asset_class"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("average_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("market_value_inr", sa.Numeric(18, 4), nullable=False),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column("broker", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", json_type(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market", "symbol", name="uq_positions_market_symbol"),
    )
    op.create_index("ix_positions_symbol", "positions", ["symbol"])

    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("strategy_id", sa.String(length=36), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("inputs", json_type(), nullable=False),
        sa.Column("metrics", json_type(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "agent_signals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("strategy_id", sa.String(length=36), nullable=True),
        sa.Column("instrument_id", sa.String(length=36), nullable=False),
        sa.Column("market", sa.Enum("INDIA", "US", name="signal_market"), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column(
            "asset_class",
            sa.Enum("EQUITY", "ETF", "CASH", name="signal_asset_class"),
            nullable=False,
        ),
        sa.Column(
            "action",
            sa.Enum("BUY", "SELL", "HOLD", "NO_TRADE", name="trade_action"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Numeric(6, 5), nullable=False),
        sa.Column("strategy_name", sa.String(length=128), nullable=False),
        sa.Column("payload", json_type(), nullable=False),
        sa.Column("data_sources", json_type(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_signals_symbol", "agent_signals", ["symbol"])

    op.create_table(
        "risk_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("signal_id", sa.String(length=36), nullable=True),
        sa.Column(
            "decision",
            sa.Enum("APPROVED", "REDUCE_SIZE", "REJECTED", "NO_TRADE", name="risk_decision_type"),
            nullable=False,
        ),
        sa.Column("approved_quantity", sa.Integer(), nullable=False),
        sa.Column("approved_capital", sa.Numeric(18, 4), nullable=False),
        sa.Column("approved_risk", sa.Numeric(18, 4), nullable=False),
        sa.Column("rejection_reasons", json_type(), nullable=False),
        sa.Column("required_actions", json_type(), nullable=False),
        sa.Column("risk_metrics", json_type(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["signal_id"], ["agent_signals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_risk_decisions_decision", "risk_decisions", ["decision"])

    op.create_table(
        "order_idempotency_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("order_record_id", sa.String(length=36), nullable=True),
        sa.Column("broker_order_id", sa.String(length=128), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "CREATED",
                "SUBMITTED",
                "ACCEPTED",
                "PARTIALLY_FILLED",
                "FILLED",
                "CANCELLED",
                "REJECTED",
                "UNKNOWN_REQUIRES_RECONCILIATION",
                name="idempotency_order_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "reconciliation_state",
            sa.Enum(
                "NOT_REQUIRED",
                "REQUIRED",
                "RECONCILED",
                "BLOCKING_DUPLICATES",
                name="idempotency_reconciliation_state",
            ),
            nullable=False,
        ),
        sa.Column("blocks_duplicates", sa.Boolean(), nullable=False),
        sa.Column("payload", json_type(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_order_idempotency_keys_key"),
    )
    op.create_index("ix_order_idempotency_keys_broker_order_id", "order_idempotency_keys", ["broker_order_id"])
    op.create_index("ix_order_idempotency_keys_idempotency_key", "order_idempotency_keys", ["idempotency_key"])
    op.create_index("ix_order_idempotency_keys_status", "order_idempotency_keys", ["status"])

    op.create_table(
        "orders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("broker_order_id", sa.String(length=128), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("market", sa.Enum("INDIA", "US", name="order_market"), nullable=False),
        sa.Column("broker", sa.Enum("ZERODHA", "ALPACA", name="broker_name"), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("side", sa.Enum("BUY", "SELL", name="order_side"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("order_type", sa.Enum("MARKET", "LIMIT", name="order_type"), nullable=False),
        sa.Column("limit_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("stop_loss", sa.Numeric(18, 4), nullable=True),
        sa.Column("strategy_id", sa.String(length=36), nullable=True),
        sa.Column("signal_id", sa.String(length=36), nullable=True),
        sa.Column("risk_decision_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "CREATED",
                "SUBMITTED",
                "ACCEPTED",
                "PARTIALLY_FILLED",
                "FILLED",
                "CANCELLED",
                "REJECTED",
                "UNKNOWN_REQUIRES_RECONCILIATION",
                name="order_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "reconciliation_state",
            sa.Enum(
                "NOT_REQUIRED",
                "REQUIRED",
                "RECONCILED",
                "BLOCKING_DUPLICATES",
                name="reconciliation_state",
            ),
            nullable=False,
        ),
        sa.Column("broker_response", json_type(), nullable=False),
        sa.Column("final_reconciliation", json_type(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["risk_decision_id"], ["risk_decisions.id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["agent_signals.id"]),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_orders_idempotency_key"),
    )
    op.create_index("ix_orders_broker_order_id", "orders", ["broker_order_id"])
    op.create_index("ix_orders_idempotency_key", "orders", ["idempotency_key"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_symbol", "orders", ["symbol"])

    op.create_table(
        "shadow_observations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("strategy_name", sa.String(length=128), nullable=False),
        sa.Column("market", sa.Enum("INDIA", "US", name="shadow_observation_market"), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=36), nullable=True),
        sa.Column("signal_id", sa.String(length=36), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_marked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("current_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("hypothetical_quantity", sa.Integer(), nullable=False),
        sa.Column("hypothetical_notional_inr", sa.Numeric(18, 4), nullable=False),
        sa.Column("hypothetical_pnl_inr", sa.Numeric(18, 4), nullable=False),
        sa.Column("hypothetical_pnl_pct", sa.Numeric(10, 6), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("notes", json_type(), nullable=False),
        sa.Column("metadata_json", json_type(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["agent_signals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shadow_observations_last_marked_at", "shadow_observations", ["last_marked_at"])
    op.create_index("ix_shadow_observations_opened_at", "shadow_observations", ["opened_at"])
    op.create_index("ix_shadow_observations_status", "shadow_observations", ["status"])
    op.create_index("ix_shadow_observations_strategy_name", "shadow_observations", ["strategy_name"])
    op.create_index("ix_shadow_observations_symbol", "shadow_observations", ["symbol"])

    op.create_table(
        "daily_market_review_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("market", sa.Enum("INDIA", "US", name="daily_review_market"), nullable=False),
        sa.Column("review_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("signals", sa.Integer(), nullable=False),
        sa.Column("shadow_hypotheses", sa.Integer(), nullable=False),
        sa.Column("real_orders", sa.Integer(), nullable=False),
        sa.Column("buy_hypotheses", sa.Integer(), nullable=False),
        sa.Column("no_trade_signals", sa.Integer(), nullable=False),
        sa.Column("winners", sa.Integer(), nullable=False),
        sa.Column("losers", sa.Integer(), nullable=False),
        sa.Column("flat", sa.Integer(), nullable=False),
        sa.Column("hypothetical_notional_inr", sa.Numeric(18, 4), nullable=False),
        sa.Column("hypothetical_pnl_inr", sa.Numeric(18, 4), nullable=False),
        sa.Column("hypothetical_pnl_pct", sa.Numeric(10, 6), nullable=False),
        sa.Column("payload", json_type(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market", "review_date", name="uq_daily_market_review_market_date"),
    )
    op.create_index("ix_daily_market_review_snapshots_market", "daily_market_review_snapshots", ["market"])
    op.create_index(
        "ix_daily_market_review_snapshots_review_date",
        "daily_market_review_snapshots",
        ["review_date"],
    )


def downgrade() -> None:
    op.drop_table("daily_market_review_snapshots")
    op.drop_table("shadow_observations")
    op.drop_table("orders")
    op.drop_table("order_idempotency_keys")
    op.drop_table("risk_decisions")
    op.drop_table("agent_signals")
    op.drop_table("backtest_runs")
    op.drop_table("positions")
    op.drop_table("compliance_state")
    op.drop_table("broker_health")
    op.drop_table("provider_health")
    op.drop_table("system_state")
    op.drop_table("strategies")
    op.drop_table("risk_events")
    op.drop_table("risk_config")
    op.drop_table("portfolio_snapshots")
    op.drop_table("news")
    op.drop_table("market_data_bars")
    op.drop_table("macro_observations")
    op.drop_table("instruments")
    op.drop_table("fx_rates")
    op.drop_table("audit_logs")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for enum_type in (
            "daily_review_market",
            "shadow_observation_market",
            "order_status",
            "reconciliation_state",
            "order_type",
            "order_side",
            "broker_name",
            "order_market",
            "idempotency_reconciliation_state",
            "idempotency_order_status",
            "risk_decision_type",
            "trade_action",
            "signal_asset_class",
            "signal_market",
            "position_asset_class",
            "position_market",
            "broker_approval_status",
            "strategy_registration_status",
            "compliance_market",
            "account_status",
            "auth_status",
            "broker_market",
            "provider_freshness_status",
            "provider_status",
            "provider_market",
            "provider_type",
            "system_trading_mode",
            "risk_event_market",
            "news_market",
            "market_data_market",
            "asset_class",
            "market",
            "freshness_status",
        ):
            op.execute(sa.text(f"DROP TYPE IF EXISTS {enum_type}"))
