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
from app.models.catalog import Commodity, GradeSpec, Variety
from app.models.common import ClaimStatus, ListingStatus, utcnow
from app.models.location import Mandal
from app.models.marketplace import Listing, ListingMedia, Watch
from app.models.user import FarmerProfile, User
from app.services import notify
from app.api.subscriptions import active_benefits

router = APIRouter(prefix="/listings", tags=["listings"])

_seller = require_roles(Role.FARMER, Role.FPO)
_verifier = require_roles(Role.FIELD_AGENT, Role.MANDAL_MANAGER, Role.SUPERADMIN)

# Active-listing cap for a seller with no paid subscription (free tier).
_FREE_LISTING_CAP = 3
# Minimum quality/sample images required before a listing can go live.
_MIN_LISTING_IMAGES = 3


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
    specifications: str | None = None
    # An FPO lead may list produce on behalf of a member farmer in their group.
    on_behalf_of: int | None = None


def _resolve_seller(body_on_behalf: int | None, user: User, db: Session) -> int:
    """Who the listing belongs to. Normally the caller; an FPO lead may list for a
    member of their own group (the listing stays owned by that member)."""
    if not body_on_behalf or body_on_behalf == user.id:
        return user.id
    if user.role != Role.FPO or not user.organisation_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an FPO lead can list for a member")
    member = db.get(User, body_on_behalf)
    if not member or member.organisation_id != user.organisation_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a member of your group")
    if member.role not in (Role.FARMER, Role.FPO):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That member is not a seller")
    return member.id


def _can_manage(listing: Listing, user: User, db: Session) -> bool:
    """The seller, or an FPO lead of the seller's group, may manage a listing."""
    if listing.seller_id == user.id:
        return True
    if user.role == Role.FPO and user.organisation_id:
        seller = db.get(User, listing.seller_id)
        if seller and seller.organisation_id == user.organisation_id:
            return True
    return False


def _place(db: Session, listing: Listing, seller: User | None) -> dict:
    """Where this produce is: mandal (+district) and the farmer's village."""
    mandal = db.get(Mandal, listing.mandal_id) if listing.mandal_id else None
    village = None
    if seller is not None:
        fp = db.scalar(select(FarmerProfile).where(FarmerProfile.user_id == seller.id))
        village = fp.village if fp else None
    return {
        "mandal_id": listing.mandal_id,
        "mandal": mandal.name if mandal else None,
        "village": village,
        "label": ", ".join([p for p in [village, mandal.name if mandal else None] if p]) or None,
    }


