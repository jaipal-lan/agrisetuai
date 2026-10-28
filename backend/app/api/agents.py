from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.money import qty
from app.core.rbac import Role
from app.models.common import InspectionOutcome
from app.models.common import OrderStatus as S
from app.models.order import Inspection, Order
from app.services import audit
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
    """Orders assigned to this agent that are in an inspection stage."""
    rows = db.scalars(
        select(Order).where(
            Order.assigned_agent_id == user.id,
            Order.status.in_([
                S.INSPECTION_ASSIGNED, S.INSPECTION_IN_PROGRESS,
                S.INSPECTION_HOLD,
            ]),
        )
    )
    return [
        {
            "order_id": o.id,
            "public_id": o.public_id,
            "status": o.status,
            "accepted_terms": o.accepted_terms,
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

    # A pass advances automatically to buyer approval (PRD 5 state chain).
    if outcome_state == S.INSPECTION_PASS and order.status == S.INSPECTION_PASS:
        _safe(db, order, S.BUYER_APPROVAL_PENDING, actor_id=user.id, reason_code="awaiting_buyer")

    audit.record(db, actor_id=user.id, action="inspection.decision", object_type="order",
                 object_id=order.public_id, new_values={"outcome": str(body.outcome), "net_qty": str(net) if net else None})
    db.commit()
    db.refresh(order)
    return {"inspection_id": insp.id, "outcome": insp.outcome, "order_status": order.status}
