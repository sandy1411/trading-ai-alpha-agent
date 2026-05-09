from __future__ import annotations

from app.brokers.base import BaseBroker
from app.core.enums import AccountStatus, AuthStatus, Market
from app.core.errors import MissingCredentialsError, TradingAlphaError
from app.core.time_utils import utc_now
from app.schemas.broker import BrokerHealth


class BrokerHealthChecker:
    def check(self, broker: BaseBroker, market: Market) -> BrokerHealth:
        try:
            broker.validate_credentials()
            session_valid = broker.check_session()
            account = broker.get_account()
            reconciled = broker.reconcile_positions()
            rejection_reasons: list[str] = []
            if not session_valid:
                rejection_reasons.append("broker_session_invalid")
            if account.status.upper() != "ACTIVE":
                rejection_reasons.append("broker_account_not_active")
            if not account.trading_enabled:
                rejection_reasons.append("broker_trading_disabled")
            if not reconciled:
                rejection_reasons.append("portfolio_reconciliation_required")
            return BrokerHealth(
                broker_name=broker.broker_name,
                market=market,
                auth_status=AuthStatus.VALID if session_valid else AuthStatus.EXPIRED,
                account_status=(
                    AccountStatus.ACTIVE if account.status.upper() == "ACTIVE" else AccountStatus.UNKNOWN
                ),
                trading_enabled=account.trading_enabled,
                buying_power=account.buying_power,
                cash=account.cash,
                positions_reconciled=reconciled,
                last_checked_at=utc_now(),
                rejection_reasons=rejection_reasons,
            )
        except MissingCredentialsError:
            return BrokerHealth(
                broker_name=broker.broker_name,
                market=market,
                auth_status=AuthStatus.MISSING_CREDENTIALS,
                account_status=AccountStatus.UNKNOWN,
                trading_enabled=False,
                buying_power=0,
                cash=0,
                positions_reconciled=False,
                last_checked_at=utc_now(),
                rejection_reasons=["broker_credentials_missing"],
            )
        except TradingAlphaError as exc:
            return BrokerHealth(
                broker_name=broker.broker_name,
                market=market,
                auth_status=AuthStatus.INVALID,
                account_status=AccountStatus.UNKNOWN,
                trading_enabled=False,
                buying_power=0,
                cash=0,
                positions_reconciled=False,
                last_checked_at=utc_now(),
                rejection_reasons=[str(exc)],
            )
        except Exception as exc:
            return BrokerHealth(
                broker_name=broker.broker_name,
                market=market,
                auth_status=AuthStatus.INVALID,
                account_status=AccountStatus.UNKNOWN,
                trading_enabled=False,
                buying_power=0,
                cash=0,
                positions_reconciled=False,
                last_checked_at=utc_now(),
                rejection_reasons=[f"broker_health_exception:{type(exc).__name__}"],
            )
