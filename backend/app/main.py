from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin,
    agents,
    auth,
    barcode,
    carriers,
    catalog,
    cron,
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
    team,
    transport,
)
from app.core.config import settings
from app.core.database import run_migrations

app = FastAPI(
    title="KissanSetu",
    version="0.2.0",
    description="Door-to-door farm-to-buyer marketplace: list, agent-verify, pay, deliver.",
)

# Allow the web app from localhost and any private-LAN IP (so a phone/tablet on
# the same Wi-Fi can reach the dev server) on ports 3000-3002.
_origin_regex = (
    r"^https?://("
    r"localhost|127\.0\.0\.1|"
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"192\.168\.\d{1,3}\.\d{1,3}|"
    r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
    r"):(3000|3001|3002|3443)$"
)
# Exact extra origins (the deployed web app, e.g. https://agrisetuai.vercel.app),
# configured via CORS_ORIGINS. The LAN regex above still covers local dev.
_extra_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_extra_origins,
    allow_origin_regex=_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API = "/api"
for module in (
    auth, locations, catalog, listings, rfqs, offers, orders, agents,
    pricing, admin, prices, lots, media, support, logistics,
    carriers, transport, reviews, payments, dashboard, team, barcode, cron,
):
    app.include_router(module.router, prefix=API)


@app.on_event("startup")
def _startup() -> None:
    # Bring the schema to head via Alembic. In production set AUTO_MIGRATE=false
    # and run migrations from the deploy pipeline instead.
    if settings.auto_migrate:
        run_migrations()


@app.on_event("startup")
def _auto_seed() -> None:
    # Seed reference + demo data once on a shell-less host (Render free tier),
    # only when the catalogue is empty. Gated by AUTO_SEED; never crashes startup.
    if not settings.auto_seed:
        return
    import logging

    from sqlalchemy import func, select

    from app.core.database import SessionLocal
    from app.models.catalog import Commodity

    db = SessionLocal()
    try:
        if (db.scalar(select(func.count(Commodity.id))) or 0) == 0:
            from app.seed import main as seed_main
            seed_main()
    except Exception:  # noqa: BLE001 - a seed failure must not break the service
        logging.getLogger("agrisetu.seed").exception("auto-seed failed")
    finally:
        db.close()


@app.on_event("startup")
async def _start_scheduler() -> None:
    # Sandboxed timer that compiles digests + raises due follow-up reminders.
    # No-op unless SCHEDULER_INTERVAL_SECONDS > 0, so tests/plain dev are unaffected.
    from app.services.scheduler import start_background_loop

    start_background_loop()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "dev_mode": settings.dev_mode, "currency": settings.currency}
