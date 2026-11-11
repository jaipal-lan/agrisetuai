"""Field leader / manager console: monitor field agents and the verification
pipeline, pass (assign) orders to agents, set targets for agents, and schedule /
record team meetings. A field leader runs a mandal's agents; a field manager
oversees leaders across a district."""
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.rbac import Role
from app.models.catalog import Commodity
from app.models.common import OrderStatus as S
from app.models.location import Mandal
from app.models.order import Inspection, Order
from app.models.team import TARGET_METRICS, AgentTarget, TeamMeeting
from app.models.user import User
from app.services import notify

router = APIRouter(prefix="/team", tags=["team"])

_lead = require_roles(Role.FIELD_LEADER, Role.FIELD_MANAGER, Role.SUPERADMIN)
_agent = require_roles(Role.FIELD_AGENT, Role.FIELD_LEADER, Role.FIELD_MANAGER, Role.SUPERADMIN)

_INSPECTION_STATES = (S.INSPECTION_ASSIGNED, S.INSPECTION_IN_PROGRESS, S.INSPECTION_HOLD)
_ACTIVE = (S.CONFIRMED, S.PAYMENT_PENDING, S.PAID, S.PACKING, S.READY_FOR_PICKUP,
           S.PICKED_UP, S.IN_TRANSIT, S.OUT_FOR_DELIVERY)

_METRIC_LABEL = {"inspections": "inspections", "orders_assigned": "orders handled"}


@router.get("/overview")
def overview(user=Depends(_lead), db: Session = Depends(get_db)):
    """Agents with their workload, and the orders currently needing verification."""
    names = {u.id: (u.name or f"user {u.id}") for u in db.scalars(select(User))}

    # Field agents + how many inspections each has done / has open now.
    agents = []
    for a in db.scalars(select(User).where(User.role == str(Role.FIELD_AGENT))):
        done = db.scalar(select(func.count(Inspection.id)).where(Inspection.agent_id == a.id)) or 0
        open_jobs = db.scalar(select(func.count(Order.id)).where(
            Order.assigned_agent_id == a.id, Order.status.in_(_INSPECTION_STATES))) or 0
        agents.append({"id": a.id, "name": a.name, "inspections_done": done, "open_jobs": open_jobs})
    agents.sort(key=lambda x: (-x["open_jobs"], x["name"] or ""))

    # Orders in the inspection stage (assigned or waiting to be assigned).
    pipeline = []
    for o in db.scalars(select(Order).where(Order.status.in_(_INSPECTION_STATES))
                        .order_by(Order.created_at)):
        t = o.accepted_terms or {}
        c = db.get(Commodity, t.get("commodity_id")) if t.get("commodity_id") else None
        pipeline.append({
            "order_id": o.id, "public_id": o.public_id, "status": o.status,
            "commodity": c.name if c else None,
            "quantity": t.get("quantity"), "unit": t.get("unit", "kg"),
            "assigned_agent_id": o.assigned_agent_id,
            "assigned_agent_name": names.get(o.assigned_agent_id) if o.assigned_agent_id else None,
        })

    active_orders = db.scalar(select(func.count(Order.id)).where(Order.status.in_(_ACTIVE))) or 0
    return {
        "agents": agents,
        "pipeline": pipeline,
        "unassigned": sum(1 for p in pipeline if not p["assigned_agent_id"]),
        "active_orders": active_orders,
    }


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

