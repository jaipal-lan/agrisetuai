from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.catalog import Commodity, GradeSpec, Variety

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/commodities")
def commodities(category: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Commodity)
    if category:
        stmt = stmt.where(Commodity.category == category)
    return [
        {
            "id": c.id,
            "category": c.category,
            "name": c.name,
            "name_te": c.name_te,
            "product_form": c.product_form,
            "unit": c.unit,
            "handling_class": c.handling_class,
        }
        for c in db.scalars(stmt.order_by(Commodity.category, Commodity.name))
    ]


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
