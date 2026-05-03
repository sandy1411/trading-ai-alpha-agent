from __future__ import annotations

import pytest

from app.brokers.broker_session import BrokerSessionValidator
from app.core.errors import FailClosedError, MissingCredentialsError


class SessionBrokerStub:
    broker_name = "SESSION"

    def __init__(self, credentials: bool, session: bool) -> None:
        self.credentials = credentials
        self.session = session

    def validate_credentials(self) -> bool:
        if not self.credentials:
            raise MissingCredentialsError("missing")
        return True

    def check_session(self) -> bool:
        return self.session


def test_broker_session_validator_blocks_expired_session() -> None:
    validator = BrokerSessionValidator()

    with pytest.raises(FailClosedError, match="broker_session_invalid"):
        validator.require_valid_session(SessionBrokerStub(credentials=True, session=False))
