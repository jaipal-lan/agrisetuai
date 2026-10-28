from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.ids import order_id as gen_order_id
from app.core.money import qty
from app.models.common import (
    ListingStatus,
    OfferStatus,
    OrderStatus,
    ensure_aware,
    utcnow,
)
from app.models.marketplace import Listing, Offer, OfferVersion
from app.models.order import Order, OrderLine
from app.models.user import User
from app.services import audit

router = APIRouter(prefix="/offers", tags=["negotiation"])

DEFAULT_OFFER_TTL = timedelta(hours=48)


class OfferCreate(BaseModel):
    listing_id: int
    price_per_unit: float = Field(gt=0)
    quantity: float = Field(gt=0)
    grade_spec_id: int | None = None
    delivery_terms: dict | None = None
    inspection_conditions: dict | None = None
    ttl_hours: int = 48


class CounterBody(BaseModel):
    price_per_unit: float = Field(gt=0)
    quantity: float = Field(gt=0)
    grade_spec_id: int | None = None
    delivery_terms: dict | None = None
    inspection_conditions: dict | None = None
    ttl_hours: int = 48


def _party_role(offer: Offer, user: User) -> str:
    if user.id == offer.buyer_id:
        return "buyer"
    if user.id == offer.seller_id:
        return "seller"
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a party to this offer")


def _version_json(v: OfferVersion) -> dict:
    return {
        "id": v.id,
        "version_no": v.version_no,
        "proposer_role": v.proposer_role,
        "price_per_unit": str(v.price_per_unit),
        "quantity": str(qty(v.quantity)),
        "unit": v.unit,
        "grade_spec_id": v.grade_spec_id,
        "delivery_terms": v.delivery_terms,
        "inspection_conditions": v.inspection_conditions,
        "expires_at": v.expires_at.isoformat(),
        "created_at": v.created_at.isoformat(),
    }


def _offer_json(offer: Offer, db: Session) -> dict:
    versions = db.scalars(
        select(OfferVersion)
        .where(OfferVersion.offer_id == offer.id)
        .order_by(OfferVersion.version_no)
    )
    return {
        "id": offer.id,
        "listing_id": offer.listing_id,
        "rfq_id": offer.rfq_id,
        "buyer_id": offer.buyer_id,
        "seller_id": offer.seller_id,
        "status": offer.status,
        "accepted_version_id": offer.accepted_version_id,
        "versions": [_version_json(v) for v in versions],
    }


