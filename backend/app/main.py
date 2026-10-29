from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin,
    agents,
    auth,
    catalog,
    listings,
    locations,
    offers,
    orders,
    pricing,
    rfqs,
)
from app.core.config import settings
from app.core.database import init_db

app = FastAPI(
    title="AgriSetuAI",
    version="0.1.0",
    description="AI farming advisory + verified farm-to-marketplace (MVP core).",
)

_dev_origins = [
    f"http://{host}:{port}"
    for host in ("localhost", "127.0.0.1")
    for port in (3000, 3001, 3002)
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_dev_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API = "/api"
for module in (auth, locations, catalog, listings, rfqs, offers, orders, agents, pricing, admin):
    app.include_router(module.router, prefix=API)


@app.on_event("startup")
def _startup() -> None:
    # Dev/SQLite convenience: ensure tables exist. Prod uses migrations.
    init_db()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "dev_mode": settings.dev_mode, "currency": settings.currency}
