from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.core.enums import Market, ProviderType


class BaseDataProvider(ABC):
    provider_name: str
    provider_type: ProviderType

    @abstractmethod
    def validate_credentials(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def health_check(self, market: Market) -> bool:
        raise NotImplementedError

    @abstractmethod
    def latest(self, symbol: str, market: Market) -> dict[str, Any]:
        raise NotImplementedError
