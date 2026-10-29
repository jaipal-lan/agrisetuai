from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.core.money import qty
from app.core.rbac import Role
from app.models.common import OfferStatus, RFQStatus, utcnow
from app.models.marketplace import RFQ, Offer, OfferVersion
from app.models.user import User

router = APIRouter(prefix="/rfqs", tags=["rfqs"])

_buyer = require_roles(Role.BUYER_HOUSEHOLD, Role.BUYER_BUSINESS)
_seller = require_roles(Role.FARMER, Role.FPO)


class RFQCreate(BaseModel):
    commodity_id: int
    variety_id: int | None = None
    grade_spec_id: int | None = None
    requested_qty: float = Field(gt=0)
    unit: str = "kg"
    target_price: float | None = None
    destination_mandal_id: int | None = None
    delivery_window: str | None = None
    packaging: str | None = None
    acceptable_variation: dict | None = None
    inspection_required: bool = True


class RFQOffer(BaseModel):
    price_per_unit: float = Field(gt=0)
    quantity: float = Field(gt=0)
    grade_spec_id: int | None = None
    delivery_terms: dict | None = None
    inspection_conditions: dict | None = None
    ttl_hours: int = 48


def _rfq_json(r: RFQ) -> dict:
    return {
        "id": r.id,
        "buyer_id": r.buyer_id,
        "commodity_id": r.commodity_id,
        "variety_id": r.variety_id,
        "grade_spec_id": r.grade_spec_id,
        "requested_qty": str(qty(r.requested_qty)),
        "unit": r.unit,
        "target_price": None if r.target_price is None else str(r.target_price),
        "destination_mandal_id": r.destination_mandal_id,
        "delivery_window": r.delivery_window,
        "packaging": r.packaging,
        "inspection_required": r.inspection_required,
        "status": r.status,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_rfq(body: RFQCreate, user: User = Depends(_buyer), db: Session = Depends(get_db)):
    rfq = RFQ(
        buyer_id=user.id,
        commodity_id=body.commodity_id,
        variety_id=body.variety_id,
        grade_spec_id=body.grade_spec_id,
        requested_qty=qty(body.requested_qty),
        unit=body.unit,
        target_price=body.target_price,
        destination_mandal_id=body.destination_mandal_id,
        delivery_window=body.delivery_window,
        packaging=body.packaging,
        acceptable_variation=body.acceptable_variation,
        inspection_required=body.inspection_required,
        status=RFQStatus.OPEN,
    )
    db.add(rfq)
    db.commit()
    db.refresh(rfq)
    return _rfq_json(rfq)


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
    return [_rfq_json(r) for r in db.scalars(stmt.order_by(RFQ.created_at.desc()))]


@router.get("/mine")
def my_rfqs(user: User = Depends(_buyer), db: Session = Depends(get_db)):
    rows = db.scalars(select(RFQ).where(RFQ.buyer_id == user.id).order_by(RFQ.created_at.desc()))
    return [_rfq_json(r) for r in rows]


@router.get("/{rfq_id}")
def get_rfq(rfq_id: int, db: Session = Depends(get_db)):
    rfq = db.get(RFQ, rfq_id)
    if not rfq:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "RFQ not found")
    return _rfq_json(rfq)


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
    db.commit()
    db.refresh(offer)
    return _offer_json(offer, db)
