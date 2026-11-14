from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.core.money import qty
from app.core.rbac import Role
from app.models.catalog import Commodity
from app.models.common import ListingStatus, OfferStatus, RFQStatus, utcnow
from app.models.location import Mandal
from app.models.marketplace import RFQ, Listing, Offer, OfferVersion, RfqComment
from app.models.user import AgentProfile, FarmerProfile, User
from app.services import notify

router = APIRouter(prefix="/rfqs", tags=["rfqs"])

# Field roles that can watch/help-source requests (and get escalations).
_AGENT_ROLES = {Role.FIELD_AGENT, Role.FIELD_LEADER, Role.FIELD_MANAGER, Role.SUPERADMIN}


def _target_mandals(rfq: RFQ) -> list[int]:
    ids = list(rfq.source_mandal_ids or [])
    if not ids and rfq.destination_mandal_id:
        ids = [rfq.destination_mandal_id]
    return [int(i) for i in ids]


def _system_comment(db: Session, rfq_id: int, body: str) -> None:
    db.add(RfqComment(rfq_id=rfq_id, author_id=None, body=body, is_system=True))


def _route_rfq(db: Session, rfq: RFQ) -> None:
    """Send the request to nearby farmers and field agents: farmers in the
    requested source areas (and anyone with an open listing for the commodity),
    plus agents whose service areas cover those mandals. Never blocks."""
    try:
        areas = set(_target_mandals(rfq))
        c = db.get(Commodity, rfq.commodity_id)
        cname = c.name if c else "a product"
        want = f"{qty(rfq.requested_qty)} {rfq.unit} of {cname}"

        farmer_ids: set[int] = set(db.scalars(select(Listing.seller_id).where(
            Listing.commodity_id == rfq.commodity_id,
            Listing.status == str(ListingStatus.OPEN),
        )))
        if areas:
            farmer_ids |= set(db.scalars(
                select(FarmerProfile.user_id).where(FarmerProfile.mandal_id.in_(areas))))
        farmer_ids.discard(rfq.buyer_id)
        for sid in farmer_ids:
            notify.send(db, user_id=sid, title=f"New buyer request: {cname}",
                        body=f"A buyer near you wants {want}. Offer into it.",
                        object_type="rfq", object_id=rfq.id)

        # Agents whose service_mandals intersect the requested areas (all agents
        # if no area was given), so they can help source it.
        agents = db.scalars(select(AgentProfile))
        for ap in agents:
            svc = set(ap.service_mandals or [])
            if not areas or (svc & areas) or not svc:
                notify.send(db, user_id=ap.user_id, title=f"Buyer request to help source: {cname}",
                            body=f"A buyer wants {want}. Help connect a farmer.",
                            object_type="rfq", object_id=rfq.id)
    except Exception:
        pass  # alerts must never block RFQ creation


def _can_view_thread(user: User, rfq: RFQ) -> bool:
    return (user.id == rfq.buyer_id or user.role == str(Role.FARMER)
            or user.role in {str(r) for r in _AGENT_ROLES})


# A farmer shops with the same login they sell with, so they can post buyer
# requirements (RFQs) too — alongside household and business buyers.
_buyer = require_roles(Role.FARMER, Role.BUYER_HOUSEHOLD, Role.BUYER_BUSINESS)
_seller = require_roles(Role.FARMER)


class RFQCreate(BaseModel):
    commodity_id: int
    variety_id: int | None = None
    grade_spec_id: int | None = None
    requested_qty: float = Field(gt=0)
    unit: str = "kg"
    target_price: float | None = None
    price_min: float | None = None
    price_max: float | None = None
    source_mandal_ids: list[int] | None = None
    destination_mandal_id: int | None = None
    delivery_window: str | None = None
    packaging: str | None = None
    note: str | None = None  # buyer's opening comment on the thread
    acceptable_variation: dict | None = None
    inspection_required: bool = True


