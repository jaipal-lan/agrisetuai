from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.ids import public_id
from app.core.money import money
from app.core.rbac import Role
from app.models.advisory import CropCase
from app.models.audit import AuditLog
from app.models.catalog import Commodity
from app.models.common import LedgerDirection
from app.models.common import OrderStatus as S
from app.models.finance import LedgerEntry, Payout, PayoutBatch
from app.models.location import District, Mandal, State
from app.models.marketplace import Listing, Offer, RFQ
from app.models.order import Inspection, Order
from app.models.support import Dispute, SupportTicket
from app.models.user import AgentProfile, BuyerProfile, FarmerProfile, User
from app.services import audit, ledger, notify
from app.services.ledger import Leg

router = APIRouter(prefix="/admin", tags=["admin"])

_staff = require_roles(Role.SUPERADMIN, Role.FINANCE, Role.MANDAL_MANAGER)


@router.get("/kpis")
def kpis(user=Depends(_staff), db: Session = Depends(get_db)):
    total_orders = db.scalar(select(func.count(Order.id))) or 0
    settled = db.scalar(select(func.count(Order.id)).where(Order.status == S.SETTLED)) or 0
    cancelled = db.scalar(select(func.count(Order.id)).where(Order.status == S.CANCELLED)) or 0
    open_listings = db.scalar(select(func.count(Listing.id)).where(Listing.status == "open")) or 0

    # GMV = product value of settled trades (from accepted terms).
    gmv = money(0)
    for o in db.scalars(select(Order).where(Order.status == S.SETTLED)):
        t = o.accepted_terms
        gmv += money(float(t["price_per_unit"]) * float(t["quantity"]))

    return {
        "total_orders": total_orders,
        "settled_orders": settled,
        "cancelled_orders": cancelled,
        "open_listings": open_listings,
        "gmv_settled": str(gmv),
    }


def _compute_reports(db: Session) -> dict:
    """GMV and order counts broken down by commodity, mandal, state and agent.

    GMV is the product value of PAID-or-beyond trades (revenue-recognised).
    """
    paid_states = [S.PAID, S.PACKING, S.READY_FOR_PICKUP, S.PICKED_UP, S.IN_TRANSIT,
                   S.OUT_FOR_DELIVERY, S.DELIVERED_PENDING_ACCEPTANCE, S.COMPLETED, S.SETTLED]

    # Lookups.
    commodities = {c.id: c.name for c in db.scalars(select(Commodity))}
    mandals = {}
    for m in db.scalars(select(Mandal)):
        mandals[m.id] = m
    districts = {d.id: d for d in db.scalars(select(District))}
    states = {s.id: s.name for s in db.scalars(select(State))}
    agent_names = {u.id: u.name for u in db.scalars(select(User))}

    def blank():
        return {"gmv": 0.0, "orders": 0}

    by_commodity: dict = {}
    by_mandal: dict = {}
    by_state: dict = {}
    by_agent: dict = {}
    total_gmv = 0.0
    total_orders = 0

    for o in db.scalars(select(Order).where(Order.status.in_(paid_states))):
        t = o.accepted_terms or {}
        value = float(t.get("price_per_unit", 0)) * float(t.get("quantity", 0))
        total_gmv += value
        total_orders += 1

        cname = commodities.get(t.get("commodity_id"), "—")
        c = by_commodity.setdefault(cname, blank()); c["gmv"] += value; c["orders"] += 1

        m = mandals.get(t.get("mandal_id"))
        mname = m.name if m else "—"
        mm = by_mandal.setdefault(mname, blank()); mm["gmv"] += value; mm["orders"] += 1

        sname = "—"
        if m:
            d = districts.get(m.district_id)
            if d:
                sname = states.get(d.state_id, "—")
        ss = by_state.setdefault(sname, blank()); ss["gmv"] += value; ss["orders"] += 1

        if o.assigned_agent_id:
            an = agent_names.get(o.assigned_agent_id, f"agent {o.assigned_agent_id}")
            aa = by_agent.setdefault(an, blank()); aa["gmv"] += value; aa["orders"] += 1

    def fmt(d: dict) -> list:
        return sorted(
            [{"key": k, "gmv": str(money(v["gmv"])), "orders": v["orders"]} for k, v in d.items()],
            key=lambda r: float(r["gmv"]), reverse=True,
        )

    return {
        "total_gmv": str(money(total_gmv)),
        "total_orders": total_orders,
        "by_commodity": fmt(by_commodity),
        "by_mandal": fmt(by_mandal),
        "by_state": fmt(by_state),
        "by_agent": fmt(by_agent),
    }


