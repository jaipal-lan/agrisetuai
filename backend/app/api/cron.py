"""External cron entry point.

A free host (Render free tier, etc.) sleeps when idle, so the in-process timer
can't be relied on to refresh market prices on schedule. A free off-box pinger
(GitHub Actions / cron-job.org / UptimeRobot) hits this endpoint on a schedule:
it both wakes the service and runs the due scheduled jobs (price refresh is still
throttled by prices_refresh_hours, so frequent pings don't over-fetch).

Protected by a shared secret (CRON_TOKEN). Disabled (404) until the token is set.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.services.scheduler import run_scheduled_jobs

router = APIRouter(prefix="/cron", tags=["cron"])


def _check_token(token: str) -> None:
    if not settings.cron_token:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cron endpoint is disabled")
    if token != settings.cron_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid cron token")


@router.api_route("/run", methods=["GET", "POST"])
def run_cron(token: str = Query(default=""),
             force_prices: bool = Query(default=False),
             db: Session = Depends(get_db)):
    """Run the scheduled jobs. Pass force_prices=1 (the daily 6 AM job) to pull
    fresh mandi prices even if the throttle window hasn't elapsed."""
    _check_token(token)
    return run_scheduled_jobs(db, force_prices=force_prices)


class PricesPayload(BaseModel):
    records: list[dict]


@router.post("/import-prices")
def import_prices(body: PricesPayload, token: str = Query(default=""),
                  db: Session = Depends(get_db)):
    """Token-protected price import for the India-region auto-importer.

    data.gov.in refuses the backend's datacenter IP (connection refused), so the
    feed is fetched from an Indian IP (a Fly.io Mumbai machine, or any Indian box)
    and the raw AGMARKNET records are POSTed here. Same upsert + stale-sweep as a
    live refresh. Authenticated by CRON_TOKEN (no user login needed)."""
    _check_token(token)
    if not body.records:
        return {"ok": False, "message": "no records provided", "upserted": 0}
    from app.services import prices_feed
    result = prices_feed.refresh_prices(db, records=body.records)
    db.commit()
    return {"ok": True, **result}
