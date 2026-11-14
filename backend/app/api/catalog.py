from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.money import qty
from app.core.rbac import Role
from app.models.catalog import Commodity, GradeSpec, Variety
from app.models.common import utcnow
from app.models.support import Notification
from app.models.user import User
from app.services import audit

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _commodity_json(c: Commodity) -> dict:
    return {
        "id": c.id,
        "category": c.category,
        "name": c.name,
        "name_te": c.name_te,
        "product_form": c.product_form,
        "unit": c.unit,
        "handling_class": c.handling_class,
        "min_order_qty": str(qty(c.min_order_qty or 0)),
        "active": c.active,
        "pending_deletion": bool(c.deletion_requested_by) and c.active,
        "deletion_reason": c.deletion_reason,
    }


@router.get("/commodities")
def commodities(category: str | None = None, db: Session = Depends(get_db)):
    """Active catalogue (what farmers list and buyers request). Removed products
    are hidden here; staff manage them via /catalog/commodities/manage."""
    stmt = select(Commodity).where(Commodity.active.is_(True))
    if category:
        stmt = stmt.where(Commodity.category == category)
    return [_commodity_json(c) for c in db.scalars(stmt.order_by(Commodity.category, Commodity.name))]


class CommodityCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    category: str = "other"
    name_te: str | None = None
    unit: str = "kg"


