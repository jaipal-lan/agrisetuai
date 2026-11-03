"""Seller-side RFQ alerts — the mirror of buyer favorites/saved searches.

A seller registers a *crop interest* (a commodity, optionally with a minimum
acceptable price). When a buyer posts an RFQ, matching sellers are notified so
they can offer in. Sellers are also auto-alerted for any commodity they already
have an open listing in, so a crop interest is opt-in extra reach — useful for
produce they grow but haven't listed yet.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.money import money
from app.core.rbac import Role
from app.models.catalog import Commodity
from app.models.common import ListingStatus, RFQStatus
from app.models.marketplace import RFQ, CropInterest, Listing
from app.models.user import User
from app.services import notify

router = APIRouter(prefix="/crop-interests", tags=["crop-interests"])

_seller = require_roles(Role.FARMER, Role.FPO)


def _open_rfqs(db: Session, commodity_id: int) -> list[RFQ]:
    return list(db.scalars(
        select(RFQ).where(RFQ.commodity_id == commodity_id, RFQ.status == RFQStatus.OPEN)
    ))


def _row(db: Session, ci: CropInterest) -> dict:
    c = db.get(Commodity, ci.commodity_id)
    rfqs = _open_rfqs(db, ci.commodity_id)
    targets = [float(r.target_price) for r in rfqs if r.target_price is not None]
    return {
        "commodity_id": ci.commodity_id,
        "commodity": c.name if c else None,
        "commodity_te": c.name_te if c else None,
        "category": c.category if c else None,
        "min_price": str(ci.min_price) if ci.min_price is not None else None,
        "open_request_count": len(rfqs),
        "best_target": max(targets) if targets else None,
    }


class InterestBody(BaseModel):
    commodity_id: int
    min_price: float | None = None


@router.post("")
def add_interest(body: InterestBody, user: User = Depends(_seller), db: Session = Depends(get_db)):
    if not db.get(Commodity, body.commodity_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Commodity not found")
    ci = db.scalar(select(CropInterest).where(
        CropInterest.user_id == user.id, CropInterest.commodity_id == body.commodity_id))
    if ci is None:
        ci = CropInterest(user_id=user.id, commodity_id=body.commodity_id)
        db.add(ci)
    ci.min_price = money(body.min_price) if body.min_price is not None else None
    db.commit()
    db.refresh(ci)
    return {**_row(db, ci), "watching": True}


@router.get("")
def list_interests(user: User = Depends(_seller), db: Session = Depends(get_db)):
    rows = db.scalars(select(CropInterest).where(CropInterest.user_id == user.id).order_by(CropInterest.id.desc()))
    return [_row(db, ci) for ci in rows]


@router.get("/{commodity_id}")
def is_interested(commodity_id: int, user: User = Depends(_seller), db: Session = Depends(get_db)):
    ci = db.scalar(select(CropInterest).where(
        CropInterest.user_id == user.id, CropInterest.commodity_id == commodity_id))
    return {"commodity_id": commodity_id, "watching": ci is not None,
            "min_price": (str(ci.min_price) if ci and ci.min_price is not None else None)}


@router.delete("/{commodity_id}")
def remove_interest(commodity_id: int, user: User = Depends(_seller), db: Session = Depends(get_db)):
    ci = db.scalar(select(CropInterest).where(
        CropInterest.user_id == user.id, CropInterest.commodity_id == commodity_id))
    if ci:
        db.delete(ci)
        db.commit()
    return {"commodity_id": commodity_id, "watching": False}


def notify_rfq_matches(db: Session, rfq: RFQ) -> None:
    """Alert sellers when a buyer posts a matching RFQ. Safe to call before the
    RFQ commit; never raises.

    Two sources, de-duplicated to one alert per seller:
      1. sellers with an OPEN listing for the commodity (active sellers), and
      2. sellers with a CropInterest for it (opt-in), unless their min_price is
         set and the RFQ's target is below it.
    """
    try:
        c = db.get(Commodity, rfq.commodity_id)
        cname = c.name if c else "a product"
        target = float(rfq.target_price) if rfq.target_price is not None else None

        recipients: set[int] = set()
        # 1. Active sellers currently listing this commodity.
        for l in db.scalars(select(Listing).where(
                Listing.commodity_id == rfq.commodity_id, Listing.status == ListingStatus.OPEN)):
            if l.seller_id != rfq.buyer_id:
                recipients.add(l.seller_id)
        # 2. Opt-in crop interests (respecting min_price).
        for ci in db.scalars(select(CropInterest).where(CropInterest.commodity_id == rfq.commodity_id)):
            if ci.user_id == rfq.buyer_id:
                continue
            if ci.min_price is not None and target is not None and target < float(ci.min_price):
                continue
            recipients.add(ci.user_id)

        if not recipients:
            return
        from app.core.money import qty as _qty
        want = _qty(rfq.requested_qty)
        tgt_txt = f" at target Rs.{target:.2f}/kg" if target is not None else ""
        for uid in recipients:
            notify.send(
                db, user_id=uid,
                title=f"New request: {cname}",
                body=f"A buyer wants {want} {rfq.unit} of {cname}{tgt_txt}. Offer in before someone else does.",
                object_type="rfq", object_id=rfq.id,
            )
    except Exception:
        pass  # alerts must never block posting an RFQ