@router.get("/reports")
def reports(user=Depends(_staff), db: Session = Depends(get_db)):
    return _compute_reports(db)


@router.get("/reports.csv")
def reports_csv(user=Depends(_staff), db: Session = Depends(get_db)):
    """Same GMV breakdown as /admin/reports, as a downloadable CSV."""
    import csv
    import io

    rep = _compute_reports(db)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["dimension", "key", "gmv_inr", "orders"])
    w.writerow(["total", "ALL", rep["total_gmv"], rep["total_orders"]])
    for dim, rows in (("commodity", rep["by_commodity"]), ("mandal", rep["by_mandal"]),
                      ("state", rep["by_state"]), ("agent", rep["by_agent"])):
        for r in rows:
            w.writerow([dim, r["key"], r["gmv"], r["orders"]])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="agrisetu-gmv-report.csv"'},
    )


@router.get("/ledger/accounts")
def ledger_accounts(user=Depends(_staff), db: Session = Depends(get_db)):
    """Net balance per account + global balance check (should be zero)."""
    rows = db.scalars(select(LedgerEntry))
    balances: dict[str, float] = {}
    for r in rows:
        amt = float(r.amount)
        balances[r.account] = balances.get(r.account, 0.0) + (amt if r.direction == "credit" else -amt)
    net = sum(balances.values())
    return {
        "accounts": {k: str(money(v)) for k, v in sorted(balances.items())},
        "net_balance": str(money(net)),
        "balanced": money(net) == money(0),
    }


@router.get("/kyc")
def kyc_queue(status_filter: str = "pending", user=Depends(_staff), db: Session = Depends(get_db)):
    """Users awaiting KYC verification (farmers, buyers, agents)."""
    out = []
    # Agents are onboarded via training/performance, not KYC verification.
    for model, kind in ((FarmerProfile, "farmer"), (BuyerProfile, "buyer")):
        for p in db.scalars(select(model).where(model.verification_status == status_filter)):
            u = db.get(User, p.user_id)
            if not u:
                continue
            out.append({
                "user_id": u.id, "name": u.name, "phone": u.phone, "role": u.role,
                "kind": kind, "verification_status": p.verification_status,
                "village": getattr(p, "village", None),
                "buyer_type": getattr(p, "buyer_type", None),
            })
    return out


class KycDecision(BaseModel):
    approve: bool
    reason: str | None = None


