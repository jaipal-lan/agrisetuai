from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.core.ids import dispute_id, idempotency_key as gen_idem, ticket_id
from app.core.money import money
from app.core.rbac import Role
from app.models.common import LedgerDirection
from app.models.common import OrderStatus as S
from app.models.finance import Payment, Refund
from app.models.order import Order
from app.models.support import Dispute, SupportTicket
from app.services import audit
from app.services import ledger
from app.services.ledger import Leg
from app.services import notify
from app.services.state_machine import InvalidTransition, transition

router = APIRouter(tags=["support"])

_ops = require_roles(
    Role.FIELD_MANAGER, Role.FIELD_MANAGER, Role.FIELD_LEADER, Role.SUPERADMIN
)


def _ticket_json(t: SupportTicket) -> dict:
    return {
        "id": t.id,
        "public_id": t.public_id,
        "opener_id": t.opener_id,
        "order_id": t.order_id,
        "issue_type": t.issue_type,
        "subject": t.subject,
        "body": t.body,
        "status": t.status,
        "owner_id": t.owner_id,
        "sla_hours": t.sla_hours,
    }


def _dispute_json(d: Dispute) -> dict:
    return {
        "id": d.id,
        "public_id": d.public_id,
        "order_id": d.order_id,
        "opener_id": d.opener_id,
        "issue_type": d.issue_type,
        "description": d.description,
        "status": d.status,
        "decision": d.decision,
        "decision_note": d.decision_note,
        "decided_by": d.decided_by,
        "evidence": d.evidence or {},
        "financial_consequence": d.financial_consequence,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


class TicketCreate(BaseModel):
    subject: str
    body: str
    issue_type: str = "general"
    order_id: int | None = None
    evidence: dict | None = None


@router.post("/tickets", status_code=status.HTTP_201_CREATED)
def create_ticket(
    body: TicketCreate, user=Depends(get_current_user), db: Session = Depends(get_db)
):
    t = SupportTicket(
        public_id=ticket_id(),
        opener_id=user.id,
        order_id=body.order_id,
        issue_type=body.issue_type,
        subject=body.subject,
        body=body.body,
        evidence=body.evidence,
    )
    db.add(t)
    audit.record(
        db,
        actor_id=user.id,
        action="ticket.create",
        object_type="ticket",
        object_id=t.public_id,
    )
    db.commit()
    db.refresh(t)
    return _ticket_json(t)


@router.get("/tickets")
def list_tickets(user=Depends(get_current_user), db: Session = Depends(get_db)):
    staff = user.role in (
        Role.FIELD_MANAGER,
        Role.FIELD_MANAGER,
        Role.FIELD_LEADER,
        Role.SUPERADMIN,
    )
    stmt = select(SupportTicket).order_by(SupportTicket.id.desc())
    if not staff:
        stmt = stmt.where(SupportTicket.opener_id == user.id)
    return [_ticket_json(t) for t in db.scalars(stmt.limit(100))]


class TicketPatch(BaseModel):
    status: str | None = None
    owner_id: int | None = None


@router.post("/tickets/{ticket_id}/update")
def update_ticket(
    ticket_id: int,
    body: TicketPatch,
    user=Depends(_ops),
    db: Session = Depends(get_db),
):
    t = db.get(SupportTicket, ticket_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    if body.status:
        t.status = body.status
    if body.owner_id is not None:
        t.owner_id = body.owner_id
    db.commit()
    return _ticket_json(t)


class DisputeCreate(BaseModel):
    order_id: int
    issue_type: str
    description: str
    evidence: dict | None = None


@router.post("/disputes", status_code=status.HTTP_201_CREATED)
def create_dispute(
    body: DisputeCreate, user=Depends(get_current_user), db: Session = Depends(get_db)
):
    order = db.get(Order, body.order_id)
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    staff = user.role in (Role.FIELD_MANAGER, Role.FIELD_MANAGER, Role.FIELD_LEADER, Role.SUPERADMIN)
    if not staff and user.id not in (order.buyer_id, order.seller_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a party to this order")
    if order.status in (S.CANCELLED, S.REFUNDED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Order is already closed")

    d = Dispute(
        public_id=dispute_id(),
        order_id=order.id,
        opener_id=user.id,
        issue_type=body.issue_type,
        description=body.description,
        evidence=body.evidence,
    )
    db.add(d)
    if order.status != S.DISPUTED:
        try:
            transition(
                db, order, S.DISPUTED, actor_id=user.id, reason_code=body.issue_type
            )
        except InvalidTransition as e:
            raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    notify.send(
        db,
        user_id=order.buyer_id,
        title="Dispute opened",
        body=f"Order {order.public_id} is under review.",
        object_type="order",
        object_id=order.public_id,
    )
    notify.send(
        db,
        user_id=order.seller_id,
        title="Dispute opened",
        body=f"Order {order.public_id} is under review.",
        object_type="order",
        object_id=order.public_id,
    )
    audit.record(
        db,
        actor_id=user.id,
        action="dispute.open",
        object_type="order",
        object_id=order.public_id,
        reason=body.issue_type,
    )
    db.commit()
    db.refresh(d)
    return _dispute_json(d)


@router.get("/disputes")
def list_disputes(user=Depends(get_current_user), db: Session = Depends(get_db)):
    staff = user.role in (
        Role.FIELD_MANAGER,
        Role.FIELD_MANAGER,
        Role.FIELD_LEADER,
        Role.SUPERADMIN,
    )
    stmt = select(Dispute).order_by(Dispute.id.desc())
    if not staff:
        stmt = stmt.where(Dispute.opener_id == user.id)
    return [_dispute_json(d) for d in db.scalars(stmt.limit(100))]


class DisputeDecision(BaseModel):
    decision: str  # uphold | reject | partial_refund | full_refund | close
    note: str | None = None
    refund_amount: float | None = None


_REFUND_DECISIONS = {"partial_refund", "full_refund"}


@router.post("/disputes/{dispute_id}/decision")
def decide_dispute(
    dispute_id: int,
    body: DisputeDecision,
    user=Depends(_ops),
    db: Session = Depends(get_db),
):
    d = db.get(Dispute, dispute_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispute not found")
    if d.status == "decided":
        raise HTTPException(status.HTTP_409_CONFLICT, "Dispute is already decided")
    order = db.get(Order, d.order_id)

    refund_result = None
    if body.decision in _REFUND_DECISIONS:
        # full_refund => remaining balance (amount=None); partial => the named amount.
        amount = None if body.decision == "full_refund" else body.refund_amount
        if body.decision == "partial_refund" and not amount:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "refund_amount is required for a partial refund")
        refund_result = perform_refund(
            db, order, amount=amount, reason_code="dispute_resolution",
            note=body.note, actor_id=user.id, idem=f"dispute-{d.public_id}",
        )
    elif body.decision == "reject":
        try:
            transition(db, order, S.COMPLETED, actor_id=user.id, reason_code="dispute_rejected")
        except InvalidTransition:
            pass

    d.status = "decided"
    d.decision = body.decision
    d.decision_note = body.note
    d.decided_by = user.id
    d.financial_consequence = {
        "refund_amount": refund_result.get("amount") if refund_result else body.refund_amount,
        "refund_id": refund_result.get("refund_id") if refund_result else None,
    }
    # Tell the opener the outcome regardless of which party raised it.
    notify.send(
        db, user_id=d.opener_id, title="Dispute resolved",
        body=f"Your dispute on order {order.public_id} was resolved: {body.decision.replace('_', ' ')}.",
        object_type="order", object_id=order.public_id,
    )
    audit.record(
        db,
        actor_id=user.id,
        action="dispute.decision",
        object_type="dispute",
        object_id=d.public_id,
        reason=body.decision,
        new_values={"note": body.note},
    )
    db.commit()
    return _dispute_json(d)


class RefundBody(BaseModel):
    amount: float | None = None  # default: remaining buyer_total
    reason_code: str = "partial_refund"
    note: str | None = None


def perform_refund(
    db: Session,
    order: Order,
    *,
    amount: float | None = None,
    reason_code: str = "partial_refund",
    note: str | None = None,
    actor_id: int,
    idem: str | None = None,
) -> dict:
    """Post a balanced refund against an order's captured payment.

    Shared by the finance refund endpoint and dispute resolution so both paths
    reverse the original quote legs identically and keep the ledger balanced.
    Raises HTTPException on invalid state; commits on success.
    """
    if order.quote is None or order.buyer_total is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Order has no captured quote")
    paid = db.scalar(select(Payment).where(Payment.order_id == order.id, Payment.status == "paid"))
    if not paid:
        raise HTTPException(status.HTTP_409_CONFLICT, "No captured payment to refund")

    idem = idem or gen_idem()
    existing = db.scalar(select(Refund).where(Refund.idempotency_key == idem))
    if existing:
        return {"refund_id": existing.id, "duplicate": True, "order_status": order.status}

    already = money(0)
    for r in db.scalars(select(Refund).where(Refund.order_id == order.id)):
        already += money(r.amount)
    remaining = money(order.buyer_total) - already
    refund_amount = money(amount if amount is not None else remaining)
    if refund_amount <= money(0) or refund_amount > remaining:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid refund amount")

    # Reverse proportionally against the original quote legs so history stays intact.
    q = order.quote
    buyer_total = money(order.buyer_total)
    ratio = refund_amount / buyer_total
    debit_spec = [
        ("seller_payable", money(q.get("seller_payable", "0")), "reverse seller"),
        ("platform_revenue", money(q.get("service_fee", "0")) + money(q.get("seller_commission", "0")), "reverse platform revenue"),
        ("transport_payable", money(q.get("transport_charge", "0")), "reverse transport"),
        ("agent_fee_payable", money(q.get("inspection_fee", "0")), "reverse inspection"),
        ("packing_revenue", money(q.get("packing_fee", "0")), "reverse packing"),
        ("tax_payable", money(q.get("tax", "0")), "reverse tax"),
    ]
    shares = {acct: money(amt * ratio) for acct, amt, _ in debit_spec}
    residual = refund_amount - sum(shares.values())
    if residual != money(0):
        biggest = max(shares, key=lambda k: shares[k])
        shares[biggest] = money(shares[biggest] + residual)

    legs = [Leg("cash_clearing", LedgerDirection.CREDIT, refund_amount, "refund to buyer")]
    legs += [Leg(acct, LedgerDirection.DEBIT, shares[acct], memo)
             for acct, _, memo in debit_spec]
    legs = [l for l in legs if money(l.amount) != money(0)]
    ledger.post(db, txn_group=f"refund:{order.public_id}:{idem[:8]}", legs=legs, order_id=order.id, currency=q["currency"])

    rec = Refund(
        order_id=order.id,
        amount=refund_amount,
        currency=q["currency"],
        reason_code=reason_code,
        note=note,
        actor_id=actor_id,
        idempotency_key=idem,
    )
    db.add(rec)
    target = S.REFUNDED if refund_amount == remaining else S.PARTIALLY_REFUNDED
    try:
        if order.status != target:
            transition(db, order, target, actor_id=actor_id, reason_code=reason_code, note=note)
    except InvalidTransition as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    audit.record(
        db,
        actor_id=actor_id,
        action="order.refund",
        object_type="order",
        object_id=order.public_id,
        reason=reason_code,
        new_values={"amount": str(refund_amount)},
    )
    db.commit()
    return {"refund_id": rec.id, "amount": str(refund_amount), "order_status": order.status, "duplicate": False}


@router.post("/orders/{order_id}/refunds")
def refund_order(
    order_id: int,
    body: RefundBody,
    idempotency_key: str | None = Header(default=None),
    user=Depends(require_roles(Role.FIELD_MANAGER, Role.SUPERADMIN, Role.FIELD_MANAGER)),
    db: Session = Depends(get_db),
):
    """Post a balanced refund. Partial refunds keep original payment history intact."""
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return perform_refund(
        db, order, amount=body.amount, reason_code=body.reason_code,
        note=body.note, actor_id=user.id, idem=idempotency_key,
    )

