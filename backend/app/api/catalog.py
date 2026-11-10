from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.money import qty
from app.core.rbac import Role
from app.models.catalog import Commodity, GradeSpec, Variety
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
    }


@router.get("/commodities")
def commodities(category: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Commodity)
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
    user=Depends(require_roles(Role.FARMER, Role.FIELD_LEADER, Role.FIELD_MANAGER, Role.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    """Add a product that isn't in the catalog yet (the seller's "Other" option).
    Reuses an existing commodity with the same name (case-insensitive) instead of
    duplicating it, so the dropdown stays clean."""
    name = body.name.strip()
    existing = db.scalar(select(Commodity).where(func.lower(Commodity.name) == name.lower()))
    if existing:
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
