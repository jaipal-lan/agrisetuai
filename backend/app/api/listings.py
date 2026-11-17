from datetime import date, datetime, timezone

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
from app.models.location import District, Mandal
from app.models.marketplace import Listing, ListingMedia
from app.models.review import Review
from app.models.user import FarmerProfile, User

router = APIRouter(prefix="/listings", tags=["listings"])

_seller = require_roles(Role.FARMER)
_verifier = require_roles(Role.FIELD_AGENT, Role.FIELD_LEADER, Role.FIELD_MANAGER, Role.SUPERADMIN)

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
    latitude: float | None = None
    longitude: float | None = None
    pickup_terms: str | None = None
    specifications: str | None = None
    quality_grade: str | None = None   # A | B | C
    defect_pct: float | None = None
    defect_notes: str | None = None


def _can_manage(listing: Listing, user: User, db: Session) -> bool:
    """Only the seller who owns a listing may manage it."""
    return listing.seller_id == user.id


def _rating_for_sellers(db: Session, seller_ids) -> tuple[float | None, int]:
    """Average buyer rating and total review count across one or more sellers
    (farmers). For a single seller it's that seller's rating; for a product card
    aggregating several farmers it's the volume-weighted average across all their
    buyer reviews — the trust signal a buyer sees before choosing a seller."""
    ids = [i for i in set(seller_ids) if i is not None]
    if not ids:
        return None, 0
    avg, cnt = db.execute(
        select(func.avg(Review.rating), func.count(Review.id))
        .where(Review.subject_type == "farmer", Review.subject_id.in_(ids))
    ).one()
    return (round(float(avg), 2) if avg is not None else None), int(cnt or 0)


def _latest_review(db: Session, seller_id: int) -> dict | None:
    """The most recent buyer review (with a written comment) for one farmer — a
    real quote to show at the decision point, not just a star number."""
    r = db.scalar(
        select(Review)
        .where(Review.subject_type == "farmer", Review.subject_id == seller_id,
               Review.comment.isnot(None), Review.comment != "")
        .order_by(Review.id.desc())
    )
    if not r:
        return None
    return {"rating": r.rating, "comment": r.comment,
            "at": r.created_at.isoformat() if r.created_at else None}


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
        {"id": m.id, "object_key": m.object_key, "media_type": m.media_type}
        for m in listing.media if m.media_type == "image"
    ]
    video_obj = next((m for m in listing.media if m.media_type == "video"), None)
    video = video_obj.object_key if video_obj else None
    video_id = video_obj.id if video_obj else None
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
        "latitude": float(listing.latitude) if listing.latitude is not None else None,
        "longitude": float(listing.longitude) if listing.longitude is not None else None,
        "unit": listing.unit,
        "pickup_terms": listing.pickup_terms,
        "specifications": listing.specifications,
        "quality_grade": listing.quality_grade,
        "defect_pct": str(listing.defect_pct) if listing.defect_pct is not None else None,
        "defect_notes": listing.defect_notes,
        "status": listing.status,
        "out_of_stock": out_of_stock,
        "video": video,
        "video_id": video_id,
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
        # Per-listing unit wins (farmer's choice); fall back to the commodity default.
        data["unit"] = listing.unit or (commodity.unit if commodity else "kg")
        data["variety"] = variety.name if variety else None
        data["grade"] = None if grade is None else {
            "code": grade.code, "label": grade.label, "attributes": grade.attributes,
        }
        data["place"] = _place(db, listing, seller)
        if listing.agent_verified and listing.verified_by:
            vb = db.get(User, listing.verified_by)
            data["verified_by_name"] = vb.name if vb else None
        # Seller's rating from buyer reviews.
        data["seller_rating"], data["seller_rating_count"] = _rating_for_sellers(
            db, [listing.seller_id]
        )
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
    seller_id = user.id
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
        latitude=body.latitude,
        longitude=body.longitude,
        pickup_terms=body.pickup_terms,
        specifications=body.specifications,
        quality_grade=body.quality_grade,
        defect_pct=body.defect_pct,
        defect_notes=body.defect_notes,
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
def _product_card(c: Commodity, rows: list[Listing], db: Session) -> dict:
    """Aggregate one commodity's open listings into a product-grid card:
    how many farmers/places offer it, the price range and a representative photo.
    `rows` is that commodity's OPEN listings (live and sold-out alike)."""
    live = [l for l in rows if qty(l.available_qty) > qty(0)]
    prices = [float(l.asking_price) for l in live]
    places = set()
    for l in live:
        m = db.get(Mandal, l.mandal_id) if l.mandal_id else None
        if m:
            places.add(m.name)
    # A representative photo: first real image from any offering, else a
    # placeholder key the media endpoint renders as produce art.
    image_key = None
    for l in (live or rows):
        img = next((m for m in l.media if m.media_type == "image"), None)
        if img:
            image_key = img.object_key
            break
    if not image_key:
        image_key = f"sample/{c.name.lower().replace(' ', '-')}.svg"
    # Trust signal: rating across the farmers currently offering this product.
    seller_rating, seller_rating_count = _rating_for_sellers(db, {l.seller_id for l in live})
    return {
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
        "seller_rating": seller_rating,
        "seller_rating_count": seller_rating_count,
    }