def _serialize(listing: Listing, seller: User | None = None, db: Session | None = None) -> dict:
    images = [
        {"object_key": m.object_key, "media_type": m.media_type}
        for m in listing.media if m.media_type == "image"
    ]
    avail = qty(listing.available_qty)
    out_of_stock = listing.status == ListingStatus.SOLD_OUT or avail <= qty(0)
    data = {
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
        "available_qty": str(avail),
        "min_order_qty": str(qty(listing.min_order_qty)),
        "asking_price": str(listing.asking_price),
        "negotiable": listing.negotiable,
        "claim_status": listing.claim_status,
        "is_organic": listing.claim_status == str(ClaimStatus.ORGANIC),
        "mandal_id": listing.mandal_id,
        "pickup_terms": listing.pickup_terms,
        "specifications": listing.specifications,
        "status": listing.status,
        "out_of_stock": out_of_stock,
        "agent_verified": listing.agent_verified,
        "verified_at": listing.verified_at.isoformat() if listing.verified_at else None,
        "verification_note": listing.verification_note,
        "image_count": len(images),
        "media": images,
    }
    if db is not None:
        commodity = db.get(Commodity, listing.commodity_id)
        variety = db.get(Variety, listing.variety_id) if listing.variety_id else None
        grade = db.get(GradeSpec, listing.grade_spec_id) if listing.grade_spec_id else None
        data["commodity"] = commodity.name if commodity else None
        data["commodity_te"] = commodity.name_te if commodity else None
        data["unit"] = commodity.unit if commodity else listing.unit
        data["variety"] = variety.name if variety else None
        data["grade"] = None if grade is None else {
            "code": grade.code, "label": grade.label, "attributes": grade.attributes,
        }
        data["place"] = _place(db, listing, seller)
        if listing.agent_verified and listing.verified_by:
            vb = db.get(User, listing.verified_by)
            data["verified_by_name"] = vb.name if vb else None
        # Seller's rating from buyer reviews.
        from app.models.review import Review
        from sqlalchemy import func as _func
        avg, cnt = db.execute(
            select(_func.avg(Review.rating), _func.count(Review.id))
            .where(Review.subject_type == "farmer", Review.subject_id == listing.seller_id)
        ).one()
        data["seller_rating"] = round(float(avg), 2) if avg is not None else None
        data["seller_rating_count"] = int(cnt or 0)
    return data


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
    seller_id = _resolve_seller(body.on_behalf_of, user, db)
    listing = Listing(
        seller_id=seller_id,
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
        specifications=body.specifications,
        status=ListingStatus.DRAFT,
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return _serialize(listing, db.get(User, seller_id), db)


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
        out.append(_serialize(listing, seller, db))
    return out


@router.get("/mine")
def my_listings(user: User = Depends(_seller), db: Session = Depends(get_db)):
    rows = db.scalars(select(Listing).where(Listing.seller_id == user.id))
    return [_serialize(listing, user, db) for listing in rows]


# --- Product view: the same product offered by multiple farmers/places --------
# Declared before /{listing_id} so "products" is not parsed as a listing id.

@router.get("/products")
def products(category: str | None = None, q: str | None = None,
             sort: str = "name", db: Session = Depends(get_db)):
    """Product catalog grouped by commodity, each with how many farmers/places
    currently offer it and the price range — the marketplace's product grid.

    `q` searches the commodity name (English or Telugu); `sort` is one of
    name | price_asc | price_desc | verified | availability.
    """
    stmt = select(Commodity)
    if category:
        stmt = stmt.where(Commodity.category == category)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where((Commodity.name.ilike(like)) | (Commodity.name_te.ilike(like)))
    out = []
    for c in db.scalars(stmt.order_by(Commodity.category, Commodity.name)):
        rows = list(db.scalars(
            select(Listing).where(Listing.commodity_id == c.id, Listing.status == ListingStatus.OPEN)
        ))
        live = [l for l in rows if qty(l.available_qty) > qty(0)]
        prices = [float(l.asking_price) for l in live]
        places = set()
        for l in live:
            m = db.get(Mandal, l.mandal_id) if l.mandal_id else None
            if m:
                places.add(m.name)
        # A representative photo for the product card: first real image from any
        # offering, else a placeholder key the media endpoint renders as produce art.
        image_key = None
        for l in (live or rows):
            img = next((m for m in l.media if m.media_type == "image"), None)
            if img:
                image_key = img.object_key
                break
        if not image_key:
            image_key = f"sample/{c.name.lower().replace(' ', '-')}.svg"
        out.append({
            "commodity_id": c.id,
            "commodity": c.name,
            "commodity_te": c.name_te,
            "category": c.category,
            "image": image_key,
            "min_order_qty": str(qty(c.min_order_qty or 0)),
            "offering_count": len(live),
            "place_count": len(places),
            "price_min": min(prices) if prices else None,
            "price_max": max(prices) if prices else None,
            "any_verified": any(l.agent_verified for l in live),
        })

    def price_key(p, hi=False):
        v = p["price_max"] if hi else p["price_min"]
        # Out-of-stock (no price) sorts last either way.
        return v if v is not None else (float("inf") if not hi else float("-inf"))

    if sort == "price_asc":
        out.sort(key=lambda p: price_key(p, hi=False))
    elif sort == "price_desc":
        out.sort(key=lambda p: price_key(p, hi=True), reverse=True)
    elif sort == "verified":
        out.sort(key=lambda p: (not p["any_verified"], p["commodity"]))
    elif sort == "availability":
        out.sort(key=lambda p: (-p["offering_count"], p["commodity"]))
    # else: keep the default category/name order from the query.
    return out


@router.get("/products/{commodity_id}")
def product_offerings(commodity_id: int, include_sold_out: bool = True, db: Session = Depends(get_db)):
    """All farmers' offerings of one product, from every place.

    Shows each seller's price, available quantity, location and verification, so a
    buyer sees the full market for a product. Sold-out lots are flagged, not hidden.
    """
    commodity = db.get(Commodity, commodity_id)
    if not commodity:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Commodity not found")
    statuses = [ListingStatus.OPEN, ListingStatus.SOLD_OUT] if include_sold_out else [ListingStatus.OPEN]
    rows = list(db.scalars(
        select(Listing).where(Listing.commodity_id == commodity_id, Listing.status.in_(statuses))
        .order_by(Listing.asking_price)
    ))
    offerings = [_serialize(l, db.get(User, l.seller_id), db) for l in rows]
    in_stock = [o for o in offerings if not o["out_of_stock"]]
    prices = [float(o["asking_price"]) for o in in_stock]
    places = sorted({o["place"]["label"] for o in in_stock if o["place"]["label"]})
    return {
        "commodity_id": commodity_id,
        "commodity": commodity.name,
        "commodity_te": commodity.name_te,
        "min_order_qty": str(qty(commodity.min_order_qty or 0)),
        "offering_count": len(in_stock),
        "price_min": min(prices) if prices else None,
        "price_max": max(prices) if prices else None,
        "places": places,
        "offerings": offerings,
    }


@router.get("/{listing_id}")
def get_listing(listing_id: int, db: Session = Depends(get_db)):
    listing = db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
    return _serialize(listing, db.get(User, listing.seller_id), db)


def _owned(listing_id: int, user: User, db: Session) -> Listing:
    listing = db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
    if not _can_manage(listing, user, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your listing")
    return listing


@router.post("/{listing_id}/publish")
def publish(listing_id: int, user: User = Depends(_seller), db: Session = Depends(get_db)):
    listing = _owned(listing_id, user, db)
    if listing.status not in (ListingStatus.DRAFT, ListingStatus.PAUSED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Listing cannot be published")
    # Require minimum quality/sample images so buyers can see the produce.
    image_count = sum(1 for m in listing.media if m.media_type == "image")
    if image_count < _MIN_LISTING_IMAGES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Add at least {_MIN_LISTING_IMAGES} sample images before publishing "
            f"({image_count}/{_MIN_LISTING_IMAGES}).",
        )
    # Enforce the subscription's active-listing cap on the listing's OWNER (the
    # member), not whoever publishes it (an FPO lead may publish on their behalf).
    owner_id = listing.seller_id
    cap = active_benefits(db, owner_id).get("max_active_listings", _FREE_LISTING_CAP)
    active_count = db.scalar(
        select(func.count())
        .select_from(Listing)
        .where(Listing.seller_id == owner_id, Listing.status == ListingStatus.OPEN)
    )
    if active_count >= cap:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Active-listing limit reached ({cap}). Upgrade your plan to list more.",
        )
    listing.status = ListingStatus.OPEN
    _notify_watchers(db, listing)
    # Alert buyers whose saved search matches this new listing (never blocks).
    from app.api.saved_searches import notify_saved_search_matches
    notify_saved_search_matches(db, listing)
    db.commit()
    return _serialize(listing, db.get(User, owner_id), db)


def _notify_watchers(db: Session, listing: Listing) -> None:
    """Alert buyers watching this commodity when a listing goes live. If the
    watcher set a target price, only alert when the new price meets it."""
    try:
        watches = list(db.scalars(select(Watch).where(Watch.commodity_id == listing.commodity_id)))
        if not watches:
            return
        c = db.get(Commodity, listing.commodity_id)
        cname = c.name if c else "a product"
        price = float(listing.asking_price)
        for w in watches:
            if w.user_id == listing.seller_id:
                continue
            tgt = float(w.target_price) if w.target_price is not None else None
            if tgt is not None and price > tgt:
                continue
            if tgt is not None:
                title, body = (f"Price alert: {cname}",
                               f"A new {cname} offering is Rs.{price:.2f}/kg — at or below your Rs.{tgt:.2f} target.")
            else:
                title, body = (f"New offering: {cname}",
                               f"A new {cname} offering is available at Rs.{price:.2f}/kg.")
            notify.send(db, user_id=w.user_id, title=title, body=body,
                        object_type="product", object_id=listing.commodity_id)
    except Exception:
        pass  # alerts must never block a publish


@router.post("/{listing_id}/pause")
def pause(listing_id: int, user: User = Depends(_seller), db: Session = Depends(get_db)):
    listing = _owned(listing_id, user, db)
    listing.status = ListingStatus.PAUSED
    db.commit()
    return _serialize(listing, user, db)


@router.post("/{listing_id}/withdraw")
def withdraw(listing_id: int, user: User = Depends(_seller), db: Session = Depends(get_db)):
    listing = _owned(listing_id, user, db)
    if float(listing.reserved_qty) > 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Cannot withdraw with reserved quantity"
        )
    listing.status = ListingStatus.WITHDRAWN
    db.commit()
    return _serialize(listing, user, db)


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
    return _serialize(listing, user, db)


class VerifyBody(BaseModel):
    note: str | None = None
    verified: bool = True


@router.post("/{listing_id}/verify")
def verify_listing(
    listing_id: int,
    body: VerifyBody,
    user: User = Depends(_verifier),
    db: Session = Depends(get_db),
):
    """A field agent / mandal manager marks a listing as agent-verified at the farm
    gate (pre-sale). This is a visual field check, not the per-order inspection."""
    listing = db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
    listing.agent_verified = body.verified
    listing.verified_by = user.id if body.verified else None
    listing.verified_at = utcnow() if body.verified else None
    listing.verification_note = body.note
    db.commit()
    return _serialize(listing, db.get(User, listing.seller_id), db)
