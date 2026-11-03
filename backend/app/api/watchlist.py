"""Buyer favorites / watchlist with optional price-alert targets.

Watching a commodity adds it here; when a farmer publishes a matching listing
(see listings.publish) watchers are notified — immediately if the new price is
at or below their target, otherwise as a "new offering" nudge.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.money import money
from app.models.catalog import Commodity
from app.models.common import ListingStatus
from app.models.location import Mandal
from app.models.marketplace import Listing, Watch
from app.models.user import User

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def _best(db: Session, commodity_id: int) -> dict:
    """Current best (lowest) price + offering/place counts for a commodity."""
    rows = list(db.scalars(
        select(Listing).where(Listing.commodity_id == commodity_id,
                              Listing.status == ListingStatus.OPEN)
    ))
    live = [l for l in rows if float(l.available_qty or 0) > 0]
    prices = [float(l.asking_price) for l in live]
    places = {db.get(Mandal, l.mandal_id).name for l in live
              if l.mandal_id and db.get(Mandal, l.mandal_id)}
    return {
        "best_price": min(prices) if prices else None,
        "offering_count": len(live),
        "place_count": len(places),
    }


class WatchBody(BaseModel):
    commodity_id: int
    target_price: float | None = None


@router.post("")
def add_watch(body: WatchBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not db.get(Commodity, body.commodity_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Commodity not found")
    w = db.scalar(select(Watch).where(Watch.user_id == user.id,
                                      Watch.commodity_id == body.commodity_id))
    if w is None:
        w = Watch(user_id=user.id, commodity_id=body.commodity_id)
        db.add(w)
    w.target_price = money(body.target_price) if body.target_price is not None else None
    db.commit()
    db.refresh(w)
    return {"commodity_id": w.commodity_id,
            "target_price": str(w.target_price) if w.target_price is not None else None,
            "watching": True}


@router.get("")
def list_watches(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    out = []
    for w in db.scalars(select(Watch).where(Watch.user_id == user.id).order_by(Watch.id.desc())):
        c = db.get(Commodity, w.commodity_id)
        if not c:
            continue
        b = _best(db, w.commodity_id)
        tgt = float(w.target_price) if w.target_price is not None else None
        out.append({
            "commodity_id": w.commodity_id,
            "commodity": c.name,
            "commodity_te": c.name_te,
            "category": c.category,
            "target_price": str(w.target_price) if w.target_price is not None else None,
            "best_price": b["best_price"],
            "offering_count": b["offering_count"],
            "place_count": b["place_count"],
            "target_met": (tgt is not None and b["best_price"] is not None and b["best_price"] <= tgt),
        })
    return out


@router.delete("/{commodity_id}")
def remove_watch(commodity_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    w = db.scalar(select(Watch).where(Watch.user_id == user.id, Watch.commodity_id == commodity_id))
    if w:
        db.delete(w)
        db.commit()
    return {"commodity_id": commodity_id, "watching": False}


@router.get("/{commodity_id}")
def is_watching(commodity_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    w = db.scalar(select(Watch).where(Watch.user_id == user.id, Watch.commodity_id == commodity_id))
    return {"commodity_id": commodity_id, "watching": w is not None,
            "target_price": (str(w.target_price) if w and w.target_price is not None else None)}