@router.post("/kyc/{user_id}/decision")
def kyc_decision(user_id: int, body: KycDecision,
                 actor=Depends(require_roles(Role.SUPERADMIN, Role.MANDAL_MANAGER)),
                 db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    new_status = "verified" if body.approve else "rejected"
    updated = False
    for prof in (target.farmer_profile, target.buyer_profile):
        if prof is not None:
            prof.verification_status = new_status
            updated = True
    if not updated:
        raise HTTPException(status.HTTP_409_CONFLICT, "User has no verifiable profile")
    notify.send(db, user_id=target.id,
                title="KYC " + ("approved" if body.approve else "rejected"),
                body=("Your account is verified." if body.approve
                      else f"Verification was not approved. {body.reason or ''}".strip()),
                object_type="user", object_id=target.id)
    audit.record(db, actor_id=actor.id, action="kyc.decision", object_type="user",
                 object_id=target.id, new_values={"status": new_status}, reason=body.reason)
    db.commit()
    return {"user_id": target.id, "verification_status": new_status}


class Broadcast(BaseModel):
    title: str
    body: str
    audience: str = "all"  # all | farmers | buyers | agents | couriers | staff


_AUDIENCE_ROLES = {
    "farmers": [Role.FARMER, Role.FPO],
    "buyers": [Role.BUYER_HOUSEHOLD, Role.BUYER_BUSINESS],
    "agents": [Role.FIELD_AGENT],
    "couriers": [Role.TRANSPORT],
    "staff": [Role.SUPPORT, Role.FINANCE, Role.MANDAL_MANAGER, Role.SUPERADMIN],
}


@router.post("/broadcast")
def broadcast(body: Broadcast,
              actor=Depends(require_roles(Role.SUPERADMIN, Role.MANDAL_MANAGER)),
              db: Session = Depends(get_db)):
    """Send an in-app announcement to every active user in the chosen audience."""
    if not body.title.strip() or not body.body.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Title and message are required")
    stmt = select(User).where(User.status == "active")
    if body.audience != "all":
        roles = _AUDIENCE_ROLES.get(body.audience)
        if not roles:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown audience")
        stmt = stmt.where(User.role.in_([str(r) for r in roles]))
    recipients = list(db.scalars(stmt))
    for u in recipients:
        notify.send(db, user_id=u.id, title=body.title.strip(), body=body.body.strip(),
                    object_type="announcement", object_id=None)
    audit.record(db, actor_id=actor.id, action="admin.broadcast", object_type="announcement",
                 object_id=None, new_values={"audience": body.audience, "count": len(recipients)})
    db.commit()
    return {"sent": len(recipients), "audience": body.audience}


_finance = require_roles(Role.FINANCE, Role.SUPERADMIN)


@router.get("/payouts")
def payouts_overview(user=Depends(_finance), db: Session = Depends(get_db)):
    """Accrued (pending) seller payouts awaiting disbursement, plus past batches."""
    pending = list(db.scalars(select(Payout).where(Payout.status == "pending").order_by(Payout.id)))
    names = {u.id: u.name for u in db.scalars(select(User))}
    orders = {o.id: o.public_id for o in db.scalars(select(Order))}
    total = money(sum(float(p.amount) for p in pending)) if pending else money(0)
    batches = db.scalars(select(PayoutBatch).order_by(PayoutBatch.id.desc()).limit(20))
    return {
        "pending_count": len(pending),
        "pending_total": str(total),
        "pending": [{
            "id": p.id, "order": orders.get(p.order_id), "seller": names.get(p.seller_id) or f"user {p.seller_id}",
            "amount": str(money(p.amount)), "currency": p.currency,
        } for p in pending],
        "batches": [{
            "public_id": b.public_id, "status": b.status, "payout_count": b.payout_count,
            "total_amount": str(money(b.total_amount)), "note": b.note,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        } for b in batches],
    }


class PayoutRun(BaseModel):
    note: str | None = None


@router.post("/payouts/run")
def run_payout_batch(body: PayoutRun, user=Depends(_finance), db: Session = Depends(get_db)):
    """Sweep all pending payouts into one disbursement batch.

    Moves each accrued amount seller_clearing -> cash_clearing (ledger stays
    balanced), marks the payout processed, links it to the batch, and alerts the
    seller. Mock disbursement in the pilot; a real bank/UPI payout API plugs in here.
    """
    pending = list(db.scalars(select(Payout).where(Payout.status == "pending").order_by(Payout.id)))
    if not pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "No pending payouts to disburse")

    batch = PayoutBatch(
        public_id=public_id("PB", 8), status="processed", payout_count=len(pending),
        currency=pending[0].currency, created_by=user.id, note=body.note,
        provider_ref=f"mock-{public_id('REF', 8).lower()}",
    )
    db.add(batch)
    db.flush()

    total = money(0)
    for p in pending:
        amt = money(p.amount)
        ledger.post(
            db,
            txn_group=f"payout_batch:{batch.public_id}:{p.order_id}",
            order_id=p.order_id,
            currency=p.currency,
            legs=[
                Leg("seller_clearing", LedgerDirection.DEBIT, amt, "disburse to seller"),
                Leg("cash_clearing", LedgerDirection.CREDIT, amt, "payout sent"),
            ],
        )
        p.status = "processed"
        p.batch_id = batch.id
        p.provider_ref = batch.provider_ref
        total += amt
        try:
            notify.send(db, user_id=p.seller_id, title="Payout sent",
                        body=f"Your payout of Rs. {amt} has been disbursed (batch {batch.public_id}).",
                        object_type="payout", object_id=batch.public_id)
        except Exception:
            pass
    batch.total_amount = total
    audit.record(db, actor_id=user.id, action="payout.batch", object_type="payout_batch",
                 object_id=batch.public_id, new_values={"count": len(pending), "total": str(total)})
    db.commit()
    return {"batch": batch.public_id, "payout_count": len(pending), "total_amount": str(total)}


@router.get("/audit-logs")
def audit_logs(limit: int = 100, user=Depends(_staff), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))
    return [
        {
            "id": a.id,
            "actor_id": a.actor_id,
            "action": a.action,
            "object_type": a.object_type,
            "object_id": a.object_id,
            "reason": a.reason,
            "at": a.at.isoformat(),
        }
        for a in rows
    ]
