from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.core.ids import lot_id as gen_lot
from app.core.money import D, qty
from app.core.rbac import Role
from app.models.common import utcnow
from app.models.order import Lot, LotEvent, Package
from app.models.support import QualityCase
from app.services import audit

router = APIRouter(tags=["lots"])

_ops = require_roles(Role.FIELD_AGENT, Role.MANDAL_MANAGER, Role.SUPERADMIN)


def _lot_by_public(public_id: str, db: Session) -> Lot:
    lot = db.scalar(select(Lot).where(Lot.public_id == public_id))
    if not lot:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lot not found")
    return lot


def _lot_json(lot: Lot, db: Session) -> dict:
    events = db.scalars(select(LotEvent).where(LotEvent.lot_id == lot.id).order_by(LotEvent.id))
    pkgs = db.scalars(select(Package).where(Package.lot_id == lot.id))
    return {
        "id": lot.id,
        "public_id": lot.public_id,
        "parent_lot_id": lot.parent_lot_id,
        "commodity_id": lot.commodity_id,
        "quantity": str(qty(lot.quantity)),
        "grade_spec_id": lot.grade_spec_id,
        "seal_ref": lot.seal_ref,
        "status": lot.status,
        "packages": [
            {"qr": p.qr_code, "net_weight": str(qty(p.net_weight)), "count": p.package_count}
            for p in pkgs
        ],
        "events": [
            {"event_type": e.event_type, "payload": e.payload, "at": e.at.isoformat()}
            for e in events
        ],
    }


@router.get("/lots/{public_id}")
def get_lot(public_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    lot = _lot_by_public(public_id, db)
    return _lot_json(lot, db)


class SplitBody(BaseModel):
    quantities: list[float] = Field(min_length=2)


@router.post("/lots/{public_id}/split")
def split_lot(
    public_id: str, body: SplitBody, user=Depends(_ops), db: Session = Depends(get_db)
):
    parent = _lot_by_public(public_id, db)
    parts = [qty(x) for x in body.quantities]
    if any(p <= 0 for p in parts):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Quantities must be positive")
    if sum(parts, start=qty(0)) != qty(parent.quantity):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Child quantities must sum to the parent lot quantity",
        )
    children = []
    for part in parts:
        child = Lot(
            public_id=gen_lot(),
            parent_lot_id=parent.id,
            source_listing_id=parent.source_listing_id,
            seller_id=parent.seller_id,
            commodity_id=parent.commodity_id,
            quantity=part,
            grade_spec_id=parent.grade_spec_id,
            status="split_child",
        )
        db.add(child)
        db.flush()
        db.add(
            LotEvent(
                lot_id=child.id,
                event_type="split_from",
                actor_id=user.id,
                payload={"parent": parent.public_id, "qty": str(part)},
                at=utcnow(),
            )
        )
        children.append(child)
    parent.status = "split"
    db.add(
        LotEvent(
            lot_id=parent.id,
            event_type="split",
            actor_id=user.id,
            payload={"children": [c.public_id for c in children]},
            at=utcnow(),
        )
    )
    audit.record(
        db,
        actor_id=user.id,
        action="lot.split",
        object_type="lot",
        object_id=parent.public_id,
        new_values={"children": [c.public_id for c in children]},
    )
    db.commit()
    return {
        "parent": parent.public_id,
        "children": [c.public_id for c in children],
    }


class MergeBody(BaseModel):
    other_public_id: str


@router.post("/lots/{public_id}/merge")
def merge_lot(
    public_id: str, body: MergeBody, user=Depends(_ops), db: Session = Depends(get_db)
):
    a = _lot_by_public(public_id, db)
    b = _lot_by_public(body.other_public_id, db)
    if a.seller_id != b.seller_id or a.commodity_id != b.commodity_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Lots can only be merged for the same seller and commodity",
        )
    combined = Lot(
        public_id=gen_lot(),
        parent_lot_id=a.id,
        source_listing_id=a.source_listing_id,
        seller_id=a.seller_id,
        commodity_id=a.commodity_id,
        quantity=qty(a.quantity) + qty(b.quantity),
        grade_spec_id=a.grade_spec_id,
        status="merged",
    )
    db.add(combined)
    db.flush()
    a.status = "merged_away"
    b.status = "merged_away"
    for src in (a, b):
        db.add(
            LotEvent(
                lot_id=src.id,
                event_type="merged_into",
                actor_id=user.id,
                payload={"into": combined.public_id},
                at=utcnow(),
            )
        )
    db.add(
        LotEvent(
            lot_id=combined.id,
            event_type="merge",
            actor_id=user.id,
            payload={"from": [a.public_id, b.public_id]},
            at=utcnow(),
        )
    )
    db.commit()
    return {"lot_id": combined.public_id, "quantity": str(qty(combined.quantity))}


class QualityCreate(BaseModel):
    listing_id: int | None = None
    lot_public_id: str | None = None
    order_id: int | None = None
    layer: str = "camera"
    notes: str | None = None
    media_refs: list[str] | None = None
    flags: dict | None = None


@router.post("/quality/cases", status_code=status.HTTP_201_CREATED)
def quality_case(
    body: QualityCreate, user=Depends(get_current_user), db: Session = Depends(get_db)
):
    from app.core.ids import quality_id

    lot_id = None
    if body.lot_public_id:
        lot_id = _lot_by_public(body.lot_public_id, db).id
    flags = body.flags or {}
    flags.setdefault("auto_reject", False)
    flags.setdefault(
        "review_required",
        True,
    )
    flags.setdefault(
        "limitation",
        "A camera check cannot prove moisture, residue, adulteration or food safety.",
    )
    c = QualityCase(
        public_id=quality_id(),
        opener_id=user.id,
        listing_id=body.listing_id,
        lot_id=lot_id,
        order_id=body.order_id,
        layer=body.layer,
        notes=body.notes,
        media_refs={"refs": body.media_refs or []},
        flags=flags,
        status="needs_review",
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return {
        "id": c.id,
        "public_id": c.public_id,
        "status": c.status,
        "flags": c.flags,
        "layer": c.layer,
    }


@router.get("/lots/{public_id}/quality")
def lot_quality(public_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    lot = _lot_by_public(public_id, db)
    rows = db.scalars(select(QualityCase).where(QualityCase.lot_id == lot.id))
    return [
        {
            "id": c.id,
            "public_id": c.public_id,
            "layer": c.layer,
            "status": c.status,
            "flags": c.flags,
            "notes": c.notes,
        }
        for c in rows
    ]
