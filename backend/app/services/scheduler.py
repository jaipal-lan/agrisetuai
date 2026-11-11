"""Sandboxed background job: compile daily notification digests.

compile_digests — for each user who has batched ("digest") alerts waiting, "send"
a single daily-digest summary notification and advance their watermark so the
same alerts aren't summarised twice.

run_scheduled_jobs() runs it and returns a small report. Triggered on demand
(POST /api/admin/scheduler/run) or by the in-process loop
(enabled with SCHEDULER_INTERVAL_SECONDS > 0).
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.support import Notification
from app.models.user import User
from app.services import notify

log = logging.getLogger("agrisetu.scheduler")


def compile_digests(db: Session) -> int:
    """Send a daily-digest summary to each user with newly-batched alerts.

    Only alerts newer than the user's watermark are counted, so a repeat run (or
    a user who hasn't opened /digest yet) is never double-notified. Returns the
    number of digest summaries sent."""
    from app.services.notify import MUTEABLE_CATEGORIES, category_for

    labels = dict(MUTEABLE_CATEGORIES)
    rows = db.scalars(
        select(Notification).where(
            Notification.deferred.is_(True),
            Notification.read_at.is_(None),
        )
    )
    by_user: dict[int, list[Notification]] = {}
    for n in rows:
        by_user.setdefault(n.user_id, []).append(n)

    sent = 0
    for user_id, notes in by_user.items():
        user = db.get(User, user_id)
        if user is None:
            continue
        watermark = user.last_digest_id or 0
        fresh = [n for n in notes if n.id > watermark]
        if not fresh:
            continue
        counts: dict[str, int] = {}
        for n in fresh:
            cat = category_for(n.object_type) or "other"
            counts[cat] = counts.get(cat, 0) + 1
        parts = ", ".join(
            f"{labels.get(c, 'Other updates')} ({k})" for c, k in counts.items()
        )
        plural = "s" if len(fresh) != 1 else ""
        notify.send(
            db, user_id=user_id,
            title="📬 Your daily digest",
            body=f"You have {len(fresh)} batched update{plural}: {parts}. Open your digest to review.",
            object_type="digest",
        )
        user.last_digest_id = max(n.id for n in fresh)
        sent += 1
    if sent:
        db.commit()
    return sent


def refresh_market_prices(db: Session) -> int:
    """Refresh live mandi prices if the feed is configured AND due (throttled by
    prices_refresh_hours); no-op otherwise. Never raises (a transient upstream
    failure must not break the job run)."""
    from app.services import prices_feed

    if not prices_feed.is_refresh_due(db):
        return 0
    try:
        result = prices_feed.refresh_prices(db)
        db.commit()
        return result.get("upserted", 0)
    except Exception:
        db.rollback()
        log.exception("price feed refresh failed")
        return 0


def raise_meeting_reminders(db: Session) -> int:
    """Notify attendees + organiser of each scheduled meeting starting within the
    reminder window (meeting_reminder_hours) that hasn't been reminded yet. Each
    meeting is reminded once. Returns the number of meetings reminded."""
    from datetime import datetime, timedelta, timezone

    from app.core.config import settings
    from app.models.team import TeamMeeting

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=settings.meeting_reminder_hours)
    sent = 0
    for m in db.scalars(select(TeamMeeting).where(
        TeamMeeting.status == "scheduled", TeamMeeting.reminded.is_(False)
    )):
        try:
            when = datetime.fromisoformat(m.scheduled_at)
        except (TypeError, ValueError):
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when < now or when > horizon:
            continue  # already past, or still further out than the window
        pretty = m.scheduled_at.replace("T", " ")[:16]
        recipients = set(m.attendee_ids or []) | {m.organizer_id}
        for uid in recipients:
            notify.send(db, user_id=uid, title="Meeting reminder",
                        body=f"Upcoming: {m.title} — {pretty}"
                             + (f" at {m.location}" if m.location else ""),
                        object_type="meeting", object_id=m.id)
        m.reminded = True
        sent += 1
    if sent:
        db.commit()
    return sent


def run_scheduled_jobs(db: Session) -> dict:
    """Run every scheduled job once and return a report."""
    from app.models.common import utcnow
    digests = compile_digests(db)
    prices = refresh_market_prices(db)
    meeting_reminders = raise_meeting_reminders(db)
    return {"ran_at": utcnow().isoformat(), "digests_sent": digests,
            "prices_refreshed": prices, "meeting_reminders": meeting_reminders}


async def _loop(interval: int) -> None:
    from app.core.database import SessionLocal

    def _once() -> dict:
        db = SessionLocal()
        try:
            return run_scheduled_jobs(db)
        finally:
            db.close()

    log.info("digest scheduler started (every %ss)", interval)
    while True:
        await asyncio.sleep(interval)
        try:
            result = await asyncio.to_thread(_once)
            if any((result["digests_sent"], result["prices_refreshed"], result["meeting_reminders"])):
                log.info("scheduler: %s", result)
        except Exception:  # never let the loop die on a transient error
            log.exception("scheduled job run failed")


def start_background_loop() -> asyncio.Task | None:
    """Start the in-process timer if SCHEDULER_INTERVAL_SECONDS > 0, else no-op."""
    from app.core.config import settings

    interval = settings.scheduler_interval_seconds
    if interval and interval > 0:
        return asyncio.create_task(_loop(interval))
    return None
