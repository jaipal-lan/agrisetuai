"""FPO (Farmer Producer Organisation) — group management for the FPO lead.

An FPO is modelled as an ``Organisation(type="fpo")``. The ``fpo``-role user who
owns it is the group lead; member farmers share the lead's ``organisation_id``.
The lead gets a *pooled, read-only* view (members + their listings / orders /
earnings) and can add or remove members. Members keep their own accounts —
listings and orders stay owned by the member who created them; the FPO view only
aggregates. A member can still log in and trade on their own.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.money import money
from app.core.rbac import Role
from app.models.common import OrderStatus as OS
from app.models.finance import Payout
from app.models.marketplace import Listing
from app.models.order import Order
from app.models.user import FarmerProfile, Organisation, User
from app.services import audit

router = APIRouter(prefix="/fpo", tags=["fpo"])

_PHONE_OK = {10, 11, 12}
_TERMINAL = (OS.SETTLED, OS.CANCELLED, OS.REFUNDED)
_EARNED = (OS.COMPLETED, OS.SETTLED, OS.PARTIALLY_REFUNDED, OS.REFUNDED)

# Only the group lead reaches these endpoints.
_lead = require_roles(Role.FPO)


class AddMember(BaseModel):
    phone: str = Field(min_length=8, max_length=15)
    name: str | None = None
    village: str | None = None


def _ensure_org(db: Session, lead: User) -> Organisation:
    """Return the lead's FPO org, creating it lazily for pre-existing fpo users."""
    if lead.organisation_id:
        org = db.get(Organisation, lead.organisation_id)
        if org:
            return org
    org = Organisation(type="fpo", legal_name=(lead.name or "Farmer group"))
    db.add(org)
    db.flush()
    lead.organisation_id = org.id
    db.commit()
    db.refresh(org)
    return org


def _org_user_ids(db: Session, org_id: int) -> list[int]:
    return list(db.scalars(select(User.id).where(User.organisation_id == org_id)))


def _seller_stats(db: Session, seller_ids: list[int]) -> dict:
    """Pooled seller figures across a set of member sellers."""
    if not seller_ids:
        return {"active_listings": 0, "orders_in_progress": 0,
                "gross_settled": "0.00", "awaiting_payout": "0.00"}
    active_listings = db.scalar(select(func.count(Listing.id)).where(
        Listing.seller_id.in_(seller_ids), Listing.status == "open")) or 0
    orders_in_progress = db.scalar(select(func.count(Order.id)).where(
        Order.seller_id.in_(seller_ids), Order.status.not_in(_TERMINAL))) or 0
    gross = money(0)
    for o in db.scalars(select(Order).where(Order.seller_id.in_(seller_ids), Order.status == OS.SETTLED)):
        q = o.quote or {}
        t = o.accepted_terms or {}
        gross += money(q.get("product_value") or (float(t.get("price_per_unit", 0)) * float(t.get("quantity", 0))))
    awaiting = money(0)
    for p in db.scalars(select(Payout).where(Payout.seller_id.in_(seller_ids), Payout.status == "pending")):
        awaiting += money(p.amount)
    return {"active_listings": active_listings, "orders_in_progress": orders_in_progress,
            "gross_settled": str(gross), "awaiting_payout": str(awaiting)}


def _member_row(db: Session, u: User, is_lead: bool) -> dict:
    active = db.scalar(select(func.count(Listing.id)).where(
        Listing.seller_id == u.id, Listing.status == "open")) or 0
    in_progress = db.scalar(select(func.count(Order.id)).where(
        Order.seller_id == u.id, Order.status.not_in(_TERMINAL))) or 0
    fp = u.farmer_profile
    return {
        "id": u.id,
        "name": u.name or "—",
        "phone": u.phone,  # lead manages their own members, so full phone is shown
        "village": fp.village if fp else None,
        "verification_status": fp.verification_status if fp else "unverified",
        "onboarding_complete": u.onboarding_complete,
        "active_listings": active,
        "orders_in_progress": in_progress,
        "is_lead": is_lead,
        "status": u.status,
    }


@router.get("")
def overview(lead: User = Depends(_lead), db: Session = Depends(get_db)):
    org = _ensure_org(db, lead)
    members = list(db.scalars(
        select(User).where(User.organisation_id == org.id).order_by(User.id)
    ))
    ids = [m.id for m in members]
    rows = [_member_row(db, m, is_lead=(m.id == lead.id)) for m in members]
    rows.sort(key=lambda r: (not r["is_lead"], r["name"].lower()))
    return {
        "organisation": {
            "id": org.id,
            "legal_name": org.legal_name,
            "verification_status": org.verification_status,
        },
        "member_count": len(ids),
        "pooled": _seller_stats(db, ids),
        "members": rows,
    }