class RfqCommentBody(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class RFQOffer(BaseModel):
    price_per_unit: float = Field(gt=0)
    quantity: float = Field(gt=0)
    grade_spec_id: int | None = None
    delivery_terms: dict | None = None
    inspection_conditions: dict | None = None
    ttl_hours: int = 48


def _rfq_json(r: RFQ, db: Session | None = None) -> dict:
    out = {
        "id": r.id,
        "buyer_id": r.buyer_id,
        "commodity_id": r.commodity_id,
        "variety_id": r.variety_id,
        "grade_spec_id": r.grade_spec_id,
        "requested_qty": str(qty(r.requested_qty)),
        "unit": r.unit,
        "target_price": None if r.target_price is None else str(r.target_price),
        "price_min": None if r.price_min is None else str(r.price_min),
        "price_max": None if r.price_max is None else str(r.price_max),
        "source_mandal_ids": r.source_mandal_ids or [],
        "destination_mandal_id": r.destination_mandal_id,
        "delivery_window": r.delivery_window,
        "packaging": r.packaging,
        "inspection_required": r.inspection_required,
        "status": r.status,
        "escalated": r.escalated,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
    if db is not None:
        ids = r.source_mandal_ids or []
        if ids:
            names = {m.id: m.name for m in db.scalars(select(Mandal).where(Mandal.id.in_(ids)))}
            out["source_mandals"] = [names.get(i) for i in ids if names.get(i)]
        else:
            out["source_mandals"] = []
        out["comment_count"] = db.scalar(
            select(RfqComment.id).where(RfqComment.rfq_id == r.id).limit(1)) is not None
    return out


@router.post("", status_code=status.HTTP_201_CREATED)
def create_rfq(body: RFQCreate, user: User = Depends(_buyer), db: Session = Depends(get_db)):
    rfq = RFQ(
        buyer_id=user.id,
        commodity_id=body.commodity_id,
        variety_id=body.variety_id,
        grade_spec_id=body.grade_spec_id,
        requested_qty=qty(body.requested_qty),
        unit=body.unit,
        target_price=body.target_price if body.target_price is not None else body.price_max,
        price_min=body.price_min,
        price_max=body.price_max,
        source_mandal_ids=[int(i) for i in (body.source_mandal_ids or [])] or None,
        destination_mandal_id=body.destination_mandal_id,
        delivery_window=body.delivery_window,
        packaging=body.packaging,
        acceptable_variation=body.acceptable_variation,
        inspection_required=body.inspection_required,
        status=RFQStatus.OPEN,
    )
    db.add(rfq)
    db.flush()
    # Activity thread: opening system entry + the buyer's optional note.
    band = ""
    if body.price_min is not None or body.price_max is not None:
        band = f" at ₹{body.price_min or '?'}–{body.price_max or '?'}/{rfq.unit}"
    _system_comment(db, rfq.id, f"Request raised for {qty(rfq.requested_qty)} {rfq.unit}{band}.")
    if body.note and body.note.strip():
        db.add(RfqComment(rfq_id=rfq.id, author_id=user.id, body=body.note.strip()))
    _route_rfq(db, rfq)
    db.commit()
    db.refresh(rfq)
    return _rfq_json(rfq, db)


@router.get("")
def search_rfqs(
    commodity_id: int | None = None,
    mandal_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Open RFQs sellers can offer into."""
    stmt = select(RFQ).where(RFQ.status == RFQStatus.OPEN)
    if commodity_id:
        stmt = stmt.where(RFQ.commodity_id == commodity_id)
    if mandal_id:
        stmt = stmt.where(RFQ.destination_mandal_id == mandal_id)
    return [_rfq_json(r, db) for r in db.scalars(stmt.order_by(RFQ.created_at.desc()))]


@router.get("/mine")
def my_rfqs(user: User = Depends(_buyer), db: Session = Depends(get_db)):
    rows = db.scalars(select(RFQ).where(RFQ.buyer_id == user.id).order_by(RFQ.created_at.desc()))
    return [_rfq_json(r, db) for r in rows]


@router.get("/{rfq_id}")
def get_rfq(rfq_id: int, db: Session = Depends(get_db)):
    rfq = db.get(RFQ, rfq_id)
    if not rfq:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "RFQ not found")
    return _rfq_json(rfq, db)


@router.get("/{rfq_id}/comments")
def list_comments(rfq_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Shared request thread: system activity + comments from the buyer, farmers
    and field staff, so every action is visible to everyone involved."""
    rfq = db.get(RFQ, rfq_id)
    if not rfq:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "RFQ not found")
    if not _can_view_thread(user, rfq):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed to view this request")
    rows = list(db.scalars(select(RfqComment).where(RfqComment.rfq_id == rfq_id)
                           .order_by(RfqComment.id)))
    names = {u.id: (u.name or u.phone, u.role)
             for u in db.scalars(select(User).where(
                 User.id.in_([c.author_id for c in rows if c.author_id])))}
    out = []
    for c in rows:
        nm, role = names.get(c.author_id, (None, None))
        out.append({
            "id": c.id, "body": c.body, "is_system": c.is_system,
            "author_id": c.author_id, "author_name": "System" if c.is_system else nm,
            "author_role": role,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })
    return out


@router.post("/{rfq_id}/comments", status_code=status.HTTP_201_CREATED)
def add_comment(rfq_id: int, body: RfqCommentBody, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    rfq = db.get(RFQ, rfq_id)
    if not rfq:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "RFQ not found")
    if not _can_view_thread(user, rfq):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed to comment on this request")
    c = RfqComment(rfq_id=rfq_id, author_id=user.id, body=body.body.strip())
    db.add(c)
    # Notify the request owner (unless they wrote it themselves).
    if user.id != rfq.buyer_id:
        notify.send(db, user_id=rfq.buyer_id, title="New comment on your request",
                    body=f"{user.name or 'Someone'}: {body.body.strip()[:80]}",
                    object_type="rfq", object_id=rfq.id)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "body": c.body, "is_system": False,
            "author_id": user.id, "author_name": user.name or user.phone,
            "author_role": user.role,
            "created_at": c.created_at.isoformat() if c.created_at else None}


@router.post("/{rfq_id}/cancel")
def cancel_rfq(rfq_id: int, user: User = Depends(_buyer), db: Session = Depends(get_db)):
    rfq = db.get(RFQ, rfq_id)
    if not rfq:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "RFQ not found")
    if rfq.buyer_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your RFQ")
    if rfq.status != RFQStatus.OPEN:
        raise HTTPException(status.HTTP_409_CONFLICT, "RFQ is not open")
    rfq.status = RFQStatus.CANCELLED
    db.commit()
    return _rfq_json(rfq)


