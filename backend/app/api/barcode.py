"""Barcode/QR bag tracking endpoints.

Bags belong to a confirmed order. Each physical bag is scanned at four stages
(pickup -> collection -> loading -> delivery); every scan is validated (invalid /
duplicate / out-of-sequence), logged immutably, advances the bag status, and
notifies the farmer + buyer. A public endpoint lets anyone track by code with no
personal data, and the superadmin can audit and manually correct.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.core.money import qty
from app.core.rbac import Role
from app.models.barcode import Bag, BagScan
from app.models.catalog import Commodity
from app.models.common import utcnow
from app.models.order import Order
from app.models.user import FarmerProfile, User
from app.services import audit, notify

router = APIRouter(tags=["barcode"])

# stage -> status it advances the bag to, and the status it requires first.
STAGE_STATUS = {"pickup": "picked_up", "collection": "at_collection",
                "loading": "in_transit", "delivery": "delivered"}
STAGE_PREV = {"pickup": "created", "collection": "picked_up",
              "loading": "at_collection", "delivery": "in_transit"}
STAGE_LABEL = {"pickup": "Picked up from farmer", "collection": "Reached collection centre",
               "loading": "Loaded — in transit", "delivery": "Delivered"}
STATUS_LABEL = {"created": "Created", "picked_up": "Picked up from farmer",
                "at_collection": "At collection centre", "in_transit": "In transit",
                "delivered": "Delivered"}
STATUS_FLOW = ["created", "picked_up", "at_collection", "in_transit", "delivered"]
_STAFF = {Role.FIELD_LEADER, Role.FIELD_MANAGER, Role.SUPERADMIN}
STAGE_ROLES = {
    "pickup": {Role.FIELD_AGENT, Role.FIELD_LEADER, Role.FIELD_MANAGER, Role.SUPERADMIN},
    "collection": {Role.FIELD_LEADER, Role.FIELD_MANAGER, Role.SUPERADMIN},
    "loading": {Role.TRANSPORT, Role.FIELD_MANAGER, Role.SUPERADMIN},
    "delivery": {Role.TRANSPORT, Role.FIELD_MANAGER, Role.SUPERADMIN},
}

_manage = require_roles(Role.FIELD_AGENT, Role.FIELD_LEADER, Role.FIELD_MANAGER, Role.SUPERADMIN)
_super = require_roles(Role.SUPERADMIN, Role.FIELD_MANAGER)


class BagGenBody(BaseModel):
    count: int = Field(ge=1, le=200)
    weights: list[float] | None = None


class ScanBody(BaseModel):
    bag_code: str
    stage: str
    lat: float | None = None
    lng: float | None = None
    note: str | None = None


class CorrectBody(BaseModel):
    to_status: str
    reason: str = Field(min_length=3, max_length=300)


def _bag_json(b: Bag) -> dict:
    return {
        "id": b.id, "bag_code": b.bag_code, "order_id": b.order_id,
        "farmer_id": b.farmer_id, "agent_id": b.agent_id, "commodity_id": b.commodity_id,
        "bag_no": b.bag_no, "weight": None if b.weight is None else str(qty(b.weight)),
        "status": b.status, "status_label": STATUS_LABEL.get(b.status, b.status),
        "last_scan_at": b.last_scan_at,
    }


def _scan_json(s: BagScan, names: dict) -> dict:
    return {
        "id": s.id, "stage": s.stage, "to_status": s.to_status,
        "status_label": STATUS_LABEL.get(s.to_status, s.to_status),
        "scanned_by": s.scanned_by, "scanned_by_name": names.get(s.scanned_by),
        "role": s.role, "lat": None if s.lat is None else float(s.lat),
        "lng": None if s.lng is None else float(s.lng), "note": s.note,
        "corrected": s.corrected, "correction_reason": s.correction_reason,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


_VIEW_ROLES = {str(Role.FIELD_AGENT), str(Role.FIELD_LEADER), str(Role.FIELD_MANAGER),
               str(Role.SUPERADMIN), str(Role.TRANSPORT)}


def _can_view(user: User, order: Order, bag: Bag) -> bool:
    return user.role in _VIEW_ROLES or user.id in {order.buyer_id, order.seller_id, bag.agent_id}


def _notify_scan(db: Session, bag: Bag, order: Order, label: str) -> None:
    when = utcnow().strftime("%d-%m-%Y %H:%M")
    msg = f"{bag.bag_code} — {label} at {when}"
    for uid in {bag.farmer_id, order.buyer_id, bag.agent_id}:
        if uid:
            notify.send(db, user_id=uid, title="Shipment update", body=msg,
                        object_type="order", object_id=order.id)


@router.post("/orders/{order_id}/bags", status_code=status.HTTP_201_CREATED)
def generate_bags(order_id: int, body: BagGenBody, user: User = Depends(_manage),
                  db: Session = Depends(get_db)):
    """Generate N barcoded bags for an order (idempotent: returns existing bags
    if already generated)."""
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    existing = list(db.scalars(select(Bag).where(Bag.order_id == order_id).order_by(Bag.bag_no)))
    if existing:
        return [_bag_json(b) for b in existing]
    commodity_id = (order.accepted_terms or {}).get("commodity_id")
    bags = []
    for i in range(1, body.count + 1):
        w = None
        if body.weights and i - 1 < len(body.weights):
            w = qty(body.weights[i - 1])
        b = Bag(bag_code=f"AGRI-{order.id}-BAG-{i:02d}", order_id=order.id,
                farmer_id=order.seller_id, agent_id=order.assigned_agent_id,
                commodity_id=commodity_id, bag_no=i, weight=w, status="created")
        db.add(b)
        bags.append(b)
    audit.record(db, actor_id=user.id, action="bag.generate", object_type="order",
                 object_id=order.id, new_values={"count": body.count})
    db.commit()
    for b in bags:
        db.refresh(b)
    return [_bag_json(b) for b in bags]


@router.get("/orders/{order_id}/bags")
def list_order_bags(order_id: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    bags = list(db.scalars(select(Bag).where(Bag.order_id == order_id).order_by(Bag.bag_no)))
    if bags and not _can_view(user, order, bags[0]):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed")
    return [_bag_json(b) for b in bags]


@router.post("/bags/scan")
def scan_bag(body: ScanBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stage = body.stage.strip().lower()
    if stage not in STAGE_STATUS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown scan stage")
    if Role(user.role) not in STAGE_ROLES[stage]:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"Your role can't scan at the {stage} stage")
    bag = db.scalar(select(Bag).where(Bag.bag_code == body.bag_code.strip()))
    if not bag:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid barcode — not found")
    new_status = STAGE_STATUS[stage]
    # Duplicate: already at this stage's status.
    if bag.status == new_status:
        last = db.scalar(select(BagScan).where(BagScan.bag_id == bag.id, BagScan.to_status == new_status)
                         .order_by(BagScan.id.desc()))
        who = db.get(User, last.scanned_by) if last and last.scanned_by else None
        when = last.created_at.strftime("%d-%m-%Y %H:%M") if last and last.created_at else "earlier"
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Already scanned ({STATUS_LABEL[new_status]}) at {when}"
                            + (f" by {who.name}" if who and who.name else ""))
    # Out of sequence.
    if bag.status != STAGE_PREV[stage]:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Out of sequence — bag is '{STATUS_LABEL.get(bag.status, bag.status)}'. "
                            f"Expected '{STATUS_LABEL[STAGE_PREV[stage]]}' before {stage}.")
    order = db.get(Order, bag.order_id)
    now = utcnow()
    db.add(BagScan(bag_id=bag.id, stage=stage, to_status=new_status, scanned_by=user.id,
                   role=user.role, lat=body.lat, lng=body.lng, note=(body.note or None)))
    bag.status = new_status
    bag.last_scan_at = now.isoformat()
    bag.last_lat = body.lat
    bag.last_lng = body.lng
    _notify_scan(db, bag, order, STAGE_LABEL[stage])
    audit.record(db, actor_id=user.id, action="bag.scan", object_type="bag",
                 object_id=bag.id, new_values={"stage": stage, "status": new_status})
    db.commit()
    db.refresh(bag)
    return {"ok": True, "message": f"{bag.bag_code}: {STAGE_LABEL[stage]}", "bag": _bag_json(bag)}


@router.get("/bags/stats")
def bag_stats(user: User = Depends(_super), db: Session = Depends(get_db)):
    """Dashboard tiles: scanned today, in transit, delivered, total."""
    today = utcnow().date()
    scans = db.scalars(select(BagScan))
    scanned_today = sum(1 for s in scans if s.created_at and s.created_at.date() == today)
    bags = list(db.scalars(select(Bag)))
    return {
        "total": len(bags),
        "scanned_today": scanned_today,
        "in_transit": sum(1 for b in bags if b.status == "in_transit"),
        "at_collection": sum(1 for b in bags if b.status == "at_collection"),
        "picked_up": sum(1 for b in bags if b.status == "picked_up"),
        "delivered": sum(1 for b in bags if b.status == "delivered"),
        "created": sum(1 for b in bags if b.status == "created"),
    }


@router.get("/bags")
def audit_bags(status_filter: str | None = Query(None, alias="status"),
               order_id: int | None = None, q: str | None = None, limit: int = 200,
               user: User = Depends(_super), db: Session = Depends(get_db)):
    """SuperAdmin/manager audit list of bags, filterable by status/order/code."""
    stmt = select(Bag)
    if status_filter:
        stmt = stmt.where(Bag.status == status_filter)
    if order_id:
        stmt = stmt.where(Bag.order_id == order_id)
    if q:
        stmt = stmt.where(Bag.bag_code.ilike(f"%{q.strip()}%"))
    rows = list(db.scalars(stmt.order_by(Bag.id.desc()).limit(limit)))
    return [_bag_json(b) for b in rows]


@router.get("/bags/{bag_code}")
def bag_detail(bag_code: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bag = db.scalar(select(Bag).where(Bag.bag_code == bag_code.strip()))
    if not bag:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bag not found")
    order = db.get(Order, bag.order_id)
    if not _can_view(user, order, bag):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed")
    scans = list(db.scalars(select(BagScan).where(BagScan.bag_id == bag.id).order_by(BagScan.id)))
    names = {u.id: u.name for u in db.scalars(select(User).where(
        User.id.in_([s.scanned_by for s in scans if s.scanned_by])))}
    out = _bag_json(bag)
    out["order_public_id"] = order.public_id if order else None
    out["scans"] = [_scan_json(s, names) for s in scans]
    return out


@router.post("/bags/{bag_code}/correct")
def correct_bag(bag_code: str, body: CorrectBody, user: User = Depends(require_roles(Role.SUPERADMIN)),
                db: Session = Depends(get_db)):
    """SuperAdmin manual status correction when a scan failed. Logged, not silent."""
    if body.to_status not in STATUS_FLOW:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown status")
    bag = db.scalar(select(Bag).where(Bag.bag_code == bag_code.strip()))
    if not bag:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bag not found")
    bag.status = body.to_status
    bag.last_scan_at = utcnow().isoformat()
    db.add(BagScan(bag_id=bag.id, stage="correction", to_status=body.to_status,
                   scanned_by=user.id, role=user.role, corrected=True,
                   correction_reason=body.reason.strip(),
                   note=f"Corrected by SuperAdmin — {body.reason.strip()}"))
    audit.record(db, actor_id=user.id, action="bag.correct", object_type="bag",
                 object_id=bag.id, new_values={"to_status": body.to_status, "reason": body.reason.strip()})
    db.commit()
    db.refresh(bag)
    return _bag_json(bag)


@router.get("/track/{code}")
def public_track(code: str, db: Session = Depends(get_db)):
    """PUBLIC — no login. Track a bag by code with no personal data (only crop +
    village + status timeline)."""
    bag = db.scalar(select(Bag).where(Bag.bag_code == code.strip()))
    if not bag:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No shipment found for this code")
    order = db.get(Order, bag.order_id)
    commodity = db.get(Commodity, bag.commodity_id) if bag.commodity_id else None
    fp = db.scalar(select(FarmerProfile).where(FarmerProfile.user_id == bag.farmer_id))
    scans = list(db.scalars(select(BagScan).where(BagScan.bag_id == bag.id).order_by(BagScan.id)))
    timeline = [{"status": s.to_status, "label": STATUS_LABEL.get(s.to_status, s.to_status),
                 "at": s.created_at.isoformat() if s.created_at else None} for s in scans]
    # Full ladder with reached/pending, so the UI can show a progress bar.
    reached = {s.to_status for s in scans} | {"created"}
    ladder = [{"status": st, "label": STATUS_LABEL[st], "reached": st in reached} for st in STATUS_FLOW]
    return {
        "bag_code": bag.bag_code,
        "order_public_id": order.public_id if order else None,
        "crop": commodity.name if commodity else None,
        "village": fp.village if fp else None,
        "status": bag.status,
        "status_label": STATUS_LABEL.get(bag.status, bag.status),
        "ladder": ladder,
        "timeline": timeline,
    }