# Declared before /{listing_id} so "products" is not parsed as a listing id.

@router.get("/products")
def products(category: str | None = None, q: str | None = None,
             sort: str = "name", min_rating: float | None = None,
             db: Session = Depends(get_db)):
    """Product catalog grouped by commodity, each with how many farmers/places
    currently offer it and the price range — the marketplace's product grid.

    `q` searches the commodity name (English or Telugu); `sort` is one of
    name | price_asc | price_desc | verified | availability | rating.
    `min_rating` keeps only products whose sellers average at least that rating.
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
        out.append(_product_card(c, rows, db))

    if min_rating is not None:
        out = [p for p in out if (p["seller_rating"] or 0) >= min_rating]

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
    elif sort == "rating":
        # Highest-rated sellers first; unrated products sort last.
        out.sort(key=lambda p: (p["seller_rating"] is None, -(p["seller_rating"] or 0), p["commodity"]))
    # else: keep the default category/name order from the query.
    return out


def _fresh_row(l: Listing, db: Session) -> dict:
    """A compact 'just listed' card for one live listing on the buyer home."""
    c = db.get(Commodity, l.commodity_id)
    seller = db.get(User, l.seller_id)
    m = db.get(Mandal, l.mandal_id) if l.mandal_id else None
    img = next((mm.object_key for mm in l.media if mm.media_type == "image"), None)
    if not img and c:
        img = f"sample/{c.name.lower().replace(' ', '-')}.svg"
    seller_rating, seller_rating_count = _rating_for_sellers(db, [l.seller_id])
    return {
        "listing_id": l.id,
        "commodity_id": l.commodity_id,
        "commodity": c.name if c else None,
        "commodity_te": c.name_te if c else None,
        "category": c.category if c else None,
        "price": float(l.asking_price),
        "available_qty": str(qty(l.available_qty)),
        "place": m.name if m else None,
        "seller": public_user(seller)["name"] if seller else None,
        "agent_verified": l.agent_verified,
        "seller_rating": seller_rating,
        "seller_rating_count": seller_rating_count,
        "image": img,
        "listed_at": l.created_at.isoformat() if l.created_at else None,
    }


@router.get("/discovery")
def discovery(mandal_id: int | None = None, db: Session = Depends(get_db)):
    """Curated buyer home: featured produce, fresh listings, browse-by-category,
    headline stats, and — when a location is given — what's available near you.

    `mandal_id` scopes the "near you" section to the buyer's district (the mandal's
    district, so nearby villages count too). Everything else is market-wide.
    """
    commodities = {c.id: c for c in db.scalars(select(Commodity))}
    open_listings = list(db.scalars(
        select(Listing).where(Listing.status == ListingStatus.OPEN)
    ))
    by_commodity: dict[int, list[Listing]] = {}
    for l in open_listings:
        by_commodity.setdefault(l.commodity_id, []).append(l)

    # Build a card per commodity that actually has live stock.
    cards = []
    for cid, rows in by_commodity.items():
        c = commodities.get(cid)
        if not c:
            continue
        card = _product_card(c, rows, db)
        if card["offering_count"] > 0:
            cards.append(card)

    INF = float("inf")
    # Featured: agent-verified first, then widest availability, then best price.
    featured = sorted(
        cards,
        key=lambda p: (not p["any_verified"], -p["offering_count"], p["price_min"] or INF),
    )[:6]

    # Browse by category, busiest category first.
    cats: dict[str, dict] = {}
    for p in cards:
        d = cats.setdefault(p["category"], {
            "category": p["category"], "product_count": 0, "offering_count": 0,
        })
        d["product_count"] += 1
        d["offering_count"] += p["offering_count"]
    categories = sorted(cats.values(), key=lambda d: (-d["offering_count"], d["category"]))

    # Fresh: most recently listed live lots.
    live_listings = [l for l in open_listings if qty(l.available_qty) > qty(0)]
    live_listings.sort(
        key=lambda l: l.created_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    fresh = [_fresh_row(l, db) for l in live_listings[:6]]

    # Near you: same-district produce, so nearby villages count, not just the mandal.
    near_you = None
    if mandal_id:
        m = db.get(Mandal, mandal_id)
        if m:
            district = db.get(District, m.district_id)
            district_mandals = set(db.scalars(
                select(Mandal.id).where(Mandal.district_id == m.district_id)
            ))
            near_cards = []
            for cid, rows in by_commodity.items():
                c = commodities.get(cid)
                if not c:
                    continue
                local = [l for l in rows if l.mandal_id in district_mandals]
                if not local:
                    continue
                card = _product_card(c, local, db)
                if card["offering_count"] > 0:
                    near_cards.append(card)
            near_cards.sort(key=lambda p: (not p["any_verified"], -p["offering_count"]))
            near_you = {
                "mandal_id": mandal_id,
                "mandal": m.name,
                "district": district.name if district else None,
                "products": near_cards[:8],
            }

    return {
        "featured": featured,
        "fresh": fresh,
        "categories": categories,
        "near_you": near_you,
        "stats": {
            "live_products": len(cards),
            "farmers": len({l.seller_id for l in live_listings}),
            "places": len({l.mandal_id for l in live_listings if l.mandal_id}),
        },
    }


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
    # Attach each seller's most recent written review — a real buyer quote.
    for o in offerings:
        sid = (o.get("seller") or {}).get("id")
        o["top_review"] = _latest_review(db, sid) if sid else None
    in_stock = [o for o in offerings if not o["out_of_stock"]]
    prices = [float(o["asking_price"]) for o in in_stock]
    places = sorted({o["place"]["label"] for o in in_stock if o["place"]["label"]})
    # Product-level trust: rating across every farmer shown on this page
    # (in-stock and sold-out offerings are both displayed here).
    seller_rating, seller_rating_count = _rating_for_sellers(
        db, {l.seller_id for l in rows}
    )
    return {
        "commodity_id": commodity_id,
        "commodity": commodity.name,
        "commodity_te": commodity.name_te,
        "min_order_qty": str(qty(commodity.min_order_qty or 0)),
        "offering_count": len(in_stock),
        "price_min": min(prices) if prices else None,
        "price_max": max(prices) if prices else None,
        "places": places,
        "seller_rating": seller_rating,
        "seller_rating_count": seller_rating_count,
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
    listing.status = ListingStatus.OPEN
    db.commit()
    return _serialize(listing, db.get(User, listing.seller_id), db)


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


@router.delete("/{listing_id}/media/{media_id}")
def delete_media(
    listing_id: int,
    media_id: int,
    user: User = Depends(_seller),
    db: Session = Depends(get_db),
):
    """Remove one photo/video from the seller's own listing (replace = delete +
    re-attach). Owner only."""
    listing = _owned(listing_id, user, db)
    m = next((x for x in listing.media if x.id == media_id), None)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found on this listing")
    db.delete(m)
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
