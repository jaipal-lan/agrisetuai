"""Sandboxed background jobs that make proactive alerts actually proactive.

Two jobs, both safe to run repeatedly (idempotent):

  compile_digests     — for each user who has batched ("digest") alerts waiting,
                        "send" a single daily-digest summary notification and
                        advance their watermark so the same alerts aren't
                        summarised twice. In production the summary would also go
                        out by email/SMS; here it lands in the in-app bell.
  raise_due_followups — raise reminders for every agent's advisory follow-ups
                        that have come due, without the agent having to open the
                        app first.

run_scheduled_jobs() runs both and returns a small report. The jobs can be
triggered on demand (POST /api/admin/scheduler/run) or by the in-process loop
(enabled with SCHEDULER_INTERVAL_SECONDS > 0).
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.advisory import AdvisoryLog
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


def raise_due_followups(db: Session) -> int:
    """Raise due advisory follow-up reminders for every agent. Returns the total
    number of reminders raised this run."""
    # Lazy import avoids a service<-api import cycle at module load.
    from app.api.agents import raise_due_followup_reminders

    agent_ids = set(db.scalars(
        select(AdvisoryLog.agent_id).where(
            AdvisoryLog.follow_up_done.is_(False),
            AdvisoryLog.follow_up_notified.is_(False),
            AdvisoryLog.follow_up_on.is_not(None),
        )
    ))
    total = 0
    for agent_id in agent_ids:
        total += raise_due_followup_reminders(db, agent_id)
    return total


def run_scheduled_jobs(db: Session) -> dict:
    """Run every scheduled job once and return a report."""
    from app.models.common import utcnow
    reminders = raise_due_followups(db)
    digests = compile_digests(db)
    return {"ran_at": utcnow().isoformat(), "reminders_raised": reminders, "digests_sent": digests}


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
            if result["digests_sent"] or result["reminders_raised"]:
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
