from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.money import qty
from app.core.rbac import Role
from app.models.advisory import AdvisoryLog
from app.models.common import InspectionOutcome
from app.models.common import OrderStatus as S
from app.models.order import Inspection, Order
from app.models.user import User
from app.services import audit, notify
from app.services.state_machine import InvalidTransition, transition

router = APIRouter(prefix="/agent", tags=["agent"])

_agent = require_roles(Role.FIELD_AGENT, Role.MANDAL_MANAGER, Role.SUPERADMIN)


def _safe(db, order, to, **kw):
    try:
        transition(db, order, to, **kw)
    except InvalidTransition as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))


@router.get("/jobs")
def jobs(user=Depends(_agent), db: Session = Depends(get_db)):
    """Orders assigned to this agent that need inspection or packing."""
    rows = db.scalars(
        select(Order).where(
            Order.assigned_agent_id == user.id,
            Order.status.in_([
                S.INSPECTION_ASSIGNED, S.INSPECTION_IN_PROGRESS,
                S.INSPECTION_HOLD, S.PAID, S.PACKING,
            ]),
        )
    )
    return [
        {
            "order_id": o.id,
            "public_id": o.public_id,
            "status": o.status,
            "accepted_terms": o.accepted_terms,
            "buyer_id": o.buyer_id,
            "seller_id": o.seller_id,
        }
        for o in rows
    ]


class InspectionSubmit(BaseModel):
    client_draft_id: str | None = None
    gross_weight: float | None = None
    tare_weight: float | None = None
    scale_ref: str | None = None
    checklist: dict | None = None
    measurements: dict | None = None
    evidence: list[str] | None = None  # media refs
    outcome: InspectionOutcome
    reason_codes: dict | None = None


@router.post("/orders/{order_id}/inspection")
def submit_inspection(
    order_id: int, body: InspectionSubmit, user=Depends(_agent), db: Session = Depends(get_db)
):
    """Record inspection evidence + decision. Drives the order state machine.

    Offline-first safe: a repeated client_draft_id returns the existing record
    instead of creating a duplicate (PRD 6.1 / QA checklist).
    """
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    if order.assigned_agent_id not in (user.id, None) and user.role == Role.FIELD_AGENT:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your assigned job")

    # Offline-first dedupe runs BEFORE the state guard: a re-synced draft must
    # return the existing record even after the order has already advanced.
    if body.client_draft_id:
        dup = db.scalar(select(Inspection).where(Inspection.client_draft_id == body.client_draft_id))
        if dup:
            return {"inspection_id": dup.id, "outcome": dup.outcome, "order_status": order.status,
                    "duplicate": True}

    if order.status not in (S.INSPECTION_ASSIGNED, S.INSPECTION_IN_PROGRESS, S.INSPECTION_HOLD):
        raise HTTPException(status.HTTP_409_CONFLICT, "Order not in an inspectable state")

    net = None
    if body.gross_weight is not None:
        net = qty(body.gross_weight) - qty(body.tare_weight or 0)

    insp = Inspection(
        order_id=order.id,
        agent_id=user.id,
        declared_qty=qty(order.accepted_terms.get("quantity", 0)),
        gross_weight=qty(body.gross_weight) if body.gross_weight is not None else None,
        tare_weight=qty(body.tare_weight) if body.tare_weight is not None else None,
        net_qty=net,
        scale_ref=body.scale_ref,
        checklist=body.checklist,
        measurements=body.measurements,
        evidence={"refs": body.evidence or []},
        outcome=str(body.outcome),
        reason_codes=body.reason_codes,
        client_draft_id=body.client_draft_id,
    )
    db.add(insp)

    # Move INSPECTION_ASSIGNED -> IN_PROGRESS first if needed.
    if order.status == S.INSPECTION_ASSIGNED:
        _safe(db, order, S.INSPECTION_IN_PROGRESS, actor_id=user.id, reason_code="inspection_started")

    outcome_state = {
        InspectionOutcome.PASS: S.INSPECTION_PASS,
        InspectionOutcome.PASS_WITH_ADJUSTMENT: S.INSPECTION_PASS,
        InspectionOutcome.HOLD: S.INSPECTION_HOLD,
        InspectionOutcome.FAIL: S.INSPECTION_FAIL,
    }[body.outcome]

    if order.status == S.INSPECTION_IN_PROGRESS:
        _safe(db, order, outcome_state, actor_id=user.id, reason_code=f"inspection_{body.outcome}")

    # Quantity adjustment is proposed, never silently written into accepted terms.
    if body.outcome == InspectionOutcome.PASS_WITH_ADJUSTMENT and net is not None:
        proposed = dict(order.accepted_terms or {})
        proposed["proposed_quantity"] = str(net)
        proposed["adjustment_pending"] = True
        order.accepted_terms = proposed

    # A pass advances automatically to buyer approval (PRD 5 state chain).
    if outcome_state == S.INSPECTION_PASS and order.status == S.INSPECTION_PASS:
        _safe(db, order, S.BUYER_APPROVAL_PENDING, actor_id=user.id, reason_code="awaiting_buyer")

    audit.record(db, actor_id=user.id, action="inspection.decision", object_type="order",
                 object_id=order.public_id, new_values={"outcome": str(body.outcome), "net_qty": str(net) if net else None})
    db.commit()
    db.refresh(order)
    return {"inspection_id": insp.id, "outcome": insp.outcome, "order_status": order.status}


# --- Agent-as-expert advisory log ----------------------------------------

