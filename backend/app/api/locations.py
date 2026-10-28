from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.location import District, Mandal, State

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("/states")
def states(db: Session = Depends(get_db)):
    return [
        {"id": s.id, "name": s.name, "code": s.code}
        for s in db.scalars(select(State).order_by(State.name))
    ]


@router.get("/districts")
def districts(state_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(District).where(District.state_id == state_id).order_by(District.name)
    )
    return [{"id": d.id, "name": d.name, "state_id": d.state_id} for d in rows]


@router.get("/mandals")
def mandals(district_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Mandal).where(Mandal.district_id == district_id).order_by(Mandal.name)
    )
    return [
        {
            "id": m.id,
            "name": m.name,
            "district_id": m.district_id,
            "serviceable": m.serviceable,
        }
        for m in rows
    ]


@router.get("/serviceability")
def serviceability(mandal_id: int, db: Session = Depends(get_db)):
    m = db.get(Mandal, mandal_id)
    return {"mandal_id": mandal_id, "serviceable": bool(m and m.serviceable)}
