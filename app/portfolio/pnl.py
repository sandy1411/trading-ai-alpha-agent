from __future__ import annotations


def pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0
    return (current - previous) / previous
