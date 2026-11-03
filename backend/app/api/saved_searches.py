"""Saved buyer searches — store a marketplace query + filters, get alerted when
a new matching listing is published, and re-run the search on demand.

Compounds the favorites/watchlist feature (which watches a single commodity):
a saved search can span a category, a price ceiling, a place, an organic claim
and a free-text term all at once. Match logic is shared between the live results
query and the publish-time alert hook (``notify_saved_search_matches``).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.rbac import BUYER_ROLES
from app.models.catalog import Commodity
from app.models.common import ListingStatus
from app.models.location import Mandal
from app.models.marketplace import Listing, SavedSearch
from app.models.user import User
from app.services import notify

router = APIRouter(prefix="/saved-searches", tags=["saved-searches"])

_ALLOWED = {"q", "category", "mandal_id", "claim_status", "max_price", "min_qty"}


def _clean_criteria(raw: dict) -> dict:
    """Keep only recognised, non-empty filter keys."""
    out: dict = {}
    for k in _ALLOWED:
        v = raw.get(k)
        if v in (None, "", []):
            continue
        if k in ("mandal_id",):
            out[k] = int(v)
        elif k in ("max_price", "min_qty"):
            out[k] = float(v)
        else:
            out[k] = str(v).strip()
    return out


def _matching_listings(db: Session, criteria: dict) -> list[Listing]:
    """Current OPEN, in-stock listings that satisfy the criteria."""
    stmt = select(Listing).where(Listing.status == ListingStatus.OPEN)
    cat = criteria.get("category")
    qtext = criteria.get("q")
    if cat or qtext:
        stmt = stmt.join(Commodity, Commodity.id == Listing.commodity_id)
        if cat:
            stmt = stmt.where(Commodity.category == cat)
        if qtext:
            like = f"%{qtext}%"
            stmt = stmt.where((Commodity.name.ilike(like)) | (Commodity.name_te.ilike(like)))
    if criteria.get("mandal_id"):
        stmt = stmt.where(Listing.mandal_id == criteria["mandal_id"])
    if criteria.get("claim_status"):
        stmt = stmt.where(Listing.claim_status == criteria["claim_status"])
    if criteria.get("max_price") is not None:
        stmt = stmt.where(Listing.asking_price <= criteria["max_price"])
    rows = list(db.scalars(stmt.order_by(Listing.id.desc())))
    min_qty = criteria.get("min_qty")
    if min_qty is not None:
        rows = [l for l in rows if float(l.available_qty) >= min_qty]
    else:
        rows = [l for l in rows if float(l.available_qty) > 0]
    return rows


def _listing_matches(db: Session, listing: Listing, criteria: dict) -> bool:
    """Does one listing satisfy the criteria? (used at publish time)."""
    if listing.status != ListingStatus.OPEN or float(listing.available_qty) <= 0:
        return False
    c = db.get(Commodity, listing.commodity_id)
    if criteria.get("category") and (not c or c.category != criteria["category"]):
        return False
    if criteria.get("q"):
        q = criteria["q"].lower()
        names = " ".join(filter(None, [c.name if c else "", c.name_te if c else ""])).lower()
        if q not in names:
            return False
    if criteria.get("mandal_id") and listing.mandal_id != criteria["mandal_id"]:
        return False
    if criteria.get("claim_status") and listing.claim_status != criteria["claim_status"]:
        return False
    if criteria.get("max_price") is not None and float(listing.asking_price) > criteria["max_price"]:
        return False
    if criteria.get("min_qty") is not None and float(listing.available_qty) < criteria["min_qty"]:
        return False
    return True


def _describe(db: Session, criteria: dict) -> str:
    """Human-readable one-liner for a criteria set (used as a fallback label)."""
    parts = []
    if criteria.get("q"):
        parts.append(f'"{criteria["q"]}"')
    if criteria.get("category"):
        parts.append(criteria["category"])
    if criteria.get("claim_status"):
        parts.append(criteria["claim_status"])
    if criteria.get("mandal_id"):
        m = db.get(Mandal, criteria["mandal_id"])
        if m:
            parts.append(f"in {m.name}")
    if criteria.get("max_price") is not None:
        parts.append(f"≤ ₹{criteria['max_price']:g}/kg")
    if criteria.get("min_qty") is not None:
        parts.append(f"≥ {criteria['min_qty']:g} kg")
    return " · ".join(parts) or "All produce"


def _row(db: Session, s: SavedSearch) -> dict:
    matches = _matching_listings(db, s.criteria or {})
    new = [l for l in matches if l.id > (s.last_match_id or 0)]
    best = min((float(l.asking_price) for l in matches), default=None)
    return {
        "id": s.id,
        "label": s.label or _describe(db, s.criteria or {}),
        "criteria": s.criteria or {},
        "alert": s.alert,
        "description": _describe(db, s.criteria or {}),
        "match_count": len(matches),
        "new_count": len(new),
        "best_price": best,
    }


class SaveBody(BaseModel):
    label: str | None = None
    criteria: dict = {}
    alert: bool = True


class UpdateBody(BaseModel):
    label: str | None = None
    criteria: dict | None = None
    alert: bool | None = None


def _buyer(user: User = Depends(get_current_user)) -> User:
    if user.role not in {str(r) for r in BUYER_ROLES}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Saved searches are for buyers")
    return user


def _owned(db: Session, search_id: int, user: User) -> SavedSearch:
    s = db.get(SavedSearch, search_id)
    if not s or s.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Saved search not found")
    return s


@router.post("", status_code=status.HTTP_201_CREATED)
def create(body: SaveBody, user: User = Depends(_buyer), db: Session = Depends(get_db)):
    criteria = _clean_criteria(body.criteria or {})
    s = SavedSearch(user_id=user.id, label=(body.label or None), criteria=criteria, alert=body.alert)
    # Mark everything already live as "seen" so the buyer is only alerted to
    # genuinely new listings from here on.
    existing = _matching_listings(db, criteria)
    s.last_match_id = max((l.id for l in existing), default=0)
    db.add(s)
    db.commit()
    db.refresh(s)
    return _row(db, s)


@router.get("")
def list_saved(user: User = Depends(_buyer), db: Session = Depends(get_db)):
    rows = db.scalars(select(SavedSearch).where(SavedSearch.user_id == user.id).order_by(SavedSearch.id.desc()))
    return [_row(db, s) for s in rows]


@router.get("/{search_id}/results")
def results(search_id: int, user: User = Depends(_buyer), db: Session = Depends(get_db)):
    from app.api.listings import _serialize

    s = _owned(db, search_id, user)
    matches = _matching_listings(db, s.criteria or {})
    offerings = [_serialize(l, db.get(User, l.seller_id), db) for l in matches]
    # Viewing the results marks the current matches as seen.
    s.last_match_id = max((l.id for l in matches), default=s.last_match_id or 0)
    db.commit()
    return {
        "id": s.id,
        "label": s.label or _describe(db, s.criteria or {}),
        "description": _describe(db, s.criteria or {}),
        "criteria": s.criteria or {},
        "count": len(offerings),
        "offerings": offerings,
    }


@router.patch("/{search_id}")
def update(search_id: int, body: UpdateBody, user: User = Depends(_buyer), db: Session = Depends(get_db)):
    s = _owned(db, search_id, user)
    if body.label is not None:
        s.label = body.label or None
    if body.criteria is not None:
        s.criteria = _clean_criteria(body.criteria)
        existing = _matching_listings(db, s.criteria)
        s.last_match_id = max((l.id for l in existing), default=0)
    if body.alert is not None:
        s.alert = body.alert
    db.commit()
    db.refresh(s)
    return _row(db, s)


@router.delete("/{search_id}")
def delete(search_id: int, user: User = Depends(_buyer), db: Session = Depends(get_db)):
    s = _owned(db, search_id, user)
    db.delete(s)
    db.commit()
    return {"id": search_id, "deleted": True}


def notify_saved_search_matches(db: Session, listing: Listing) -> None:
    """Alert buyers whose saved search matches a newly published listing.

    Safe to call before commit from listings.publish; never raises."""
    try:
        c = db.get(Commodity, listing.commodity_id)
        cname = c.name if c else "a product"
        price = float(listing.asking_price)
        for s in db.scalars(select(SavedSearch)):
            if s.user_id == listing.seller_id or not s.alert:
                continue
            if listing.id <= (s.last_match_id or 0):
                continue
            if not _listing_matches(db, listing, s.criteria or {}):
                continue
            label = s.label or _describe(db, s.criteria or {})
            notify.send(
                db, user_id=s.user_id,
                title=f"New match: {cname}",
                body=f'A new {cname} offering at Rs.{price:.2f}/kg matches your saved search "{label}".',
                object_type="saved_search", object_id=s.id,
            )
            # Do NOT advance last_match_id here: the buyer hasn't *seen* this
            # listing yet, so it must still count as "new" until they open the
            # results. Each listing is evaluated once (at its own publish), so
            # there's no risk of re-alerting.
    except Exception:
        pass  # alerts must never block a publish