def _latest(offer: Offer, db: Session) -> OfferVersion:
    return db.scalars(
        select(OfferVersion)
        .where(OfferVersion.offer_id == offer.id)
        .order_by(OfferVersion.version_no.desc())
    ).first()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_offer(
    body: OfferCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """A buyer opens a negotiation thread against an open listing (version 1)."""
    listing = db.get(Listing, body.listing_id)
    if not listing or listing.status != ListingStatus.OPEN:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not open")
    if listing.seller_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot offer on own listing")
    if qty(body.quantity) > qty(listing.available_qty):
        raise HTTPException(status.HTTP_409_CONFLICT, "Quantity exceeds available")
    if listing.min_order_qty and qty(body.quantity) < qty(listing.min_order_qty):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Below minimum order quantity")

    offer = Offer(
        listing_id=listing.id,
        buyer_id=user.id,
        seller_id=listing.seller_id,
        status=OfferStatus.OPEN,
    )
    db.add(offer)
    db.flush()
    now = utcnow()
    v = OfferVersion(
        offer_id=offer.id,
        version_no=1,
        proposer_role="buyer",
        proposer_id=user.id,
        price_per_unit=body.price_per_unit,
        quantity=qty(body.quantity),
        unit=listing.unit,
        grade_spec_id=body.grade_spec_id or listing.grade_spec_id,
        delivery_terms=body.delivery_terms,
        inspection_conditions=body.inspection_conditions,
        expires_at=now + timedelta(hours=body.ttl_hours),
        created_at=now,
    )
    db.add(v)
    db.commit()
    db.refresh(offer)
    return _offer_json(offer, db)


@router.get("")
def my_offers(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """All negotiation threads where the caller is the buyer or the seller."""
    from sqlalchemy import or_

    rows = db.scalars(
        select(Offer)
        .where(or_(Offer.buyer_id == user.id, Offer.seller_id == user.id))
        .order_by(Offer.created_at.desc())
    )
    return [_offer_json(o, db) for o in rows]


@router.get("/{offer_id}")
def get_offer(offer_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")
    _party_role(offer, user)
    return _offer_json(offer, db)


@router.get("/{offer_id}/history")
def offer_history(offer_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")
    _party_role(offer, user)
    return _offer_json(offer, db)["versions"]


@router.post("/{offer_id}/counter")
def counter(
    offer_id: int,
    body: CounterBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")
    role = _party_role(offer, user)
    if offer.status not in (OfferStatus.OPEN, OfferStatus.COUNTERED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Offer is closed")

    latest = _latest(offer, db)
    # Only the side that did NOT make the latest proposal may counter it.
    if latest.proposer_role == role:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Awaiting the other party's response"
        )
    if ensure_aware(latest.expires_at) < utcnow():
        offer.status = OfferStatus.EXPIRED
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "Latest offer has expired")

    # Re-validate against live listing availability for the new quantity.
    listing = db.get(Listing, offer.listing_id) if offer.listing_id else None
    if listing and qty(body.quantity) > qty(listing.available_qty):
        raise HTTPException(status.HTTP_409_CONFLICT, "Quantity exceeds available")

    now = utcnow()
    v = OfferVersion(
        offer_id=offer.id,
        version_no=latest.version_no + 1,
        proposer_role=role,
        proposer_id=user.id,
        price_per_unit=body.price_per_unit,
        quantity=qty(body.quantity),
        unit=latest.unit,
        grade_spec_id=body.grade_spec_id if body.grade_spec_id is not None else latest.grade_spec_id,
        delivery_terms=body.delivery_terms if body.delivery_terms is not None else latest.delivery_terms,
        inspection_conditions=body.inspection_conditions
        if body.inspection_conditions is not None
        else latest.inspection_conditions,
        expires_at=now + timedelta(hours=body.ttl_hours),
        created_at=now,
    )
    db.add(v)
    offer.status = OfferStatus.OPEN  # awaiting the original proposer now
    db.commit()
    db.refresh(offer)
    return _offer_json(offer, db)


@router.post("/{offer_id}/reject")
def reject(offer_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")
    _party_role(offer, user)
    if offer.status not in (OfferStatus.OPEN, OfferStatus.COUNTERED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Offer is closed")
    offer.status = OfferStatus.REJECTED
    db.commit()
    return _offer_json(offer, db)


@router.post("/{offer_id}/accept")
def accept(offer_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Accept the latest version. Creates a provisional order and reserves stock.

    Only the party that did not make the latest proposal can accept it.
    """
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")
    role = _party_role(offer, user)
    if offer.status not in (OfferStatus.OPEN, OfferStatus.COUNTERED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Offer is closed")

    latest = _latest(offer, db)
    if latest.proposer_role == role:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You cannot accept your own proposal"
        )
    if ensure_aware(latest.expires_at) < utcnow():
        offer.status = OfferStatus.EXPIRED
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "Offer has expired")

    listing = db.get(Listing, offer.listing_id) if offer.listing_id else None
    accepted_qty = qty(latest.quantity)

    if listing is not None:
        # Reserve against live availability; prevent overselling. The row lock is a
        # no-op on SQLite (dev) but real on Postgres (prod).
        fresh = db.get(Listing, listing.id, with_for_update=True)
        if accepted_qty > qty(fresh.available_qty):
            raise HTTPException(status.HTTP_409_CONFLICT, "Quantity no longer available")
        fresh.reserved_qty = qty(fresh.reserved_qty) + accepted_qty
        if qty(fresh.available_qty) <= 0:
            fresh.status = ListingStatus.SOLD_OUT

    # Snapshot the exact accepted terms into the order (immutable record).
    accepted_terms = {
        "offer_version_id": latest.id,
        "version_no": latest.version_no,
        "price_per_unit": str(latest.price_per_unit),
        "quantity": str(accepted_qty),
        "unit": latest.unit,
        "grade_spec_id": latest.grade_spec_id,
        "delivery_terms": latest.delivery_terms,
        "inspection_conditions": latest.inspection_conditions,
    }

    order = Order(
        public_id=gen_order_id(),
        buyer_id=offer.buyer_id,
        seller_id=offer.seller_id,
        offer_id=offer.id,
        status=OrderStatus.PROVISIONAL_AGREEMENT,
        accepted_terms=accepted_terms,
    )
    db.add(order)
    db.flush()
    db.add(
        OrderLine(
            order_id=order.id,
            listing_id=offer.listing_id,
            quantity=accepted_qty,
            price_per_unit=latest.price_per_unit,
            unit=latest.unit,
            grade_spec_id=latest.grade_spec_id,
            allocation_status="reserved",
        )
    )

    offer.status = OfferStatus.ACCEPTED
    offer.accepted_version_id = latest.id
    audit.record(
        db,
        actor_id=user.id,
        action="offer.accept",
        object_type="offer",
        object_id=offer.id,
        new_values={"order_public_id": order.public_id, "accepted_terms": accepted_terms},
    )
    db.commit()
    db.refresh(order)
    return {
        "offer": _offer_json(offer, db),
        "order": {
            "id": order.id,
            "public_id": order.public_id,
            "status": order.status,
            "accepted_terms": order.accepted_terms,
        },
    }