def _window(period_start: str, period_end: str) -> tuple[datetime, datetime]:
    """[start 00:00, end+1day 00:00) in UTC from inclusive ISO dates."""
    start = datetime.combine(date.fromisoformat(period_start), time.min, tzinfo=timezone.utc)
    end = datetime.combine(date.fromisoformat(period_end) + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return start, end


def _progress(db: Session, t: AgentTarget) -> int:
    """Live count of the agent's work for the target's metric within its window."""
    try:
        start, end = _window(t.period_start, t.period_end)
    except ValueError:
        return 0
    if t.metric == "orders_assigned":
        stmt = select(func.count(Order.id)).where(
            Order.assigned_agent_id == t.agent_id,
            Order.created_at >= start, Order.created_at < end)
    else:  # "inspections" (default)
        stmt = select(func.count(Inspection.id)).where(
            Inspection.agent_id == t.agent_id,
            Inspection.created_at >= start, Inspection.created_at < end)
    return db.scalar(stmt) or 0


def _target_json(db: Session, t: AgentTarget, names: dict[int, str]) -> dict:
    done = _progress(db, t)
    goal = t.target_value or 0
    pct = round(min(100, done / goal * 100)) if goal else 0
    return {
        "id": t.id, "agent_id": t.agent_id, "agent_name": names.get(t.agent_id),
        "set_by_id": t.set_by_id, "set_by_name": names.get(t.set_by_id),
        "metric": t.metric, "metric_label": _METRIC_LABEL.get(t.metric, t.metric),
        "target_value": goal, "progress": done, "pct": pct, "met": goal and done >= goal,
        "period_start": t.period_start, "period_end": t.period_end,
        "note": t.note, "status": t.status,
    }


class TargetCreate(BaseModel):
    agent_id: int
    metric: str = "inspections"
    target_value: int
    period_start: str
    period_end: str
    note: str | None = None


class TargetUpdate(BaseModel):
    target_value: int | None = None
    period_start: str | None = None
    period_end: str | None = None
    note: str | None = None
    status: str | None = None


@router.get("/targets")
def list_targets(status: str = "active", user=Depends(_lead), db: Session = Depends(get_db)):
    """All targets (with live progress). ``status=all`` includes archived."""
    names = {u.id: (u.name or f"user {u.id}") for u in db.scalars(select(User))}
    stmt = select(AgentTarget).order_by(AgentTarget.status, AgentTarget.period_end.desc())
    if status != "all":
        stmt = stmt.where(AgentTarget.status == status)
    return [_target_json(db, t, names) for t in db.scalars(stmt)]


@router.post("/targets")
def create_target(body: TargetCreate, user=Depends(_lead), db: Session = Depends(get_db)):
    if body.metric not in TARGET_METRICS:
        raise HTTPException(400, f"Unknown metric. Choose one of {', '.join(TARGET_METRICS)}.")
    if body.target_value <= 0:
        raise HTTPException(400, "Target value must be positive.")
    try:
        _window(body.period_start, body.period_end)
    except ValueError:
        raise HTTPException(400, "period_start / period_end must be ISO dates (YYYY-MM-DD).")
    agent = db.get(User, body.agent_id)
    if agent is None or agent.role != str(Role.FIELD_AGENT):
        raise HTTPException(404, "Field agent not found.")
    t = AgentTarget(agent_id=body.agent_id, set_by_id=user.id, metric=body.metric,
                    target_value=body.target_value, period_start=body.period_start,
                    period_end=body.period_end, note=body.note, status="active")
    db.add(t)
    db.flush()
    notify.send(db, user_id=body.agent_id, title="New target set",
                body=f"{user.name or 'Your leader'} set a target: {body.target_value} "
                     f"{_METRIC_LABEL.get(body.metric, body.metric)} by {body.period_end}.",
                object_type="target", object_id=t.id)
    db.commit()
    names = {u.id: (u.name or f"user {u.id}") for u in db.scalars(select(User))}
    return _target_json(db, t, names)


@router.patch("/targets/{target_id}")
def update_target(target_id: int, body: TargetUpdate, user=Depends(_lead), db: Session = Depends(get_db)):
    t = db.get(AgentTarget, target_id)
    if t is None:
        raise HTTPException(404, "Target not found.")
    if body.target_value is not None:
        if body.target_value <= 0:
            raise HTTPException(400, "Target value must be positive.")
        t.target_value = body.target_value
    if body.period_start is not None:
        t.period_start = body.period_start
    if body.period_end is not None:
        t.period_end = body.period_end
    if body.status is not None:
        if body.status not in ("active", "archived"):
            raise HTTPException(400, "status must be active or archived.")
        t.status = body.status
    if body.note is not None:
        t.note = body.note
    try:
        _window(t.period_start, t.period_end)
    except ValueError:
        raise HTTPException(400, "period dates must be ISO dates (YYYY-MM-DD).")
    db.commit()
    names = {u.id: (u.name or f"user {u.id}") for u in db.scalars(select(User))}
    return _target_json(db, t, names)


@router.delete("/targets/{target_id}")
def delete_target(target_id: int, user=Depends(_lead), db: Session = Depends(get_db)):
    t = db.get(AgentTarget, target_id)
    if t is None:
        raise HTTPException(404, "Target not found.")
    db.delete(t)
    db.commit()
    return {"deleted": target_id}


@router.get("/my-targets")
def my_targets(user=Depends(_agent), db: Session = Depends(get_db)):
    """An agent's own active targets with live progress."""
    names = {u.id: (u.name or f"user {u.id}") for u in db.scalars(select(User))}
    rows = db.scalars(select(AgentTarget).where(
        AgentTarget.agent_id == user.id, AgentTarget.status == "active")
        .order_by(AgentTarget.period_end))
    return [_target_json(db, t, names) for t in rows]


# ---------------------------------------------------------------------------
# Meetings
# ---------------------------------------------------------------------------

def _meeting_json(m: TeamMeeting, names: dict[int, str], mandals: dict[int, str]) -> dict:
    ids = m.attendee_ids or []
    return {
        "id": m.id, "title": m.title, "scheduled_at": m.scheduled_at,
        "location": m.location, "agenda": m.agenda, "status": m.status,
        "notes": m.notes,
        "organizer_id": m.organizer_id, "organizer_name": names.get(m.organizer_id),
        "mandal_id": m.mandal_id, "mandal": mandals.get(m.mandal_id) if m.mandal_id else None,
        "attendee_ids": ids,
        "attendees": [{"id": i, "name": names.get(i)} for i in ids],
        "attended_ids": m.attended_ids or [],
        "attendee_count": len(ids),
    }


class MeetingCreate(BaseModel):
    title: str
    scheduled_at: str
    location: str | None = None
    agenda: str | None = None
    attendee_ids: list[int] | None = None
    mandal_id: int | None = None


class MeetingUpdate(BaseModel):
    title: str | None = None
    scheduled_at: str | None = None
    location: str | None = None
    agenda: str | None = None
    attendee_ids: list[int] | None = None
    attended_ids: list[int] | None = None
    notes: str | None = None
    status: str | None = None


def _names(db: Session) -> dict[int, str]:
    return {u.id: (u.name or f"user {u.id}") for u in db.scalars(select(User))}


def _mandal_names(db: Session) -> dict[int, str]:
    return {m.id: m.name for m in db.scalars(select(Mandal))}


@router.get("/meetings")
def list_meetings(status: str = "all", user=Depends(_lead), db: Session = Depends(get_db)):
    names, mandals = _names(db), _mandal_names(db)
    stmt = select(TeamMeeting).order_by(TeamMeeting.scheduled_at.desc())
    if status != "all":
        stmt = stmt.where(TeamMeeting.status == status)
    return [_meeting_json(m, names, mandals) for m in db.scalars(stmt)]


@router.post("/meetings")
def create_meeting(body: MeetingCreate, user=Depends(_lead), db: Session = Depends(get_db)):
    if not body.title.strip():
        raise HTTPException(400, "Title is required.")
    if not body.scheduled_at.strip():
        raise HTTPException(400, "Scheduled time is required.")
    m = TeamMeeting(organizer_id=user.id, title=body.title.strip(),
                    scheduled_at=body.scheduled_at.strip(), location=body.location,
                    agenda=body.agenda, attendee_ids=body.attendee_ids or [],
                    mandal_id=body.mandal_id, status="scheduled")
    db.add(m)
    db.flush()
    when = body.scheduled_at.strip()[:16].replace("T", " ")
    for aid in (body.attendee_ids or []):
        notify.send(db, user_id=aid, title="Team meeting scheduled",
                    body=f"{body.title.strip()} — {when}"
                         + (f" at {body.location}" if body.location else ""),
                    object_type="meeting", object_id=m.id)
    db.commit()
    return _meeting_json(m, _names(db), _mandal_names(db))


@router.patch("/meetings/{meeting_id}")
def update_meeting(meeting_id: int, body: MeetingUpdate, user=Depends(_lead), db: Session = Depends(get_db)):
    m = db.get(TeamMeeting, meeting_id)
    if m is None:
        raise HTTPException(404, "Meeting not found.")
    prev_attendees = set(m.attendee_ids or [])
    if body.title is not None:
        m.title = body.title.strip()
    if body.scheduled_at is not None:
        m.scheduled_at = body.scheduled_at.strip()
    if body.location is not None:
        m.location = body.location
    if body.agenda is not None:
        m.agenda = body.agenda
    if body.attendee_ids is not None:
        m.attendee_ids = body.attendee_ids
    if body.attended_ids is not None:
        m.attended_ids = body.attended_ids
    if body.notes is not None:
        m.notes = body.notes
    if body.status is not None:
        if body.status not in ("scheduled", "done", "cancelled"):
            raise HTTPException(400, "status must be scheduled, done or cancelled.")
        m.status = body.status
    db.flush()
    # Notify any newly-added attendees of a (re)scheduled meeting.
    if body.attendee_ids is not None and m.status == "scheduled":
        when = (m.scheduled_at or "")[:16].replace("T", " ")
        for aid in set(body.attendee_ids) - prev_attendees:
            notify.send(db, user_id=aid, title="Team meeting scheduled",
                        body=f"{m.title} — {when}", object_type="meeting", object_id=m.id)
    db.commit()
    return _meeting_json(m, _names(db), _mandal_names(db))


@router.delete("/meetings/{meeting_id}")
def delete_meeting(meeting_id: int, user=Depends(_lead), db: Session = Depends(get_db)):
    m = db.get(TeamMeeting, meeting_id)
    if m is None:
        raise HTTPException(404, "Meeting not found.")
    db.delete(m)
    db.commit()
    return {"deleted": meeting_id}


@router.get("/my-meetings")
def my_meetings(user=Depends(_agent), db: Session = Depends(get_db)):
    """Upcoming/recent meetings an agent is invited to (or organises)."""
    names, mandals = _names(db), _mandal_names(db)
    out = []
    for m in db.scalars(select(TeamMeeting).where(TeamMeeting.status != "cancelled")
                        .order_by(TeamMeeting.scheduled_at.desc())):
        if user.id in (m.attendee_ids or []) or m.organizer_id == user.id:
            out.append(_meeting_json(m, names, mandals))
    return out
