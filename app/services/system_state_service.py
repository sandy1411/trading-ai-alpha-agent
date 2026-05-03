from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import TradingMode
from app.core.errors import RiskRejectedError
from app.db.models.audit import AuditLog
from app.db.models.system_state import SystemState
from app.db.session import SessionLocal
from app.risk.kill_switch import SystemStateSnapshot


class SystemStateService:
    state_key = "global"

    def __init__(
        self,
        settings: Settings | None = None,
        session_factory: Callable[[], Session] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.session_factory = session_factory or SessionLocal

    def get_state(self) -> SystemStateSnapshot:
        try:
            with self.session_factory() as session:
                row = self._get_or_create_row(session)
                session.commit()
                return self._snapshot_from_row(row)
        except SQLAlchemyError:
            return self._database_unavailable_snapshot()

    def enable_kill_switch(self) -> SystemStateSnapshot:
        return self._mutate_state(kill_switch=True, reason="kill_switch_enabled")

    def disable_kill_switch(self) -> SystemStateSnapshot:
        return self._mutate_state(kill_switch=False, reason="kill_switch_disabled")

    def set_mode(self, mode: TradingMode) -> SystemStateSnapshot:
        if mode.is_live_capable and self.settings.live_mode_safety_errors():
            raise RiskRejectedError("live_mode_safety_flags_not_satisfied")
        return self._mutate_state(trading_mode=mode, reason=f"mode_changed:{mode.value}")

    def _mutate_state(
        self,
        *,
        trading_mode: TradingMode | None = None,
        kill_switch: bool | None = None,
        reason: str,
    ) -> SystemStateSnapshot:
        try:
            with self.session_factory() as session:
                row = self._get_or_create_row(session)
                before = self._snapshot_from_row(row)
                if trading_mode is not None:
                    row.trading_mode = trading_mode
                if kill_switch is not None:
                    row.kill_switch = kill_switch
                row.reason = reason
                after = self._snapshot_from_row(row)
                session.add(
                    AuditLog(
                        actor="system_state_service",
                        action=reason,
                        entity_type="system_state",
                        entity_id=row.id,
                        before=asdict(before),
                        after=asdict(after),
                        message="System state changed.",
                    )
                )
                session.commit()
                return after
        except SQLAlchemyError as exc:
            raise RiskRejectedError("system_state_database_unavailable") from exc

    def _get_or_create_row(self, session: Session) -> SystemState:
        row = session.scalar(select(SystemState).where(SystemState.key == self.state_key))
        if row is not None:
            return row
        row = SystemState(
            key=self.state_key,
            trading_mode=self.settings.trading_mode,
            live_trading_enabled=self.settings.live_trading_enabled,
            kill_switch=self.settings.kill_switch,
            reason="initialized_from_environment",
            state={},
        )
        session.add(row)
        session.flush()
        return row

    @staticmethod
    def _snapshot_from_row(row: SystemState) -> SystemStateSnapshot:
        return SystemStateSnapshot(
            trading_mode=row.trading_mode,
            live_trading_enabled=row.live_trading_enabled,
            kill_switch=row.kill_switch,
        )

    def _database_unavailable_snapshot(self) -> SystemStateSnapshot:
        return SystemStateSnapshot(
            trading_mode=self.settings.trading_mode,
            live_trading_enabled=False,
            kill_switch=True,
        )


system_state_service = SystemStateService()
