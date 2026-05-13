from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    AccountStatus,
    AuthStatus,
    ComplianceApprovalStatus,
    FreshnessStatus,
    Market,
    ProviderStatus,
    ProviderType,
    TradingMode,
)
from app.core.time_utils import utc_now
from app.db.base import Base, JSONBType, TimestampMixin


class SystemState(Base, TimestampMixin):
    __tablename__ = "system_state"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    trading_mode: Mapped[TradingMode] = mapped_column(
        SAEnum(TradingMode, name="system_trading_mode"),
        default=TradingMode.SHADOW_LIVE,
    )
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=True)
    reason: Mapped[str] = mapped_column(String(1000), default="")
    state: Mapped[dict] = mapped_column(JSONBType, default=dict)


class ProviderHealthRecord(Base, TimestampMixin):
    __tablename__ = "provider_health"
    __table_args__ = (
        UniqueConstraint("provider_name", "provider_type", "market", name="uq_provider_health"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    provider_name: Mapped[str] = mapped_column(String(128))
    provider_type: Mapped[ProviderType] = mapped_column(SAEnum(ProviderType, name="provider_type"))
    market: Mapped[Market] = mapped_column(SAEnum(Market, name="provider_market"))
    status: Mapped[ProviderStatus] = mapped_column(SAEnum(ProviderStatus, name="provider_status"))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(String(1000), default="")
    freshness_status: Mapped[FreshnessStatus] = mapped_column(
        SAEnum(FreshnessStatus, name="provider_freshness_status"),
        default=FreshnessStatus.MISSING,
    )


class BrokerHealthRecord(Base, TimestampMixin):
    __tablename__ = "broker_health"
    __table_args__ = (UniqueConstraint("broker_name", "market", name="uq_broker_health"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    broker_name: Mapped[str] = mapped_column(String(128))
    market: Mapped[Market] = mapped_column(SAEnum(Market, name="broker_market"))
    auth_status: Mapped[AuthStatus] = mapped_column(SAEnum(AuthStatus, name="auth_status"))
    account_status: Mapped[AccountStatus] = mapped_column(SAEnum(AccountStatus, name="account_status"))
    trading_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    buying_power: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    cash: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    positions_reconciled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ComplianceState(Base, TimestampMixin):
    __tablename__ = "compliance_state"
    __table_args__ = (UniqueConstraint("market", "broker", name="uq_compliance_state"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    market: Mapped[Market] = mapped_column(SAEnum(Market, name="compliance_market"))
    broker: Mapped[str] = mapped_column(String(128), default="")
    algo_compliance_required: Mapped[bool] = mapped_column(Boolean, default=True)
    algo_id: Mapped[str] = mapped_column(String(128), default="")
    strategy_registration_status: Mapped[ComplianceApprovalStatus] = mapped_column(
        SAEnum(ComplianceApprovalStatus, name="strategy_registration_status"),
        default=ComplianceApprovalStatus.NOT_APPROVED,
    )
    broker_approval_status: Mapped[ComplianceApprovalStatus] = mapped_column(
        SAEnum(ComplianceApprovalStatus, name="broker_approval_status"),
        default=ComplianceApprovalStatus.NOT_APPROVED,
    )
    exchange_algo_identifier: Mapped[str] = mapped_column(String(128), default="")
    order_tag: Mapped[str] = mapped_column(String(128), default="")
    unique_order_identifier: Mapped[str] = mapped_column(String(128), default="")
    can_place_live_orders: Mapped[bool] = mapped_column(Boolean, default=False)
    rejection_reasons: Mapped[list] = mapped_column(JSONBType, default=list)
