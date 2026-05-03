from __future__ import annotations

from app.brokers.base import BaseBroker
from app.core.errors import FailClosedError


class BrokerSessionValidator:
    def require_valid_session(self, broker: BaseBroker) -> None:
        if not broker.validate_credentials():
            raise FailClosedError("broker_credentials_invalid")
        if not broker.check_session():
            raise FailClosedError("broker_session_invalid")
