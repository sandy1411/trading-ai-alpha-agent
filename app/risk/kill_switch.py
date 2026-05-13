from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.core.enums import TradingMode


@dataclass(slots=True)
class SystemStateSnapshot:
    trading_mode: TradingMode = TradingMode.SHADOW_LIVE
    live_trading_enabled: bool = False
    kill_switch: bool = True
    compliance_status: str = "NOT_APPROVED"

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "SystemStateSnapshot":
        resolved = settings or get_settings()
        return cls(
            trading_mode=resolved.trading_mode,
            live_trading_enabled=resolved.live_trading_enabled,
            kill_switch=resolved.kill_switch,
        )


class KillSwitch:
    def __init__(self, state: SystemStateSnapshot | None = None) -> None:
        self.state = state or SystemStateSnapshot()

    def is_enabled(self) -> bool:
        return self.state.kill_switch

    def enable(self) -> SystemStateSnapshot:
        self.state.kill_switch = True
        return self.state

    def disable(self) -> SystemStateSnapshot:
        self.state.kill_switch = False
        return self.state
