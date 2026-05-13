from __future__ import annotations

from datetime import UTC, date, datetime
from statistics import mean


class DailyReviewEngine:
    def generate(self, rows: list[dict], *, report_date: date | None = None) -> dict:
        day = report_date or datetime.now(UTC).date()
        signals = [row for row in rows if row.get("event_type") in {"SIGNAL_ACCEPTED", "SIGNAL_REJECTED"}]
        accepted = [row for row in rows if row.get("event_type") == "SIGNAL_ACCEPTED"]
        rejected = [row for row in rows if row.get("event_type") == "SIGNAL_REJECTED"]
        exits = [row for row in rows if row.get("event_type") == "POSITION_EXITED"]
        net_pnls = [float(row.get("net_pnl") or 0) for row in exits]
        gross_pnls = [float(row.get("gross_pnl") or 0) for row in exits]
        charges = [float(row.get("charges") or 0) for row in exits]
        wins = [pnl for pnl in net_pnls if pnl > 0]
        losses = [abs(pnl) for pnl in net_pnls if pnl < 0]
        win_rate = len(wins) / len(net_pnls) if net_pnls else 0.0
        loss_rate = 1 - win_rate if net_pnls else 0.0
        avg_win = mean(wins) if wins else 0.0
        avg_loss = mean(losses) if losses else 0.0
        gross_profit = sum(wins)
        gross_loss = sum(losses)
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit else 0)
        expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
        drawdown = self._max_drawdown(net_pnls)
        best_trade = max(exits, key=lambda row: float(row.get("net_pnl") or 0), default=None)
        worst_trade = min(exits, key=lambda row: float(row.get("net_pnl") or 0), default=None)
        return {
            "report_date": day.isoformat(),
            "total_signals_generated": len(signals),
            "signals_accepted": len(accepted),
            "signals_rejected": len(rejected),
            "trades_taken": len(exits),
            "win_rate": win_rate,
            "average_win": avg_win,
            "average_loss": avg_loss,
            "profit_factor": profit_factor,
            "expectancy": expectancy,
            "gross_pnl": sum(gross_pnls),
            "net_pnl": sum(net_pnls),
            "total_charges": sum(charges),
            "max_drawdown": drawdown,
            "long_pnl": self._pnl_by_direction(exits, "LONG"),
            "short_pnl": self._pnl_by_direction(exits, "SHORT"),
            "strategy_wise_pnl": self._group_pnl(exits, "strategy"),
            "regime_wise_pnl": self._group_pnl(exits, "regime"),
            "time_of_day_pnl": {},
            "symbol_wise_pnl": self._group_pnl(exits, "symbol"),
            "biggest_mistake": worst_trade.get("exit_reason") if worst_trade else None,
            "best_trade": best_trade,
            "worst_trade": worst_trade,
        }

    @staticmethod
    def _pnl_by_direction(rows: list[dict], direction: str) -> float:
        return sum(float(row.get("net_pnl") or 0) for row in rows if row.get("direction") == direction)

    @staticmethod
    def _group_pnl(rows: list[dict], key: str) -> dict[str, float]:
        grouped: dict[str, float] = {}
        for row in rows:
            value = str(row.get(key) or "UNKNOWN")
            grouped[value] = grouped.get(value, 0.0) + float(row.get("net_pnl") or 0)
        return grouped

    @staticmethod
    def _max_drawdown(pnls: list[float]) -> float:
        peak = 0.0
        equity = 0.0
        max_drawdown = 0.0
        for pnl in pnls:
            equity += pnl
            peak = max(peak, equity)
            max_drawdown = min(max_drawdown, equity - peak)
        return abs(max_drawdown)

