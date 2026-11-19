from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.ids import public_id
from app.core.money import money
from app.core.rbac import Role
from app.core.serializers import _id_documents, _mask, _secure_media_url
from app.models.audit import AuditLog
from app.models.catalog import Commodity
from app.models.common import LedgerDirection
from app.models.common import OrderStatus as S
from app.models.finance import LedgerEntry, Payout, PayoutBatch, WithdrawalRequest
from app.models.location import District, Mandal, State
from app.models.marketplace import Listing, Offer, RFQ
from app.models.order import Inspection, Order
from app.models.support import Dispute, SupportTicket
from app.models.user import AgentProfile, BuyerProfile, FarmerProfile, Organisation, User
from app.services import audit, kyc, ledger, notify
from app.services.ledger import Leg

router = APIRouter(prefix="/admin", tags=["admin"])

_staff = require_roles(Role.SUPERADMIN, Role.FIELD_MANAGER, Role.FIELD_LEADER)


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


def _parse_window(from_: str | None, to: str | None):
    """Parse YYYY-MM-DD from/to into a [start, end) UTC datetime window. `to` is
    inclusive (end-of-day). Either side may be None (open-ended)."""
    def parse(s):
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start = end = None
    try:
        if from_:
            start = parse(from_)
        if to:
            end = parse(to) + timedelta(days=1)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Dates must be YYYY-MM-DD")
    return start, end


def _window(stmt, col, start, end):
    if start is not None:
        stmt = stmt.where(col >= start)
    if end is not None:
        stmt = stmt.where(col < end)
    return stmt


