from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostBreakdown:
    brokerage: float
    stt: float
    exchange_charges: float
    gst: float
    stamp_duty: float
    sebi_charges: float
    slippage_cost: float

    @property
    def total(self) -> float:
        return (
            self.brokerage
            + self.stt
            + self.exchange_charges
            + self.gst
            + self.stamp_duty
            + self.sebi_charges
            + self.slippage_cost
        )

    def model_dump(self) -> dict[str, float]:
        return {
            "brokerage": self.brokerage,
            "stt": self.stt,
            "exchange_charges": self.exchange_charges,
            "gst": self.gst,
            "stamp_duty": self.stamp_duty,
            "sebi_charges": self.sebi_charges,
            "slippage_cost": self.slippage_cost,
            "total": self.total,
        }


class CostModel:
    """India equity intraday approximation for shadow reporting."""

    def calculate(
        self,
        *,
        buy_value: float,
        sell_value: float,
        slippage_cost: float = 0.0,
    ) -> CostBreakdown:
        turnover = buy_value + sell_value
        brokerage = min(20.0, 0.0003 * buy_value) + min(20.0, 0.0003 * sell_value)
        stt = 0.00025 * sell_value
        exchange_charges = 0.0000325 * turnover
        sebi_charges = 0.000001 * turnover
        stamp_duty = 0.00003 * buy_value
        gst = 0.18 * (brokerage + exchange_charges + sebi_charges)
        return CostBreakdown(
            brokerage=round(brokerage, 4),
            stt=round(stt, 4),
            exchange_charges=round(exchange_charges, 4),
            gst=round(gst, 4),
            stamp_duty=round(stamp_duty, 4),
            sebi_charges=round(sebi_charges, 4),
            slippage_cost=round(slippage_cost, 4),
        )