@router.post("/{rfq_id}/offers", status_code=status.HTTP_201_CREATED)
def offer_into_rfq(
    rfq_id: int, body: RFQOffer, user: User = Depends(_seller), db: Session = Depends(get_db)
):
    """A seller proposes into an open RFQ, opening a negotiation thread (version 1).

    The buyer then counters/accepts via the standard /offers endpoints.
    """
    from app.api.offers import _offer_json  # shared serializer

    rfq = db.get(RFQ, rfq_id)
    if not rfq or rfq.status != RFQStatus.OPEN:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "RFQ not open")
    if rfq.buyer_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot offer on your own RFQ")

    offer = Offer(
        rfq_id=rfq.id,
        buyer_id=rfq.buyer_id,
        seller_id=user.id,
        status=OfferStatus.OPEN,
    )
    db.add(offer)
    db.flush()
    now = utcnow()
    db.add(
        OfferVersion(
            offer_id=offer.id,
            version_no=1,
            proposer_role="seller",
            proposer_id=user.id,
            price_per_unit=body.price_per_unit,
            quantity=qty(body.quantity),
            unit=rfq.unit,
            grade_spec_id=body.grade_spec_id or rfq.grade_spec_id,
            delivery_terms=body.delivery_terms,
            inspection_conditions=body.inspection_conditions,
            expires_at=now + timedelta(hours=body.ttl_hours),
            created_at=now,
        )
    )
    _system_comment(db, rfq.id,
                    f"{user.name or 'A farmer'} offered ₹{body.price_per_unit}/{rfq.unit} "
                    f"for {qty(body.quantity)} {rfq.unit}.")
    notify.send(db, user_id=rfq.buyer_id, title="You received an offer",
                body=f"{user.name or 'A farmer'} offered on your request.",
                object_type="rfq", object_id=rfq.id)
    db.commit()
    db.refresh(offer)
    return _offer_json(offer, db)