def _compute_reports(db: Session, start=None, end=None) -> dict:
    """GMV and order counts broken down by commodity, mandal, state and agent.

    GMV is the product value of PAID-or-beyond trades (revenue-recognised).
    Optionally restricted to orders created within [start, end).
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

    for o in db.scalars(_window(select(Order).where(Order.status.in_(paid_states)),
                                 Order.created_at, start, end)):
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
def reports(from_: str | None = Query(None, alias="from"), to: str | None = None,
            user=Depends(_staff), db: Session = Depends(get_db)):
    start, end = _parse_window(from_, to)
    return {**_compute_reports(db, start, end), "from": from_, "to": to}


@router.get("/reports.csv")
def reports_csv(from_: str | None = Query(None, alias="from"), to: str | None = None,
                user=Depends(_staff), db: Session = Depends(get_db)):
    """Same GMV breakdown as /admin/reports, as a downloadable CSV."""
    import csv
    import io

    start, end = _parse_window(from_, to)
    rep = _compute_reports(db, start, end)
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
        headers={"Content-Disposition": 'attachment; filename="kissansetu-gmv-report.csv"'},
    )


def _pct(num: int, den: int) -> float:
    return round(100.0 * num / den, 1) if den else 0.0


def _compute_ops_report(db: Session, start=None, end=None) -> dict:
    """Operational scorecard: field-agent throughput/quality, courier delivery
    performance, dispute rate + outcomes, and payout standing. Optionally
    restricted to records created within [start, end)."""
    from app.models.order import Shipment, ShipmentEvent

    names = {u.id: (u.name or f"user {u.id}") for u in db.scalars(select(User))}

    # --- Field agents: inspections (by outcome), orders handled ---------------
    agents: dict[int, dict] = {}

    def agent(aid):
        return agents.setdefault(aid, {
            "agent_id": aid, "name": names.get(aid, f"user {aid}"),
            "inspections": 0, "pass": 0, "hold": 0, "fail": 0,
            "orders_assigned": 0,
        })

    for insp in db.scalars(_window(select(Inspection), Inspection.created_at, start, end)):
        a = agent(insp.agent_id)
        a["inspections"] += 1
        oc = (insp.outcome or "").lower()
        if oc in ("pass", "pass_with_adjustment"):
            a["pass"] += 1
        elif oc == "hold":
            a["hold"] += 1
        elif oc == "fail":
            a["fail"] += 1
    for aid, in db.execute(_window(
        select(Order.assigned_agent_id).where(Order.assigned_agent_id.is_not(None)),
        Order.created_at, start, end)):
        agent(aid)["orders_assigned"] += 1

    agent_rows = []
    for a in agents.values():
        a["pass_rate_pct"] = _pct(a["pass"], a["inspections"])
        agent_rows.append(a)
    agent_rows.sort(key=lambda r: (r["inspections"], r["orders_assigned"]), reverse=True)

    # --- Couriers: delivery completion + average transit time -----------------
    # Earliest timestamp per (shipment, event) for transit-time math.
    ev_at: dict[int, dict[str, datetime]] = {}
    for e in db.scalars(select(ShipmentEvent).order_by(ShipmentEvent.at)):
        ev_at.setdefault(e.shipment_id, {}).setdefault(e.event, e.at)

    couriers: dict[int, dict] = {}
    transit_acc: dict[int, list] = {}
    for sh in db.scalars(_window(
            select(Shipment).where(Shipment.courier_id.is_not(None)),
            Shipment.created_at, start, end)):
        c = couriers.setdefault(sh.courier_id, {
            "courier_id": sh.courier_id, "name": sh.courier_name or f"courier {sh.courier_id}",
            "shipments": 0, "delivered": 0, "active": 0, "failed": 0,
        })
        c["shipments"] += 1
        evs = ev_at.get(sh.id, {})
        if "delivered" in evs:
            c["delivered"] += 1
            if "picked_up" in evs:
                hrs = (evs["delivered"] - evs["picked_up"]).total_seconds() / 3600.0
                if hrs >= 0:
                    transit_acc.setdefault(sh.courier_id, []).append(hrs)
        elif "failed_delivery" in evs or sh.status == "failed_delivery":
            c["failed"] += 1
        else:
            c["active"] += 1

    courier_rows = []
    for cid, c in couriers.items():
        c["completion_rate_pct"] = _pct(c["delivered"], c["shipments"])
        acc = transit_acc.get(cid, [])
        c["avg_transit_hours"] = round(sum(acc) / len(acc), 1) if acc else None
        courier_rows.append(c)
    courier_rows.sort(key=lambda r: r["shipments"], reverse=True)

    # --- Disputes: rate against revenue-recognised orders + outcome mix -------
    paid_states = [S.PAID, S.PACKING, S.READY_FOR_PICKUP, S.PICKED_UP, S.IN_TRANSIT,
                   S.OUT_FOR_DELIVERY, S.DELIVERED_PENDING_ACCEPTANCE, S.COMPLETED, S.SETTLED]
    paid_orders = db.scalar(_window(
        select(func.count(Order.id)).where(Order.status.in_(paid_states)),
        Order.created_at, start, end)) or 0
    total_disputes = db.scalar(_window(select(func.count(Dispute.id)), Dispute.created_at, start, end)) or 0
    by_outcome: dict[str, int] = {}
    decided = 0
    for d in db.scalars(_window(select(Dispute), Dispute.created_at, start, end)):
        if d.decision:
            decided += 1
            by_outcome[d.decision] = by_outcome.get(d.decision, 0) + 1
    disputes = {
        "total": total_disputes,
        "open": total_disputes - decided,
        "decided": decided,
        "dispute_rate_pct": _pct(total_disputes, paid_orders),
        "by_outcome": by_outcome,
    }

    # --- Payouts: pending vs processed, batches -------------------------------
    def _sum(stmt):
        tot = money(0)
        for p in db.scalars(stmt):
            tot += money(p.amount)
        return tot

    def _pq(status_val):
        return _window(select(Payout).where(Payout.status == status_val), Payout.created_at, start, end)

    def _pc(status_val):
        return _window(select(func.count(Payout.id)).where(Payout.status == status_val),
                       Payout.created_at, start, end)
    payouts = {
        "pending_count": db.scalar(_pc("pending")) or 0,
        "pending_total": str(_sum(_pq("pending"))),
        "processed_count": db.scalar(_pc("processed")) or 0,
        "processed_total": str(_sum(_pq("processed"))),
        "batches": db.scalar(_window(select(func.count(PayoutBatch.id)), PayoutBatch.created_at, start, end)) or 0,
    }

    return {"agents": agent_rows, "couriers": courier_rows,
            "disputes": disputes, "payouts": payouts}


@router.get("/ops-report")
def ops_report(from_: str | None = Query(None, alias="from"), to: str | None = None,
               user=Depends(_staff), db: Session = Depends(get_db)):
    start, end = _parse_window(from_, to)
    return {**_compute_ops_report(db, start, end), "from": from_, "to": to}


@router.get("/ops-report.csv")
def ops_report_csv(from_: str | None = Query(None, alias="from"), to: str | None = None,
                   user=Depends(_staff), db: Session = Depends(get_db)):
    """Operational scorecard as a downloadable CSV (one section per block)."""
    import csv
    import io

    start, end = _parse_window(from_, to)
    rep = _compute_ops_report(db, start, end)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["AGENTS"])
    w.writerow(["name", "inspections", "pass", "hold", "fail", "pass_rate_pct",
                "orders_assigned"])
    for a in rep["agents"]:
        w.writerow([a["name"], a["inspections"], a["pass"], a["hold"], a["fail"],
                    a["pass_rate_pct"], a["orders_assigned"]])
    w.writerow([])
    w.writerow(["COURIERS"])
    w.writerow(["name", "shipments", "delivered", "active", "failed",
                "completion_rate_pct", "avg_transit_hours"])
    for c in rep["couriers"]:
        w.writerow([c["name"], c["shipments"], c["delivered"], c["active"], c["failed"],
                    c["completion_rate_pct"], c["avg_transit_hours"]])
    w.writerow([])
    d = rep["disputes"]
    w.writerow(["DISPUTES"])
    w.writerow(["total", "open", "decided", "dispute_rate_pct"])
    w.writerow([d["total"], d["open"], d["decided"], d["dispute_rate_pct"]])
    w.writerow(["outcome", "count"])
    for k, v in d["by_outcome"].items():
        w.writerow([k, v])
    w.writerow([])
    p = rep["payouts"]
    w.writerow(["PAYOUTS"])
    w.writerow(["pending_count", "pending_total_inr", "processed_count", "processed_total_inr", "batches"])
    w.writerow([p["pending_count"], p["pending_total"], p["processed_count"],
                p["processed_total"], p["batches"]])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="kissansetu-ops-report.csv"'},
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
    """Users awaiting KYC verification (farmers, buyers), with their submitted
    government photo-ID documents so staff can review them before deciding."""
    out = []
    # Agents are onboarded via training/performance, not KYC verification.
    for model, kind in ((FarmerProfile, "farmer"), (BuyerProfile, "buyer")):
        for p in db.scalars(select(model).where(model.verification_status == status_filter)):
            u = db.get(User, p.user_id)
            if not u:
                continue
            entry = {
                "user_id": u.id, "name": u.name, "phone": u.phone, "role": u.role,
                "kind": kind, "verification_status": p.verification_status,
                "village": getattr(p, "village", None),
                "buyer_type": getattr(p, "buyer_type", None),
                "aadhaar_masked": _mask(u.aadhaar),
                "pan_masked": _mask(u.pan),
                # Uploaded ID photos/PDFs for the reviewer to open one by one.
                "id_documents": _id_documents(u),
            }
            # Business buyers: attach the organisation's registration evidence
            # (signed links) + details so staff can review the KYC in one place.
            if u.organisation_id:
                org = db.get(Organisation, u.organisation_id)
                if org:
                    refs = org.licence_refs or {}
                    entry["business"] = {
                        "legal_name": org.legal_name,
                        "registration_number": refs.get("registration_number"),
                        "gst": refs.get("gst"),
                        "evidence": [{"object_key": k, "url": _secure_media_url(k)}
                                     for k in (refs.get("evidence_keys") or [])],
                    }
            out.append(entry)
    return out


class KycDecision(BaseModel):
    approve: bool
    reason: str | None = None


@router.post("/kyc/{user_id}/decision")
def kyc_decision(user_id: int, body: KycDecision,
                 actor=Depends(require_roles(Role.SUPERADMIN, Role.FIELD_LEADER)),
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
    "farmers": [Role.FARMER],
    "buyers": [Role.BUYER_HOUSEHOLD, Role.BUYER_BUSINESS],
    "agents": [Role.FIELD_AGENT],
    "couriers": [Role.TRANSPORT],
    "staff": [Role.FIELD_AGENT, Role.FIELD_LEADER, Role.FIELD_MANAGER, Role.SUPERADMIN],
}


@router.post("/broadcast")
def broadcast(body: Broadcast,
              actor=Depends(require_roles(Role.SUPERADMIN, Role.FIELD_LEADER)),
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


_finance = require_roles(Role.FIELD_MANAGER, Role.SUPERADMIN)


@router.get("/payouts")
def payouts_overview(user=Depends(_finance), db: Session = Depends(get_db)):
    """Accrued (pending) seller payouts awaiting disbursement, plus past batches."""
    from app.models.account import PayoutAccount

    pending = list(db.scalars(select(Payout).where(Payout.status == "pending").order_by(Payout.id)))
    names = {u.id: u.name for u in db.scalars(select(User))}
    orders = {o.id: o.public_id for o in db.scalars(select(Order))}
    accounts = {a.user_id: a for a in db.scalars(select(PayoutAccount))}
    have_account = set(accounts)
    verified_accounts = {uid for uid, a in accounts.items() if a.verified}
    # Identity-KYC status of each pending payee (N/A for transport -> treated ok).
    payees = {u.id: u for u in db.scalars(
        select(User).where(User.id.in_({p.seller_id for p in pending})))} if pending else {}
    id_ok = {uid: kyc.identity_verified(u) for uid, u in payees.items()}
    total = money(sum(float(p.amount) for p in pending)) if pending else money(0)
    missing = sum(1 for p in pending if p.seller_id not in have_account)
    # Payouts that cannot be disbursed yet: no/unverified account, or unverified identity.
    blocked = sum(1 for p in pending if p.seller_id not in verified_accounts)
    blocked_identity = sum(1 for p in pending if not id_ok.get(p.seller_id, False))
    batches = db.scalars(select(PayoutBatch).order_by(PayoutBatch.id.desc()).limit(20))
    return {
        "pending_count": len(pending),
        "pending_total": str(total),
        "missing_payout_accounts": missing,
        "blocked_unverified": blocked,
        "blocked_unverified_identity": blocked_identity,
        "pending": [{
            "id": p.id, "order": orders.get(p.order_id), "seller": names.get(p.seller_id) or f"user {p.seller_id}",
            "payee_type": getattr(p, "payee_type", "seller"),
            "has_account": p.seller_id in have_account,
            "verified": p.seller_id in verified_accounts,
            "identity_verified": id_ok.get(p.seller_id, False),
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


def _disburse_payouts(db, payouts, *, created_by, note=None):
    """Move a set of accrued (pending) payouts into one disbursement batch:
    clearing -> cash_clearing per payout (ledger stays balanced), mark processed,
    link the batch, notify each payee. Shared by the admin batch run and
    farmer-initiated withdrawals. Caller commits."""
    batch = PayoutBatch(
        public_id=public_id("PB", 8), status="processed", payout_count=len(payouts),
        currency=payouts[0].currency, created_by=created_by, note=note,
        provider_ref=f"mock-{public_id('REF', 8).lower()}",
    )
    db.add(batch)
    db.flush()
    total = money(0)
    for p in payouts:
        amt = money(p.amount)
        is_transport = getattr(p, "payee_type", "seller") == "transport"
        clearing = "transport_clearing" if is_transport else "seller_clearing"
        who = "transport partner" if is_transport else "seller"
        ledger.post(
            db,
            txn_group=f"payout_batch:{batch.public_id}:{p.order_id}",
            order_id=p.order_id,
            currency=p.currency,
            legs=[
                Leg(clearing, LedgerDirection.DEBIT, amt, f"disburse to {who}"),
                Leg("cash_clearing", LedgerDirection.CREDIT, amt, "payout sent"),
            ],
        )
        p.status = "processed"
        p.batch_id = batch.id
        p.provider_ref = batch.provider_ref
        total += amt
        try:
            notify.send(db, user_id=p.seller_id, title="Payout sent",
                        body=f"Your {('delivery ' if is_transport else '')}payout of Rs. {amt} "
                             f"has been disbursed (batch {batch.public_id}).",
                        object_type="payout", object_id=batch.public_id)
        except Exception:
            pass
    batch.total_amount = total
    return batch


@router.post("/payouts/run")
def run_payout_batch(body: PayoutRun, user=Depends(_finance), db: Session = Depends(get_db)):
    """Sweep all pending payouts into one disbursement batch.

    Moves each accrued amount seller_clearing -> cash_clearing (ledger stays
    balanced), marks the payout processed, links it to the batch, and alerts the
    seller. Mock disbursement in the pilot; a real bank/UPI payout API plugs in here.
    """
    from app.models.account import PayoutAccount

    all_pending = list(db.scalars(select(Payout).where(Payout.status == "pending").order_by(Payout.id)))
    if not all_pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "No pending payouts to disburse")

    # Only disburse to payees with BOTH a verified payout account AND a verified
    # identity (identity-KYC is N/A for transport). Anything else is held.
    verified_accounts = {a.user_id for a in db.scalars(select(PayoutAccount)) if a.verified}
    payees = {u.id: u for u in db.scalars(
        select(User).where(User.id.in_({p.seller_id for p in all_pending})))}

    def _disbursable(p):
        return (p.seller_id in verified_accounts
                and kyc.identity_verified(payees.get(p.seller_id)))

    pending = [p for p in all_pending if _disbursable(p)]
    held = len(all_pending) - len(pending)
    held_identity = sum(1 for p in all_pending
                        if p.seller_id in verified_accounts
                        and not kyc.identity_verified(payees.get(p.seller_id)))
    if not pending:
        reason = ("their identity is not verified yet (approve it in the Identity "
                  "verification queue)" if held_identity
                  else "the payee has no verified payout account (verify it under Payout accounts)")
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"No payouts are disbursable — {held} pending payout(s) are held because {reason}.",
        )

    batch = _disburse_payouts(db, pending, created_by=user.id, note=body.note)
    total = batch.total_amount
    audit.record(db, actor_id=user.id, action="payout.batch", object_type="payout_batch",
                 object_id=batch.public_id, new_values={"count": len(pending), "total": str(total)})
    db.commit()
    return {"batch": batch.public_id, "payout_count": len(pending),
            "total_amount": str(total), "held_unverified": held,
            "held_unverified_identity": held_identity}


# --- Farmer withdrawal requests (finance approves -> disburse) -------------

class WithdrawalDecision(BaseModel):
    approve: bool
    reason: str | None = None


@router.get("/withdrawals")
def withdrawals_queue(status_filter: str = "requested", user=Depends(_finance),
                      db: Session = Depends(get_db)):
    """Farmer/partner withdrawal requests for finance. Defaults to the pending
    ('requested') queue; pass status_filter=paid|rejected|all for others."""
    rows = list(db.scalars(select(WithdrawalRequest).order_by(WithdrawalRequest.id.desc())))
    if status_filter != "all":
        rows = [w for w in rows if w.status == status_filter]
    names = {u.id: (u.name or u.phone) for u in db.scalars(select(User))}
    return [{
        "id": w.id, "farmer_id": w.farmer_id, "farmer_name": names.get(w.farmer_id),
        "amount": str(w.amount), "currency": w.currency, "method": w.method,
        "account_masked": w.account_masked, "status": w.status, "note": w.note,
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "decided_at": w.decided_at,
    } for w in rows]


@router.post("/withdrawals/{wid}/decision")
def decide_withdrawal(wid: int, body: WithdrawalDecision, user=Depends(_finance),
                      db: Session = Depends(get_db)):
    """Approve a withdrawal (disburses the farmer's accrued payouts through the
    normal ledger path) or reject it (balance stays, paid in a later batch)."""
    from app.models.account import PayoutAccount
    from app.models.common import utcnow

    w = db.get(WithdrawalRequest, wid)
    if not w:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Withdrawal request not found")
    if w.status != "requested":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Already {w.status}")
    w.decided_by = user.id
    w.decided_at = utcnow().isoformat()
    if not body.approve:
        w.status = "rejected"
        w.note = (body.reason or "").strip() or None
        notify.send(db, user_id=w.farmer_id, title="Withdrawal declined",
                    body=f"Your withdrawal request of Rs. {w.amount} was declined."
                         + (f" Reason: {w.note}" if w.note else ""),
                    object_type="payout", object_id=w.id)
        audit.record(db, actor_id=user.id, action="withdrawal.reject", object_type="user",
                     object_id=w.farmer_id, new_values={"id": w.id})
        db.commit()
        return {"id": w.id, "status": w.status}

    acct = db.scalar(select(PayoutAccount).where(PayoutAccount.user_id == w.farmer_id))
    if not acct or not acct.verified:
        raise HTTPException(status.HTTP_409_CONFLICT, "Payee's payout account is not verified.")
    if not kyc.identity_verified(db.get(User, w.farmer_id)):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Payee's identity is not verified yet — approve it in the "
                            "Identity verification queue first.")
    pending = list(db.scalars(select(Payout).where(
        Payout.seller_id == w.farmer_id, Payout.status == "pending").order_by(Payout.id)))
    if not pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "No accrued payouts to disburse for this payee.")
    batch = _disburse_payouts(db, pending, created_by=user.id, note=f"withdrawal #{w.id}")
    w.status = "paid"
    w.amount = batch.total_amount
    w.batch_id = batch.id
    notify.send(db, user_id=w.farmer_id, title="Withdrawal paid",
                body=f"Your withdrawal of Rs. {batch.total_amount} has been paid out (batch {batch.public_id}).",
                object_type="payout", object_id=batch.public_id)
    audit.record(db, actor_id=user.id, action="withdrawal.approve", object_type="payout_batch",
                 object_id=batch.public_id, new_values={"id": w.id, "amount": str(batch.total_amount)})
    db.commit()
    return {"id": w.id, "status": w.status, "batch": batch.public_id, "amount": str(batch.total_amount)}


# --- Payout-account verification ------------------------------------------

@router.get("/payout-accounts")
def payout_accounts_queue(status_filter: str = "unverified",
                          user=Depends(_finance), db: Session = Depends(get_db)):
    """Partner payout accounts (seller/transport) for finance to verify. Defaults
    to the unverified queue; pass status_filter=verified|all to see others."""
    from app.models.account import PayoutAccount

    accounts = list(db.scalars(select(PayoutAccount).order_by(PayoutAccount.updated_at.desc())))
    if status_filter == "unverified":
        accounts = [a for a in accounts if not a.verified]
    elif status_filter == "verified":
        accounts = [a for a in accounts if a.verified]
    users = {u.id: u for u in db.scalars(select(User))}
    out = []
    for a in accounts:
        u = users.get(a.user_id)
        acct = a.account_number
        masked = f"****{acct[-4:]}" if acct and len(acct) >= 4 else acct
        out.append({
            "user_id": a.user_id,
            "name": (u.name if u else None) or f"user {a.user_id}",
            "phone": u.phone if u else None,
            "role": u.role if u else None,
            "method": a.method,
            "upi_id": a.upi_id,
            "account_name": a.account_name,
            "account_number_masked": masked,
            "ifsc": a.ifsc,
            "verified": a.verified,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        })
    return out


class PayoutVerifyDecision(BaseModel):
    approve: bool
    reason: str | None = None


@router.post("/payout-accounts/{user_id}/verify")
def verify_payout_account(user_id: int, body: PayoutVerifyDecision,
                          actor=Depends(_finance), db: Session = Depends(get_db)):
    """Approve or reject a partner's payout account. Only verified accounts are
    paid out (see run_payout_batch)."""
    from app.models.account import PayoutAccount

    a = db.scalar(select(PayoutAccount).where(PayoutAccount.user_id == user_id))
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No payout account for this user")
    a.verified = bool(body.approve)
    notify.send(db, user_id=user_id,
                title="Payout account " + ("verified" if body.approve else "rejected"),
                body=("Your payout account is verified — you'll receive payouts here."
                      if body.approve else
                      f"Your payout account was not approved. {body.reason or 'Please re-check the details.'}".strip()),
                object_type="payout_account", object_id=user_id)
    audit.record(db, actor_id=actor.id, action="payout_account.verify", object_type="user",
                 object_id=user_id, new_values={"verified": a.verified}, reason=body.reason)
    db.commit()
    return {"user_id": user_id, "verified": a.verified}


@router.get("/users")
def list_users(q: str | None = None, role: str | None = None, status_filter: str | None = None,
               user=Depends(_staff), db: Session = Depends(get_db)):
    """Directory of all users with optional search/role/status filters."""
    stmt = select(User).order_by(User.id.desc())
    if role:
        stmt = stmt.where(User.role == role)
    if status_filter:
        stmt = stmt.where(User.status == status_filter)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where((User.name.ilike(like)) | (User.phone.ilike(like)))
    rows = list(db.scalars(stmt.limit(200)))
    return [{"id": u.id, "name": u.name, "phone": u.phone, "role": u.role,
             "status": u.status, "onboarding_complete": u.onboarding_complete} for u in rows]


class UserStatus(BaseModel):
    status: str  # active | suspended
    reason: str | None = None


@router.post("/users/{user_id}/status")
def set_user_status(user_id: int, body: UserStatus,
                    actor=Depends(require_roles(Role.SUPERADMIN)),
                    db: Session = Depends(get_db)):
    """Suspend or reactivate a user. Suspending also revokes their active sessions."""
    if body.status not in ("active", "suspended"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "status must be active or suspended")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if target.id == actor.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot change your own status")
    target.status = body.status
    if body.status == "suspended":
        target.token_version = int(target.token_version or 0) + 1  # force logout
    notify.send(db, user_id=target.id,
                title="Account " + ("suspended" if body.status == "suspended" else "reactivated"),
                body=(f"Your account was suspended. {body.reason or ''}".strip()
                      if body.status == "suspended" else "Your account is active again."),
                object_type="user", object_id=target.id)
    audit.record(db, actor_id=actor.id, action="user.status", object_type="user",
                 object_id=target.id, new_values={"status": body.status}, reason=body.reason)
    db.commit()
    return {"user_id": target.id, "status": target.status}


@router.post("/scheduler/run")
def run_scheduler(user=Depends(require_roles(Role.SUPERADMIN)), db: Session = Depends(get_db)):
    """Run the sandboxed scheduled jobs once: raise due follow-up reminders and
    compile daily digests. Handy for a demo, or for an external cron to call in
    place of the in-process timer (SCHEDULER_INTERVAL_SECONDS)."""
    from app.services.scheduler import run_scheduled_jobs

    result = run_scheduled_jobs(db)
    audit.record(db, actor_id=user.id, action="scheduler.run", object_type="system",
                 object_id="scheduler", new_values=result)
    db.commit()
    return result


@router.get("/prices/status")
def prices_status(user=Depends(_staff), db: Session = Depends(get_db)):
    """Live-feed health: configuration, row counts and freshness, for the badge."""
    from app.services import prices_feed
    return prices_feed.status(db)


class PricesImport(BaseModel):
    records: list[dict]


@router.post("/prices/import")
def import_market_prices(body: PricesImport, user=Depends(require_roles(Role.SUPERADMIN)),
                         db: Session = Depends(get_db)):
    """Upsert mandi prices fetched elsewhere (e.g. from an India IP that can reach
    data.gov.in — the server's own datacenter may be geo-blocked). Same upsert +
    stale-sweep as the live refresh."""
    from app.services import prices_feed
    if not body.records:
        return {"ok": False, "message": "no records provided"}
    result = prices_feed.refresh_prices(db, records=body.records)
    audit.record(db, actor_id=user.id, action="prices.import", object_type="system",
                 object_id="market_prices", new_values={"count": result.get("upserted")})
    db.commit()
    return {"ok": True, **result}


@router.get("/prices/diagnose")
def prices_diagnose(user=Depends(require_roles(Role.SUPERADMIN))):
    """Diagnostic: show the key length (not the key) and exactly what data.gov.in
    returns to THIS server for a 1-row probe — distinguishes a bad key from a
    network/geo block without needing log access."""
    import json as _json
    import urllib.parse as _up
    import urllib.request as _ur

    from app.core.config import settings as _s
    from app.services import prices_feed as _pf

    out = {"provider": _s.prices_provider, "key_len": len(_s.data_gov_in_api_key or ""),
           "configured": _pf.provider_configured()}
    if not out["configured"]:
        return out
    params = {"api-key": _s.data_gov_in_api_key, "format": "json", "limit": "1"}
    url = f"{_pf.DATA_GOV_URL}?{_up.urlencode(params)}"
    try:
        req = _ur.Request(url, headers={"User-Agent": "agrisetuai/diag"})
        with _ur.urlopen(req, timeout=25) as r:  # noqa: S310 (fixed gov URL)
            body = r.read().decode("utf-8")
        d = _json.loads(body)
        out.update({"http": 200, "api_status": d.get("status"), "message": d.get("message"),
                    "total": d.get("total"), "count": d.get("count"),
                    "records": len(d.get("records", [])), "body_head": body[:160]})
    except Exception as e:  # noqa: BLE001
        out.update({"error": repr(e)[:300]})
    return out


@router.post("/prices/refresh")
def refresh_market_prices(user=Depends(require_roles(Role.SUPERADMIN)), db: Session = Depends(get_db)):
    """Pull the latest government-declared mandi prices from the live feed
    (data.gov.in / AGMARKNET) and upsert them. Requires PRICES_PROVIDER=data_gov_in
    + DATA_GOV_IN_API_KEY; returns a 400-style 'not configured' message otherwise."""
    from app.services import prices_feed

    if not prices_feed.provider_configured():
        return {"configured": False,
                "message": "Live price feed not configured. Set PRICES_PROVIDER=data_gov_in "
                           "and DATA_GOV_IN_API_KEY, then try again. Showing seeded sample prices."}
    try:
        result = prices_feed.refresh_prices(db)
    except Exception as exc:  # network / upstream failure — report, don't 500
        db.rollback()
        return {"configured": True, "ok": False, "message": f"Price feed error: {exc}"}
    audit.record(db, actor_id=user.id, action="prices.refresh", object_type="system",
                 object_id="market_prices", new_values=result)
    db.commit()
    return {"configured": True, "ok": True, **result}


# --- Service areas (delivery coverage) -------------------------------------

def _state_code_for(db: Session, name: str) -> str:
    """A unique short code for a new state (existing codes are reused elsewhere)."""
    base = "".join(c for c in name.upper() if c.isalpha())[:3] or "ST"
    code, n = base, 1
    while db.scalar(select(State).where(State.code == code)):
        n += 1
        code = f"{base[:2]}{n}"
    return code


def _ensure_mandal(db: Session, state_name: str, district_name: str, mandal_name: str,
                   lat, lng, *, serviceable: bool = True, state_code: str | None = None):
    from decimal import Decimal
    state = db.scalar(select(State).where(State.name == state_name))
    if not state:
        state = State(name=state_name, code=state_code or _state_code_for(db, state_name))
        db.add(state)
        db.flush()
    district = db.scalar(select(District).where(
        District.name == district_name, District.state_id == state.id))
    if not district:
        district = District(name=district_name, state_id=state.id)
        db.add(district)
        db.flush()
    m = db.scalar(select(Mandal).where(
        Mandal.name == mandal_name, Mandal.district_id == district.id))
    created = m is None
    if created:
        m = Mandal(name=mandal_name, district_id=district.id)
        db.add(m)
    if lat is not None:
        m.latitude = Decimal(str(lat))
    if lng is not None:
        m.longitude = Decimal(str(lng))
    m.serviceable = serviceable
    db.flush()
    return m, created


@router.get("/service-areas")
def service_areas(user=Depends(_staff), db: Session = Depends(get_db)):
    """All states → districts → mandals with coverage + coordinates, for the
    superadmin coverage manager."""
    states = list(db.scalars(select(State).order_by(State.name)))
    districts = list(db.scalars(select(District).order_by(District.name)))
    mandals = list(db.scalars(select(Mandal).order_by(Mandal.name)))
    d_by_state: dict[int, list] = {}
    m_by_district: dict[int, list] = {}
    for m in mandals:
        m_by_district.setdefault(m.district_id, []).append({
            "id": m.id, "name": m.name, "serviceable": m.serviceable,
            "latitude": float(m.latitude) if m.latitude is not None else None,
            "longitude": float(m.longitude) if m.longitude is not None else None,
        })
    for d in districts:
        d_by_state.setdefault(d.state_id, []).append({
            "id": d.id, "name": d.name, "mandals": m_by_district.get(d.id, []),
        })
    return [{
        "id": s.id, "name": s.name, "code": s.code,
        "districts": d_by_state.get(s.id, []),
        "serviceable_count": sum(1 for d in d_by_state.get(s.id, [])
                                 for m in d["mandals"] if m["serviceable"]),
    } for s in states]


class MandalUpsert(BaseModel):
    state: str
    district: str
    name: str
    latitude: float | None = None
    longitude: float | None = None
    serviceable: bool = True


@router.post("/service-areas/mandal")
def add_service_mandal(body: MandalUpsert,
                       user=Depends(require_roles(Role.SUPERADMIN)),
                       db: Session = Depends(get_db)):
    """Add (or update) a single mandal's coverage + coordinates."""
    name = (body.name or "").strip()
    if not (name and body.state.strip() and body.district.strip()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "State, district and mandal name are required.")
    m, created = _ensure_mandal(db, body.state.strip(), body.district.strip(), name,
                                body.latitude, body.longitude, serviceable=body.serviceable)
    audit.record(db, actor_id=user.id, action="service_area.upsert", object_type="mandal",
                 object_id=m.id, new_values={"name": name, "serviceable": body.serviceable})
    db.commit()
    return {"id": m.id, "created": created, "serviceable": m.serviceable}


class MandalPatch(BaseModel):
    serviceable: bool | None = None
    latitude: float | None = None
    longitude: float | None = None


@router.patch("/service-areas/mandal/{mandal_id}")
def patch_service_mandal(mandal_id: int, body: MandalPatch,
                         user=Depends(require_roles(Role.SUPERADMIN)),
                         db: Session = Depends(get_db)):
    """Toggle a mandal's serviceable flag or correct its coordinates."""
    from decimal import Decimal
    m = db.get(Mandal, mandal_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mandal not found")
    if body.serviceable is not None:
        m.serviceable = body.serviceable
    if body.latitude is not None:
        m.latitude = Decimal(str(body.latitude))
    if body.longitude is not None:
        m.longitude = Decimal(str(body.longitude))
    audit.record(db, actor_id=user.id, action="service_area.patch", object_type="mandal",
                 object_id=m.id, new_values={"serviceable": m.serviceable})
    db.commit()
    return {"id": m.id, "serviceable": m.serviceable}


@router.post("/service-areas/preset/hyderabad")
def add_hyderabad_metro(user=Depends(require_roles(Role.SUPERADMIN)),
                        db: Session = Depends(get_db)):
    """One-click: add the Hyderabad metro mandals as serviceable coverage."""
    from app.core.geo_presets import HYDERABAD_METRO
    added = 0
    for state_name, code, district, mandal, lat, lng in HYDERABAD_METRO:
        _, created = _ensure_mandal(db, state_name, district, mandal, lat, lng,
                                    serviceable=True, state_code=code)
        added += 1 if created else 0
    audit.record(db, actor_id=user.id, action="service_area.preset", object_type="system",
                 object_id="hyderabad", new_values={"added": added})
    db.commit()
    return {"ok": True, "added": added, "total": len(HYDERABAD_METRO)}


@router.post("/service-areas/preset/launch")
def launch_coverage(user=Depends(require_roles(Role.SUPERADMIN)),
                    db: Session = Depends(get_db)):
    """One-click launch config: Telangana + Andhra Pradesh are LOADED into the
    coverage menu, but only the Hyderabad metro is left SERVICEABLE. Every other
    mandal is set non-serviceable, so today only Hyderabad buyers/farmers transact;
    the superadmin flips a region on (per-mandal toggle) once agents/transport are
    onboarded there."""
    from app.core.geo_presets import AP_TG_REGIONS, HYDERABAD_METRO
    hyd_ids: set[int] = set()
    for state_name, code, district, mandal, lat, lng in HYDERABAD_METRO:
        m, _ = _ensure_mandal(db, state_name, district, mandal, lat, lng,
                              serviceable=True, state_code=code)
        hyd_ids.add(m.id)
    loaded = 0
    for state_name, code, district, mandal, lat, lng in AP_TG_REGIONS:
        _, created = _ensure_mandal(db, state_name, district, mandal, lat, lng,
                                    serviceable=False, state_code=code)
        loaded += 1 if created else 0
    # Everything except the Hyderabad metro is inactive until a region is onboarded.
    deactivated = 0
    for m in db.scalars(select(Mandal)):
        if m.id not in hyd_ids and m.serviceable:
            m.serviceable = False
            deactivated += 1
    audit.record(db, actor_id=user.id, action="service_area.launch", object_type="system",
                 object_id="hyderabad_only",
                 new_values={"hyderabad": len(hyd_ids), "loaded": loaded, "deactivated": deactivated})
    db.commit()
    return {"ok": True, "hyderabad_active": len(hyd_ids),
            "regions_loaded": loaded, "deactivated": deactivated}


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
