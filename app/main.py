from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.api.routes import (
    alerts,
    brokers,
    dashboard,
    health,
    orders,
    portfolio,
    providers,
    risk,
    shadow,
    system,
    zerodha,
)
from app.core.config import get_settings
from app.core.logging import configure_logging

configure_logging()
settings = get_settings()

app = FastAPI(title=settings.app_name)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard")


app.include_router(health.router)
app.include_router(dashboard.router)
app.include_router(alerts.router)
app.include_router(system.router)
app.include_router(brokers.router)
app.include_router(providers.router)
app.include_router(risk.router)
app.include_router(shadow.router)
app.include_router(orders.router)
app.include_router(portfolio.router)
app.include_router(zerodha.router)