class AdvisoryLogCreate(BaseModel):
    client_draft_id: str | None = None
    farmer_phone: str | None = None
    listing_id: int | None = None
    crop: str | None = None
    topic: str = "advisory"  # advisory | education | follow_up
    observation: str | None = None
    recommendation: str | None = None
    follow_up_on: str | None = None


def _log_json(l: AdvisoryLog) -> dict:
    return {
        "id": l.id,
        "agent_id": l.agent_id,
        "farmer_id": l.farmer_id,
        "listing_id": l.listing_id,
        "crop": l.crop,
        "topic": l.topic,
        "observation": l.observation,
        "recommendation": l.recommendation,
        "follow_up_on": l.follow_up_on,
        "follow_up_done": l.follow_up_done,
        "created_at": l.created_at.isoformat() if l.created_at else None,
    }


@router.post("/advisory-logs", status_code=status.HTTP_201_CREATED)
def create_advisory_log(body: AdvisoryLogCreate, user=Depends(_agent), db: Session = Depends(get_db)):
    """Field agent records advisory / farmer-education notes from a visit.

    Offline-first safe: a repeated client_draft_id returns the existing record
    instead of creating a duplicate, so a draft captured in the field and synced
    later (or twice) never double-logs.
    """
    if body.client_draft_id:
        dup = db.scalar(select(AdvisoryLog).where(AdvisoryLog.client_draft_id == body.client_draft_id))
        if dup:
            return {**_log_json(dup), "duplicate": True}
    farmer_id = None
    if body.farmer_phone:
        farmer = db.scalar(select(User).where(User.phone == body.farmer_phone))
        farmer_id = farmer.id if farmer else None
    log = AdvisoryLog(
        agent_id=user.id, farmer_id=farmer_id, listing_id=body.listing_id, crop=body.crop,
        topic=body.topic, observation=body.observation, recommendation=body.recommendation,
        follow_up_on=body.follow_up_on, client_draft_id=body.client_draft_id,
    )
    db.add(log)
    db.flush()
    # Close the loop: the farmer sees advice logged about them (respects their
    # notification preferences via the 'advisory' category).
    if farmer_id:
        crop_txt = f" on {body.crop}" if body.crop else ""
        notify.send(
            db, user_id=farmer_id,
            title="New advice from your field agent",
            body=(body.recommendation or body.observation or "Your agent logged a visit.") + crop_txt,
            object_type="advisory_log", object_id=log.id,
        )
    db.commit()
    db.refresh(log)
    return _log_json(log)


@router.get("/advisory-logs")
def list_advisory_logs(user=Depends(_agent), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(AdvisoryLog).where(AdvisoryLog.agent_id == user.id)
        .order_by(AdvisoryLog.id.desc()).limit(100)
    )
    return [_log_json(l) for l in rows]


# --- Follow-up reminders -------------------------------------------------------

def _parse_follow_date(s: str | None) -> date | None:
    """Parse a follow_up_on value (e.g. '2026-11-20') to a date, or None if it
    isn't a plain ISO date — the field is free text, so be defensive."""
    if not s or len(s) < 10:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _open_followups(db: Session, agent_id: int):
    """Advisory logs with an unresolved, parseable follow-up date."""
    rows = db.scalars(select(AdvisoryLog).where(
        AdvisoryLog.agent_id == agent_id,
        AdvisoryLog.follow_up_done.is_(False),
        AdvisoryLog.follow_up_on.is_not(None),
    ))
    out = []
    for l in rows:
        d = _parse_follow_date(l.follow_up_on)
        if d is not None:
            out.append((l, d))
    return out


def due_followup_count(db: Session, agent_id: int, today: date | None = None) -> int:
    today = today or date.today()
    return sum(1 for _, d in _open_followups(db, agent_id) if d <= today)


def raise_due_followup_reminders(db: Session, agent_id: int, today: date | None = None) -> int:
    """Raise a one-time advisory reminder for each follow-up that has come due.
    Idempotent via follow_up_notified, and routed through notify.send so it
    honours the agent's mute/digest preferences (the 'advisory' category)."""
    today = today or date.today()
    created = 0
    for l, d in _open_followups(db, agent_id):
        if d > today or l.follow_up_notified:
            continue
        label = l.crop or "a farmer"
        detail = l.recommendation or l.observation or "check in"
        notify.send(
            db, user_id=agent_id,
            title="Advisory follow-up due",
            body=f"Follow-up due for {label}: {detail}",
            object_type="advisory_log", object_id=l.id,
        )
        l.follow_up_notified = True
        created += 1
    if created:
        db.commit()
    return created


@router.get("/follow-ups")
def follow_ups(user=Depends(_agent), db: Session = Depends(get_db)):
    """The agent's follow-up to-do list: due (today or overdue) and upcoming.
    Opening this also raises reminders for anything newly due."""
    today = date.today()
    raise_due_followup_reminders(db, user.id, today)
    due, upcoming = [], []
    for l, d in sorted(_open_followups(db, user.id), key=lambda x: x[1]):
        item = {**_log_json(l), "follow_up_date": d.isoformat(),
                "days_until": (d - today).days, "overdue": d < today}
        (due if d <= today else upcoming).append(item)
    return {"today": today.isoformat(), "due": due, "upcoming": upcoming}


@router.post("/advisory-logs/{log_id}/follow-up-done")
def mark_follow_up_done(log_id: int, user=Depends(_agent), db: Session = Depends(get_db)):
    """Mark a follow-up as acted on, clearing it from the to-do list."""
    log = db.get(AdvisoryLog, log_id)
    if not log or log.agent_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Advisory log not found")
    log.follow_up_done = True
    db.commit()
    return {"id": log.id, "follow_up_done": True}
