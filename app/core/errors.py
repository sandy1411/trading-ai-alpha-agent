from __future__ import annotations


class TradingAlphaError(Exception):
    """Base exception for platform errors."""


class FailClosedError(TradingAlphaError):
    """Raised when a safety dependency is unavailable or inconclusive."""


class MissingCredentialsError(FailClosedError):
    """Raised when a real provider or broker credential is absent."""


class RiskRejectedError(FailClosedError):
    """Raised when deterministic risk controls reject an action."""


class OrderIdempotencyError(FailClosedError):
    """Raised when an order would violate idempotency constraints."""
