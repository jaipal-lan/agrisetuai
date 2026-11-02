from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.core.money import qty
from app.core.rbac import Role
from app.core.serializers import public_user
from app.models.catalog import Commodity
from app.models.common import ClaimStatus, ListingStatus
from app.models.marketplace import Listing, ListingMedia
from app.models.user import User
from app.api.subscriptions import active_benefits

router = APIRouter(prefix="/listings", tags=["listings"])

_seller = require_roles(Role.FARMER, Role.FPO)

# Active-listing cap for a seller with no paid subscription (free tier).
_FREE_LISTING_CAP = 3


class ListingCreate(BaseModel):
    commodity_id: int
    variety_id: int | None = None
    grade_spec_id: int | None = None
    harvest_year: int | None = None
    available_from: date | None = None
    unit: str = "kg"
    total_qty: float = Field(gt=0)
    min_order_qty: float = 0
    asking_price: float = Field(gt=0)
    negotiable: bool = True
    claim_status: ClaimStatus = ClaimStatus.CONVENTIONAL
    claim_evidence: dict | None = None
    mandal_id: int | None = None
    pickup_terms: str | None = None


def _serialize(listing: Listing, seller: User | None = None) -> dict:
    return {
        "id": listing.id,
        "seller": public_user(seller) if seller else {"id": listing.seller_id},
        "commodity_id": listing.commodity_id,
        "variety_id": listing.variety_id,
        "grade_spec_id": listing.grade_spec_id,
        "harvest_year": listing.harvest_year,
        "unit": listing.unit,
        "total_qty": str(qty(listing.total_qty)),
        "reserved_qty": str(qty(listing.reserved_qty)),
        "sold_qty": str(qty(listing.sold_qty)),
        "available_qty": str(qty(listing.available_qty)),
        "min_order_qty": str(qty(listing.min_order_qty)),
        "asking_price": str(listing.asking_price),
        "negotiable": listing.negotiable,
        "claim_status": listing.claim_status,
        "mandal_id": listing.mandal_id,
        "pickup_terms": listing.pickup_terms,
        "status": listing.status,
        "media": [{"object_key": m.object_key, "media_type": m.media_type} for m in listing.media],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_listing(
    body: ListingCreate, user: User = Depends(_seller), db: Session = Depends(get_db)
):
    # Do not display 'certified organic' without supporting evidence (PRD section 3).
    claim = body.claim_status
    if claim == ClaimStatus.ORGANIC and not body.claim_evidence:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Organic claim requires evidence; use 'in_conversion' or attach certification.",
        )
    listing = Listing(
        seller_id=user.id,
        commodity_id=body.commodity_id,
        variety_id=body.variety_id,
        grade_spec_id=body.grade_spec_id,
        harvest_year=body.harvest_year,
        available_from=body.available_from,
        unit=body.unit,
        total_qty=qty(body.total_qty),
        min_order_qty=qty(body.min_order_qty),
        asking_price=body.asking_price,
        negotiable=body.negotiable,
        claim_status=str(claim),
        claim_evidence=body.claim_evidence,
        mandal_id=body.mandal_id,
        pickup_terms=body.pickup_terms,
        status=ListingStatus.DRAFT,
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return _serialize(listing, user)


@router.get("")
def search_listings(
    commodity_id: int | None = None,
    category: str | None = None,
    mandal_id: int | None = None,
    claim_status: ClaimStatus | None = None,
    max_price: float | None = None,
    min_qty: float | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Listing).where(Listing.status == ListingStatus.OPEN)
    if commodity_id:
        stmt = stmt.where(Listing.commodity_id == commodity_id)
    if category:
        stmt = stmt.join(Commodity, Commodity.id == Listing.commodity_id).where(
            Commodity.category == category
        )
    if mandal_id:
        stmt = stmt.where(Listing.mandal_id == mandal_id)
    if claim_status:
        stmt = stmt.where(Listing.claim_status == str(claim_status))
    if max_price is not None:
        stmt = stmt.where(Listing.asking_price <= max_price)
    rows = list(db.scalars(stmt.order_by(Listing.created_at.desc())))
    out = []
    for listing in rows:
        if min_qty is not None and float(listing.available_qty) < min_qty:
            continue
        seller = db.get(User, listing.seller_id)
        out.append(_serialize(listing, seller))
    return out


@router.get("/mine")
def my_listings(user: User = Depends(_seller), db: Session = Depends(get_db)):
    rows = db.scalars(select(Listing).where(Listing.seller_id == user.id))
    return [_serialize(listing, user) for listing in rows]


@router.get("/{listing_id}")
def get_listing(listing_id: int, db: Session = Depends(get_db)):
    listing = db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
    return _serialize(listing, db.get(User, listing.seller_id))


def _owned(listing_id: int, user: User, db: Session) -> Listing:
    listing = db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
    if listing.seller_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your listing")
    return listing


@router.post("/{listing_id}/publish")
def publish(listing_id: int, user: User = Depends(_seller), db: Session = Depends(get_db)):
    listing = _owned(listing_id, user, db)
    if listing.status not in (ListingStatus.DRAFT, ListingStatus.PAUSED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Listing cannot be published")
    # Enforce the subscription's active-listing cap (free tier otherwise).
    cap = active_benefits(db, user.id).get("max_active_listings", _FREE_LISTING_CAP)
    active_count = db.scalar(
        select(func.count())
        .select_from(Listing)
        .where(Listing.seller_id == user.id, Listing.status == ListingStatus.OPEN)
    )
    if active_count >= cap:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Active-listing limit reached ({cap}). Upgrade your plan to list more.",
        )
    listing.status = ListingStatus.OPEN
    db.commit()
    return _serialize(listing, user)


@router.post("/{listing_id}/pause")
def pause(listing_id: int, user: User = Depends(_seller), db: Session = Depends(get_db)):
    listing = _owned(listing_id, user, db)
    listing.status = ListingStatus.PAUSED
    db.commit()
    return _serialize(listing, user)


@router.post("/{listing_id}/withdraw")
def withdraw(listing_id: int, user: User = Depends(_seller), db: Session = Depends(get_db)):
    listing = _owned(listing_id, user, db)
    if float(listing.reserved_qty) > 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Cannot withdraw with reserved quantity"
        )
    listing.status = ListingStatus.WITHDRAWN
    db.commit()
    return _serialize(listing, user)


class MediaAttach(BaseModel):
    object_key: str
    media_type: str = "image"
    checksum: str | None = None


@router.post("/{listing_id}/media")
def attach_media(
    listing_id: int,
    body: MediaAttach,
    user: User = Depends(_seller),
    db: Session = Depends(get_db),
):
    listing = _owned(listing_id, user, db)
    db.add(
        ListingMedia(
            listing_id=listing.id,
            object_key=body.object_key,
            media_type=body.media_type,
            checksum=body.checksum,
            access_class="public",
        )
    )
    db.commit()
    db.refresh(listing)
    return _serialize(listing, user)
