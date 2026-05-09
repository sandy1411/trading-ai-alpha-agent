from __future__ import annotations

import json
from math import floor
from typing import Any

import typer
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models.audit import AuditLog
from app.db.models.shadow import ShadowObservation
from app.db.session import SessionLocal

app = typer.Typer(help="Rescale open shadow observations. This never places orders.")


@app.command()
def run() -> None:
    settings = get_settings()
    with SessionLocal() as session:
        observations = session.scalars(
            select(ShadowObservation).where(ShadowObservation.status == "OPEN_OBSERVATION")
        ).all()
        changed = 0
        rows: list[dict[str, Any]] = []
        for observation in observations:
            metadata = observation.metadata_json or {}
            fx_rate = float(metadata.get("usd_inr") or 1.0)
            entry_price = float(observation.entry_price or 0)
            current_price = float(observation.current_price or 0)
            price_inr = entry_price * fx_rate
            quantity = floor(settings.shadow_hypothesis_notional_inr / price_inr) if price_inr > 0 else 0
            notional = quantity * entry_price * fx_rate
            pnl = (current_price - entry_price) * quantity * fx_rate
            pnl_pct = pnl / notional if notional else 0.0
            if (
                int(observation.hypothetical_quantity or 0) != quantity
                or float(observation.hypothetical_notional_inr or 0) != notional
            ):
                changed += 1
            observation.hypothetical_quantity = quantity
            observation.hypothetical_notional_inr = notional
            observation.hypothetical_pnl_inr = pnl
            observation.hypothetical_pnl_pct = pnl_pct
            observation.metadata_json = {
                **metadata,
                "shadow_notional_per_symbol_inr": settings.shadow_hypothesis_notional_inr,
                "sizing_policy": "whole_share_shadow_budget",
                "rescaled_shadow_book": True,
            }
            rows.append(
                {
                    "market": observation.market.value,
                    "symbol": observation.symbol,
                    "quantity": quantity,
                    "notional_inr": notional,
                    "pnl_inr": pnl,
                }
            )
        session.add(
            AuditLog(
                actor="rescale_shadow_book_script",
                action="shadow_book_rescaled",
                entity_type="shadow_observation",
                message=(
                    "Open shadow observations rescaled to configured per-symbol "
                    "hypothesis notional. No orders were placed."
                ),
                context={
                    "shadow_hypothesis_notional_inr": settings.shadow_hypothesis_notional_inr,
                    "observations": len(observations),
                    "changed": changed,
                },
            )
        )
        session.commit()
        typer.echo(
            json.dumps(
                {
                    "status": "completed",
                    "shadow_hypothesis_notional_inr": settings.shadow_hypothesis_notional_inr,
                    "observations": len(observations),
                    "changed": changed,
                    "orders_placed": 0,
                    "rows": rows,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    app()
