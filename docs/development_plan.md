# Development Plan

## Phase 0

Repository structure, configuration, logging, enums, errors, security masking, Docker assets, and tests.

## Phase 1

PostgreSQL schema, SQLAlchemy models, Alembic setup, Pydantic contracts, system state, audit service, kill switch storage path, and risk config.

## Phase 2 Safe Skeleton

Broker interfaces, real Zerodha and Alpaca adapter skeletons, provider health, broker session checks, idempotency, order lifecycle, reconciliation, and fail-closed execution guardrails.

## Next Step

Generate the first Alembic migration, add durable system-state/idempotency persistence, then test broker/provider health against real credentials in shadow-live only.
