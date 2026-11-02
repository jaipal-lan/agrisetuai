from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin,
    advisory,
    agents,
    auth,
    carriers,
    catalog,
    insights,
    listings,
    locations,
    logistics,
    lots,
    media,
    offers,
    orders,
    pricing,
    rfqs,
    subscriptions,
    support,
    transport,
)
from app.core.config import settings
from app.core.database import run_migrations

app = FastAPI(
    title="AgriSetuAI",
    version="0.1.0",
    description="AI farming advisory + verified farm-to-marketplace (MVP core).",
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
    pricing, admin, advisory, insights, lots, media, support, logistics,
    subscriptions, carriers, transport,
):
    app.include_router(module.router, prefix=API)


@app.on_event("startup")
def _startup() -> None:
    # Bring the schema to head via Alembic. In production set AUTO_MIGRATE=false
    # and run migrations from the deploy pipeline instead.
    if settings.auto_migrate:
        run_migrations()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "dev_mode": settings.dev_mode, "currency": settings.currency}
