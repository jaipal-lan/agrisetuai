from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.money import money
from app.core.rbac import Role
from app.models.common import OrderStatus as S, utcnow
from app.models.order import Order, Shipment

router = APIRouter(prefix="/transport", tags=["transport"])

_transport = require_roles(Role.TRANSPORT, Role.FIELD_LEADER, Role.SUPERADMIN)

# Order states a transport partner acts on.
_ACTIVE = [S.READY_FOR_PICKUP, S.PICKED_UP, S.IN_TRANSIT, S.OUT_FOR_DELIVERY]


@router.get("/jobs")
def transport_jobs(include_done: bool = False, user=Depends(_transport), db: Session = Depends(get_db)):
    """Pickups/deliveries for the transport partner, with the buyer-paid transport
    charge as the trip earning. Includes completed trips when include_done=true."""
    states = list(_ACTIVE)
    if include_done:
        states += [S.DELIVERED_PENDING_ACCEPTANCE, S.COMPLETED, S.SETTLED]
    orders = db.scalars(select(Order).where(Order.status.in_(states)).order_by(Order.id.desc()))
    jobs = []
    earnings_active = money(0)
    for o in orders:
        shipment = db.scalar(select(Shipment).where(Shipment.order_id == o.id))
        quote = o.quote or {}
        charge = money(quote.get("transport_charge", 0))
        if o.status in _ACTIVE:
            earnings_active += charge
        jobs.append({
            "order_id": o.id,
            "public_id": o.public_id,
            "status": o.status,
            "courier_name": shipment.courier_name if shipment else None,
            "vehicle_class": shipment.vehicle_class if shipment else None,
            "shipment_status": shipment.status if shipment else None,
            "transport_charge": str(charge),
            "quantity": (o.accepted_terms or {}).get("quantity"),
            "unit": (o.accepted_terms or {}).get("unit"),
        })
    return {"jobs": jobs, "active_earning": str(earnings_active), "active_count":
            sum(1 for j in jobs if j["status"] in [str(s) for s in _ACTIVE])}


class LocationPing(BaseModel):
    lat: float
    lng: float


@router.post("/orders/{order_id}/location")
def post_location(order_id: int, body: LocationPing, user=Depends(_transport),
                  db: Session = Depends(get_db)):
    """The courier app posts its live GPS position for an in-flight order, so the
    buyer can watch the delivery approach. Only accepted while the order is out
    for pickup/transit/delivery."""
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(404, "Order not found.")
    if order.status not in _ACTIVE:
        raise HTTPException(409, "Order is not in a deliverable state.")
    if not (-90 <= body.lat <= 90 and -180 <= body.lng <= 180):
        raise HTTPException(400, "Invalid coordinates.")
    shipment = db.scalar(select(Shipment).where(Shipment.order_id == order.id))
    if shipment is None:
        raise HTTPException(404, "No shipment for this order yet.")
    shipment.last_lat = body.lat
    shipment.last_lng = body.lng
    shipment.last_location_at = utcnow()
    db.commit()
    return {"ok": True, "at": shipment.last_location_at.isoformat()}
