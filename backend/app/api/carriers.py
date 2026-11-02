from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.core.rbac import Role
from app.models.carrier import Carrier
from app.services import audit

router = APIRouter(prefix="/carriers", tags=["carriers"])

_admin = require_roles(Role.SUPERADMIN)
_ops = require_roles(Role.SUPERADMIN, Role.MANDAL_MANAGER, Role.FINANCE, Role.TRANSPORT)


def _json(c: Carrier) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "code": c.code,
        "contact_phone": c.contact_phone,
        "contact_email": c.contact_email,
        "vehicle_classes": c.vehicle_classes or [],
        "service_areas": c.service_areas or [],
        "kyc_status": c.kyc_status,
        "active": c.active,
        "rating": c.rating,
    }


class CarrierCreate(BaseModel):
    name: str
    code: str
    contact_phone: str | None = None
    contact_email: str | None = None
    vehicle_classes: list[str] | None = None
    service_areas: list[str] | None = None


class CarrierUpdate(BaseModel):
    contact_phone: str | None = None
    contact_email: str | None = None
    vehicle_classes: list[str] | None = None
    service_areas: list[str] | None = None
    kyc_status: str | None = None
    active: bool | None = None


@router.get("")
def list_carriers(
    active_only: bool = False,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Carrier).order_by(Carrier.name)
    if active_only:
        stmt = stmt.where(Carrier.active.is_(True))
    return [_json(c) for c in db.scalars(stmt)]


@router.post("", status_code=status.HTTP_201_CREATED)
def onboard_carrier(body: CarrierCreate, user=Depends(_admin), db: Session = Depends(get_db)):
    if db.scalar(select(Carrier).where(Carrier.code == body.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Carrier code already exists")
    c = Carrier(
        name=body.name, code=body.code, contact_phone=body.contact_phone,
        contact_email=body.contact_email, vehicle_classes=body.vehicle_classes or [],
        service_areas=body.service_areas or [], kyc_status="pending", active=True,
    )
    db.add(c)
    db.flush()
    audit.record(db, actor_id=user.id, action="carrier.onboard", object_type="carrier",
                 object_id=c.id, new_values={"code": c.code})
    db.commit()
    db.refresh(c)
    return _json(c)


@router.patch("/{carrier_id}")
def update_carrier(carrier_id: int, body: CarrierUpdate, user=Depends(_admin), db: Session = Depends(get_db)):
    c = db.get(Carrier, carrier_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Carrier not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(c, field, value)
    audit.record(db, actor_id=user.id, action="carrier.update", object_type="carrier",
                 object_id=c.id, new_values=body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(c)
    return _json(c)
