from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.core.enums import AccountStatus, AuthStatus, Market
from app.schemas.common import StrictSchema


class BrokerHealth(StrictSchema):
    broker_name: str
    market: Market
    auth_status: AuthStatus = AuthStatus.UNKNOWN
    account_status: AccountStatus = AccountStatus.UNKNOWN
    trading_enabled: bool = False
    buying_power: float = Field(default=0, ge=0)
    cash: float = Field(default=0, ge=0)
    positions_reconciled: bool = False
    last_checked_at: datetime
    rejection_reasons: list[str] = Field(default_factory=list)

    @property
    def is_healthy_for_live(self) -> bool:
        return (
            self.auth_status == AuthStatus.VALID
            and self.account_status == AccountStatus.ACTIVE
            and self.trading_enabled
            and self.positions_reconciled
        )
