import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.location import District, Mandal, State

router = APIRouter(prefix="/locations", tags=["locations"])


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


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
def mandals(district_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(Mandal).order_by(Mandal.name)
    if district_id is not None:
        stmt = stmt.where(Mandal.district_id == district_id)
    rows = db.scalars(stmt)
    return [
        {
            "id": m.id,
            "name": m.name,
            "district_id": m.district_id,
            "serviceable": m.serviceable,
        }
        for m in rows
    ]


@router.get("/nearest")
def nearest(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    db: Session = Depends(get_db),
):
    """Nearest mandal to a GPS point (device geolocation at sign-up/checkout),
    by straight-line distance to mandal centroids. Prefers serviceable mandals;
    falls back to the nearest of any if none serviceable is close."""
    rows = [
        m for m in db.scalars(select(Mandal))
        if m.latitude is not None and m.longitude is not None
    ]
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No mandal coordinates available")
    scored = sorted(
        ((_haversine_km(lat, lng, float(m.latitude), float(m.longitude)), m) for m in rows),
        key=lambda t: t[0],
    )
    serviceable = [t for t in scored if t[1].serviceable]
    dist, m = (serviceable or scored)[0]
    return {
        "mandal_id": m.id,
        "name": m.name,
        "district_id": m.district_id,
        "serviceable": bool(m.serviceable),
        "distance_km": round(dist, 1),
    }


@router.get("/serviceability")
def serviceability(mandal_id: int, db: Session = Depends(get_db)):
    m = db.get(Mandal, mandal_id)
    return {"mandal_id": mandal_id, "serviceable": bool(m and m.serviceable)}
