from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import pytest

from app.core.config import Settings
from app.core.enums import TradingMode
from app.core.errors import RiskRejectedError
from app.db.base import Base
from app.services.system_state_service import SystemStateService


def test_kill_switch_state_is_persisted() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    settings = Settings(_env_file=None)

    first_service = SystemStateService(settings=settings, session_factory=session_factory)
    assert first_service.get_state().kill_switch is True
    first_service.disable_kill_switch()

    second_service = SystemStateService(settings=settings, session_factory=session_factory)
    assert second_service.get_state().kill_switch is False


def test_live_mode_update_is_blocked_until_safety_flags_are_satisfied() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    service = SystemStateService(
        settings=Settings(_env_file=None),
        session_factory=session_factory,
    )

    with pytest.raises(RiskRejectedError, match="live_mode_safety_flags_not_satisfied"):
        service.set_mode(TradingMode.LIVE_AUTONOMOUS)
