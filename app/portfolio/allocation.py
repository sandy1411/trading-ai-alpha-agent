from __future__ import annotations


def allocation_pct(value: float, portfolio_value: float) -> float:
    if portfolio_value <= 0:
        return 0
    return value / portfolio_value
