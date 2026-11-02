from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.location import Mandal
from app.services import distance

router = APIRouter(prefix="/logistics", tags=["logistics"])


@router.get("/distance")
def distance_between(
    from_mandal_id: int,
    to_mandal_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Computed road distance between two mandals, with how it was derived.

    Used by the quote preview and by confirm-quote when no override is given.
    """
    if not db.get(Mandal, from_mandal_id) or not db.get(Mandal, to_mandal_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mandal not found")
    return distance.route_km_between(db, from_mandal_id, to_mandal_id).to_json()


@router.get("/serviceability")
def serviceability(mandal_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    m = db.get(Mandal, mandal_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mandal not found")
    return {
        "mandal_id": m.id,
        "name": m.name,
        "serviceable": m.serviceable,
        "has_coordinates": m.latitude is not None and m.longitude is not None,
    }
