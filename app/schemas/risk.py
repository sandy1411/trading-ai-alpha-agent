from __future__ import annotations

from pydantic import Field

from app.core.config import Settings
from app.core.enums import ComplianceApprovalStatus, Market, MarketCalendarState, RiskDecisionType
from app.schemas.common import StrictSchema, new_id


class RiskConfig(StrictSchema):
    max_risk_per_trade_pct: float = Field(default=0.005, gt=0, le=0.05)
    max_daily_loss_pct: float = Field(default=0.0125, gt=0, le=0.2)
    max_weekly_loss_pct: float = Field(default=0.04, gt=0, le=0.5)
    max_monthly_drawdown_pct: float = Field(default=0.08, gt=0, le=0.7)
    max_total_drawdown_pct: float = Field(default=0.10, gt=0, le=0.8)
    max_single_stock_position_pct: float = Field(default=0.075, gt=0, le=1)
    max_single_etf_position_pct: float = Field(default=0.15, gt=0, le=1)
    max_sector_exposure_pct: float = Field(default=0.25, gt=0, le=1)
    max_total_equity_exposure_pct: float = Field(default=0.80, gt=0, le=1)
    max_india_exposure_pct: float = Field(default=0.70, gt=0, le=1)
    max_us_exposure_pct: float = Field(default=0.70, gt=0, le=1)
    max_open_positions_total: int = Field(default=15, ge=1)
    max_open_positions_india: int = Field(default=8, ge=1)
    max_open_positions_us: int = Field(default=8, ge=1)
    min_reward_risk_ratio: float = Field(default=1.0, ge=0)
    max_slippage_pct: float = Field(default=0.0025, ge=0, le=0.05)

    @classmethod
    def from_settings(cls, settings: Settings) -> "RiskConfig":
        return cls(
            max_risk_per_trade_pct=settings.max_risk_per_trade_pct,
            max_daily_loss_pct=settings.max_daily_loss_pct,
            max_weekly_loss_pct=settings.max_weekly_loss_pct,
            max_monthly_drawdown_pct=settings.max_monthly_drawdown_pct,
            max_total_drawdown_pct=settings.max_total_drawdown_pct,
            max_single_stock_position_pct=settings.max_single_stock_position_pct,
            max_single_etf_position_pct=settings.max_single_etf_position_pct,
            max_sector_exposure_pct=settings.max_sector_exposure_pct,
            max_total_equity_exposure_pct=settings.max_total_equity_exposure_pct,
            max_india_exposure_pct=settings.max_india_exposure_pct,
            max_us_exposure_pct=settings.max_us_exposure_pct,
            max_open_positions_total=settings.max_open_positions_total,
            max_open_positions_india=settings.max_open_positions_india,
            max_open_positions_us=settings.max_open_positions_us,
        )


class RiskDecision(StrictSchema):
    id: str = Field(default_factory=new_id)
    signal_id: str | None = None
    decision: RiskDecisionType
    approved_quantity: int = Field(default=0, ge=0)
    approved_capital: float = Field(default=0, ge=0)
    approved_risk: float = Field(default=0, ge=0)
    rejection_reasons: list[str] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)
    risk_metrics: dict[str, float | int | str | bool] = Field(default_factory=dict)

    @property
    def is_approved_for_execution(self) -> bool:
        return self.decision in {RiskDecisionType.APPROVED, RiskDecisionType.REDUCE_SIZE}


class MarketCalendarStatus(StrictSchema):
    market: Market
    state: MarketCalendarState
    reason: str = ""

    @property
    def is_open(self) -> bool:
        return self.state == MarketCalendarState.OPEN


class ComplianceStatus(StrictSchema):
    market: Market
    broker: str = ""
    algo_compliance_required: bool = True
    algo_id: str = ""
    strategy_registration_status: ComplianceApprovalStatus = ComplianceApprovalStatus.NOT_APPROVED
    broker_approval_status: ComplianceApprovalStatus = ComplianceApprovalStatus.NOT_APPROVED
    exchange_algo_identifier: str = ""
    order_tag: str = ""
    unique_order_identifier: str = ""
    can_place_live_orders: bool = False
    rejection_reasons: list[str] = Field(default_factory=list)

    @property
    def approved(self) -> bool:
        if not self.algo_compliance_required:
            return self.can_place_live_orders
        return (
            self.strategy_registration_status == ComplianceApprovalStatus.APPROVED
            and self.broker_approval_status == ComplianceApprovalStatus.APPROVED
            and bool(self.exchange_algo_identifier)
            and self.can_place_live_orders
        )
