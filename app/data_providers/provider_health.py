from __future__ import annotations

from app.core.enums import FreshnessStatus, Market, ProviderStatus
from app.core.errors import MissingCredentialsError, TradingAlphaError
from app.core.time_utils import utc_now
from app.data_providers.base import BaseDataProvider
from app.schemas.provider import ProviderHealth


class ProviderHealthChecker:
    def check(self, provider: BaseDataProvider, market: Market) -> ProviderHealth:
        try:
            provider.validate_credentials()
            ok = provider.health_check(market)
            return ProviderHealth(
                provider_name=provider.provider_name,
                provider_type=provider.provider_type,
                market=market,
                status=ProviderStatus.OK if ok else ProviderStatus.DEGRADED,
                last_success_at=utc_now() if ok else None,
                freshness_status=FreshnessStatus.FRESH if ok else FreshnessStatus.STALE,
            )
        except MissingCredentialsError:
            return ProviderHealth(
                provider_name=provider.provider_name,
                provider_type=provider.provider_type,
                market=market,
                status=ProviderStatus.MISSING_CREDENTIALS,
                last_error="provider_credentials_missing",
                freshness_status=FreshnessStatus.MISSING,
            )
        except TradingAlphaError as exc:
            return ProviderHealth(
                provider_name=provider.provider_name,
                provider_type=provider.provider_type,
                market=market,
                status=ProviderStatus.DOWN,
                last_error=str(exc),
                freshness_status=FreshnessStatus.MISSING,
            )
        except Exception as exc:
            return ProviderHealth(
                provider_name=provider.provider_name,
                provider_type=provider.provider_type,
                market=market,
                status=ProviderStatus.DOWN,
                last_error=f"provider_health_exception:{type(exc).__name__}",
                freshness_status=FreshnessStatus.MISSING,
            )