@router.post("/members", status_code=status.HTTP_201_CREATED)
def add_member(body: AddMember, lead: User = Depends(_lead), db: Session = Depends(get_db)):
    org = _ensure_org(db, lead)
    phone = body.phone.strip()
    if not phone.isdigit() or len(phone) not in _PHONE_OK:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid phone number")

    user = db.scalar(select(User).where(User.phone == phone))
    if user is not None:
        if user.organisation_id == org.id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Already a member of this group")
        if user.organisation_id is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "This person already belongs to another organisation")
        if user.role not in (Role.FARMER, Role.FPO):
            raise HTTPException(status.HTTP_409_CONFLICT, "Only farmer accounts can join an FPO")
        user.organisation_id = org.id
        if body.name and not user.name:
            user.name = body.name
        created = False
    else:
        # Pre-register the member; they activate the account later via OTP login.
        user = User(phone=phone, role=str(Role.FARMER), name=body.name, organisation_id=org.id)
        db.add(user)
        db.flush()
        db.add(FarmerProfile(user_id=user.id, village=body.village))
        created = True

    audit.record(db, actor_id=lead.id, action="fpo.member.add", object_type="user",
                 object_id=user.id, new_values={"org": org.id, "created": created})
    db.commit()
    db.refresh(user)
    return {"created": created, "member": _member_row(db, user, is_lead=False)}


@router.delete("/members/{user_id}")
def remove_member(user_id: int, lead: User = Depends(_lead), db: Session = Depends(get_db)):
    org = _ensure_org(db, lead)
    if user_id == lead.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The group lead cannot remove themselves")
    member = db.get(User, user_id)
    if member is None or member.organisation_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a member of this group")
    member.organisation_id = None
    audit.record(db, actor_id=lead.id, action="fpo.member.remove", object_type="user",
                 object_id=user_id, new_values={"org": org.id})
    db.commit()
    return {"ok": True, "removed": user_id}


def _pooled_earnings(db: Session, seller_ids: list[int]) -> dict:
    """Per-member earnings summary + group totals (settled/completed orders)."""
    id_to_name = dict(db.execute(
        select(User.id, User.name).where(User.id.in_(seller_ids))
    ).all()) if seller_ids else {}
    payouts: dict[int, list] = {}
    if seller_ids:
        for p in db.scalars(select(Payout).where(Payout.seller_id.in_(seller_ids))):
            payouts.setdefault(p.order_id, []).append(p)

    per: dict[int, dict] = {sid: {"seller_id": sid, "name": id_to_name.get(sid) or "—",
                                  "orders": 0, "gross": money(0), "commission": money(0),
                                  "net": money(0), "paid": money(0)} for sid in seller_ids}
    g_gross = g_comm = g_net = g_paid = money(0)
    orders = db.scalars(select(Order).where(
        Order.seller_id.in_(seller_ids), Order.status.in_(_EARNED))) if seller_ids else []
    for o in orders:
        q = o.quote or {}
        t = o.accepted_terms or {}
        gross = money(q.get("product_value") or (float(t.get("price_per_unit", 0)) * float(t.get("quantity", 0))))
        comm = money(q.get("seller_commission", 0))
        net = money(o.seller_payable or (gross - comm))
        paid = money(0)
        for p in payouts.get(o.id, []):
            paid += money(p.amount)
        row = per[o.seller_id]
        row["orders"] += 1
        row["gross"] += gross; row["commission"] += comm; row["net"] += net; row["paid"] += paid
        g_gross += gross; g_comm += comm; g_net += net; g_paid += paid

    members = [{**r, "gross": str(r["gross"]), "commission": str(r["commission"]),
                "net": str(r["net"]), "paid": str(r["paid"])}
               for r in per.values()]
    members.sort(key=lambda r: float(r["net"]), reverse=True)
    return {
        "currency": "INR",
        "members": members,
        "totals": {"gross": str(g_gross), "commission": str(g_comm),
                   "net": str(g_net), "paid": str(g_paid)},
    }


@router.get("/earnings")
def group_earnings(lead: User = Depends(_lead), db: Session = Depends(get_db)):
    org = _ensure_org(db, lead)
    return _pooled_earnings(db, _org_user_ids(db, org.id))


@router.get("/earnings.csv")
def group_earnings_csv(lead: User = Depends(_lead), db: Session = Depends(get_db)):
    import csv
    import io

    from fastapi.responses import Response

    org = _ensure_org(db, lead)
    data = _pooled_earnings(db, _org_user_ids(db, org.id))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["member", "orders", "gross_inr", "commission_inr", "net_inr", "paid_inr"])
    for m in data["members"]:
        w.writerow([m["name"], m["orders"], m["gross"], m["commission"], m["net"], m["paid"]])
    tot = data["totals"]
    w.writerow(["GROUP TOTAL", "", tot["gross"], tot["commission"], tot["net"], tot["paid"]])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="agrisetu-fpo-earnings.csv"'},
    )