@router.post("/commodities", status_code=status.HTTP_201_CREATED)
def create_commodity(
    body: CommodityCreate,
    user=Depends(require_roles(
        Role.FARMER, Role.FIELD_AGENT, Role.FIELD_LEADER, Role.FIELD_MANAGER, Role.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    """Add a product to the catalogue. Open to farmers (the seller's "Other"
    option) and to field staff (agents/leaders/managers/superadmin) so the list
    stays complete for everyone. Reuses an existing commodity with the same name
    (case-insensitive); a previously-removed one is reactivated instead of
    duplicated, so the dropdown stays clean."""
    name = body.name.strip()
    existing = db.scalar(select(Commodity).where(func.lower(Commodity.name) == name.lower()))
    if existing:
        if not existing.active:
            existing.active = True
            existing.deletion_requested_by = None
            existing.deletion_requested_at = None
            existing.deletion_reason = None
            audit.record(db, actor_id=user.id, action="catalog.reactivate_commodity",
                         object_type="commodity", object_id=existing.id, new_values={"name": name})
            db.commit()
        return _commodity_json(existing)
    c = Commodity(
        category=(body.category or "other").strip().lower(),
        name=name, name_te=(body.name_te or None),
        product_form=name.lower(), unit=body.unit or "kg",
        handling_class="dry_grain", min_order_qty=0,
    )
    db.add(c)
    audit.record(db, actor_id=user.id, action="catalog.add_commodity",
                 object_type="commodity", new_values={"name": name})
    db.commit()
    db.refresh(c)
    return _commodity_json(c)


# --- Commodity removal: request (leader/manager) -> approve (superadmin) -----

class DeletionRequestBody(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class DeletionDecisionBody(BaseModel):
    approve: bool


def _notify(db: Session, user_id: int, title: str, body: str, object_id) -> None:
    db.add(Notification(user_id=user_id, title=title, body=body,
                        object_type="commodity", object_id=str(object_id)))


@router.get("/commodities/manage")
def manage_commodities(
    user=Depends(require_roles(Role.FIELD_AGENT, Role.FIELD_LEADER, Role.FIELD_MANAGER, Role.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    """Staff catalogue view: every product incl. removed ones, each flagged with
    status, who requested removal (and why), and how many listings use it — so a
    superadmin can decide safely."""
    from app.models.marketplace import Listing

    counts = dict(db.execute(
        select(Listing.commodity_id, func.count(Listing.id)).group_by(Listing.commodity_id)
    ).all())
    names = {u.id: (u.name or u.phone) for u in db.scalars(select(User))}
    rows = db.scalars(select(Commodity).order_by(Commodity.active.desc(), Commodity.category, Commodity.name))
    out = []
    for c in rows:
        j = _commodity_json(c)
        j["listing_count"] = counts.get(c.id, 0)
        j["deletion_requested_by_name"] = names.get(c.deletion_requested_by) if c.deletion_requested_by else None
        j["deletion_requested_at"] = c.deletion_requested_at
        out.append(j)
    return out


@router.post("/commodities/{commodity_id}/request-deletion")
def request_deletion(
    commodity_id: int,
    body: DeletionRequestBody,
    user=Depends(require_roles(Role.FIELD_LEADER, Role.FIELD_MANAGER, Role.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    """Field leader/manager asks for a product to be removed. Pending until a
    superadmin approves; the product stays usable in the meantime."""
    c = db.get(Commodity, commodity_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Commodity not found")
    if not c.active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This product is already removed")
    if c.deletion_requested_by:
        raise HTTPException(status.HTTP_409_CONFLICT, "A removal request is already pending")
    c.deletion_requested_by = user.id
    c.deletion_requested_at = utcnow().isoformat()
    c.deletion_reason = body.reason.strip()
    for sa_user in db.scalars(select(User).where(User.role == str(Role.SUPERADMIN), User.status == "active")):
        _notify(db, sa_user.id, "Product removal requested",
                f"{user.name or 'A manager'} asked to remove '{c.name}': {c.deletion_reason}", c.id)
    audit.record(db, actor_id=user.id, action="catalog.request_deletion", object_type="commodity",
                 object_id=c.id, new_values={"reason": c.deletion_reason})
    db.commit()
    return _commodity_json(c)


@router.post("/commodities/{commodity_id}/deletion-decision")
def decide_deletion(
    commodity_id: int,
    body: DeletionDecisionBody,
    user=Depends(require_roles(Role.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    """Superadmin approves (removes from the list) or rejects a removal request."""
    c = db.get(Commodity, commodity_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Commodity not found")
    if not c.deletion_requested_by:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No pending removal request")
    requester = c.deletion_requested_by
    if body.approve:
        c.active = False
        c.deletion_requested_by = None
        c.deletion_requested_at = None
        _notify(db, requester, "Removal approved", f"'{c.name}' has been removed from the catalogue.", c.id)
        action = "catalog.delete_approved"
    else:
        c.deletion_requested_by = None
        c.deletion_requested_at = None
        c.deletion_reason = None
        _notify(db, requester, "Removal rejected", f"The request to remove '{c.name}' was declined.", c.id)
        action = "catalog.delete_rejected"
    audit.record(db, actor_id=user.id, action=action, object_type="commodity", object_id=c.id)
    db.commit()
    return _commodity_json(c)


@router.post("/commodities/{commodity_id}/restore")
def restore_commodity(
    commodity_id: int,
    user=Depends(require_roles(Role.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    """Superadmin brings a removed product back into the catalogue."""
    c = db.get(Commodity, commodity_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Commodity not found")
    c.active = True
    c.deletion_requested_by = None
    c.deletion_requested_at = None
    c.deletion_reason = None
    audit.record(db, actor_id=user.id, action="catalog.restore", object_type="commodity", object_id=c.id)
    db.commit()
    return _commodity_json(c)


class MOQBody(BaseModel):
    min_order_qty: float = Field(ge=0)


@router.patch("/commodities/{commodity_id}/moq")
def set_moq(
    commodity_id: int,
    body: MOQBody,
    user=Depends(require_roles(Role.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    """Superadmin: configure a product's minimum order quantity."""
    c = db.get(Commodity, commodity_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Commodity not found")
    old = str(qty(c.min_order_qty or 0))
    c.min_order_qty = qty(body.min_order_qty)
    audit.record(db, actor_id=user.id, action="catalog.set_moq", object_type="commodity",
                 object_id=c.id, old_values={"min_order_qty": old},
                 new_values={"min_order_qty": str(qty(body.min_order_qty))})
    db.commit()
    return _commodity_json(c)


@router.get("/commodities/{commodity_id}/varieties")
def varieties(commodity_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(select(Variety).where(Variety.commodity_id == commodity_id))
    return [{"id": v.id, "name": v.name, "name_te": v.name_te} for v in rows]


@router.get("/commodities/{commodity_id}/grades")
def grades(commodity_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(select(GradeSpec).where(GradeSpec.commodity_id == commodity_id))
    return [
        {
            "id": g.id,
            "code": g.code,
            "label": g.label,
            "attributes": g.attributes,
            "spec_version": g.spec_version,
        }
        for g in rows
    ]
