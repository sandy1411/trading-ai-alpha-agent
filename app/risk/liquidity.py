from __future__ import annotations

from app.schemas.signal import TradeCandidate


def liquidity_rejection_reason(candidate: TradeCandidate) -> str | None:
    if "illiquid" in {flag.lower() for flag in candidate.risk_flags}:
        return "liquidity_check_failed"
    return None
