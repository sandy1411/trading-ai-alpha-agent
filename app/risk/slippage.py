from __future__ import annotations

from app.schemas.signal import TradeCandidate


def slippage_rejection_reason(candidate: TradeCandidate) -> str | None:
    if "high_slippage" in {flag.lower() for flag in candidate.risk_flags}:
        return "slippage_check_failed"
    return None
