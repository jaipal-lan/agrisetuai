from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin,
    agents,
    auth,
    carriers,
    catalog,
    dashboard,
    listings,
    locations,
    logistics,
    lots,
    media,
    offers,
    orders,
    payments,
    prices,
    pricing,
    reviews,
    rfqs,
    support,
    transport,
)
from app.core.config import settings
from app.core.database import run_migrations

app = FastAPI(
    title="AgriSetuAI",
    version="0.2.0",
    description="Door-to-door farm-to-buyer marketplace: list, agent-verify, pay, deliver.",
)

# Allow the web app from localhost and any private-LAN IP (so a phone/tablet on
# the same Wi-Fi can reach the dev server) on ports 3000-3002.
_origin_regex = (
    r"^http://("
    r"localhost|127\.0\.0\.1|"
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"192\.168\.\d{1,3}\.\d{1,3}|"
    r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
    r"):(3000|3001|3002)$"
)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API = "/api"
for module in (
    auth, locations, catalog, listings, rfqs, offers, orders, agents,
    pricing, admin, prices, lots, media, support, logistics,
    carriers, transport, reviews, payments, dashboard,
):
    app.include_router(module.router, prefix=API)


@app.on_event("startup")
def _startup() -> None:
    # Bring the schema to head via Alembic. In production set AUTO_MIGRATE=false
    # and run migrations from the deploy pipeline instead.
    if settings.auto_migrate:
        run_migrations()


@app.on_event("startup")
async def _start_scheduler() -> None:
    # Sandboxed timer that compiles digests + raises due follow-up reminders.
    # No-op unless SCHEDULER_INTERVAL_SECONDS > 0, so tests/plain dev are unaffected.
    from app.services.scheduler import start_background_loop

    start_background_loop()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "dev_mode": settings.dev_mode, "currency": settings.currency}
