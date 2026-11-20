"""External cron entry point.

A free host (Render free tier, etc.) sleeps when idle, so the in-process timer
can't be relied on to refresh market prices on schedule. A free off-box pinger
(GitHub Actions / cron-job.org / UptimeRobot) hits this endpoint on a schedule:
it both wakes the service and runs the due scheduled jobs (price refresh is still
throttled by prices_refresh_hours, so frequent pings don't over-fetch).

Protected by a shared secret (CRON_TOKEN). Disabled (404) until the token is set.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.services.scheduler import run_scheduled_jobs

router = APIRouter(prefix="/cron", tags=["cron"])


@router.api_route("/run", methods=["GET", "POST"])
def run_cron(token: str = Query(default=""), db: Session = Depends(get_db)):
    if not settings.cron_token:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cron endpoint is disabled")
    if token != settings.cron_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid cron token")
    return run_scheduled_jobs(db)
