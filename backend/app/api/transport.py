from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.money import money
from app.core.rbac import Role
from app.models.catalog import Commodity
from app.models.common import OrderStatus as S, utcnow
from app.models.finance import Payout
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
    # A courier only sees jobs that are theirs or still unclaimed; staff
    # (leader/superadmin) oversee the whole pool.
    is_courier = user.role == Role.TRANSPORT
    jobs = []
    earnings_active = money(0)
    for o in orders:
        shipment = db.scalar(select(Shipment).where(Shipment.order_id == o.id))
        carrier_id = shipment.carrier_id if shipment else None
        mine = carrier_id == user.id
        claimable = carrier_id is None
        if is_courier and not (mine or claimable):
            continue  # another courier already owns this delivery
        quote = o.quote or {}
        charge = money(quote.get("transport_charge", 0))
        if o.status in _ACTIVE and (mine or not is_courier):
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
            "mine": mine,
            "claimable": claimable,
        })
    return {"jobs": jobs, "active_earning": str(earnings_active), "active_count":
            sum(1 for j in jobs if j["status"] in [str(s) for s in _ACTIVE])}


def _earnings(db: Session, user) -> dict:
    """A transport partner's delivery earnings: accrued-but-unpaid vs paid payouts
    (settled trips) plus in-progress charges on trips still in flight."""
    payouts = list(db.scalars(select(Payout).where(
        Payout.payee_type == "transport", Payout.seller_id == user.id).order_by(Payout.id.desc())))
    pending = money(0)
    paid = money(0)
    trips = []
    for p in payouts:
        amt = money(p.amount)
        if p.status == "processed":
            paid += amt
        else:
            pending += amt
        o = db.get(Order, p.order_id) if p.order_id else None
        t = (o.accepted_terms or {}) if o else {}
        c = db.get(Commodity, t.get("commodity_id")) if t.get("commodity_id") else None
        trips.append({
            "order_id": p.order_id,
            "public_id": o.public_id if o else None,
            "commodity": c.name if c else None,
            "quantity": t.get("quantity"), "unit": t.get("unit", "kg"),
            "amount": str(amt),
            "status": "paid" if p.status == "processed" else "awaiting payout",
            "batch_id": p.batch_id,
        })
    # Trips still moving — charge not yet accrued (order not settled).
    in_progress = money(0)
    for o in db.scalars(select(Order).where(Order.status.in_(_ACTIVE))):
        sh = db.scalar(select(Shipment).where(Shipment.order_id == o.id))
        if sh and sh.carrier_id == user.id:
            in_progress += money((o.quote or {}).get("transport_charge", 0))
    return {
        "trips": trips,
        "paid_total": str(paid),
        "pending_total": str(pending),
        "in_progress_total": str(in_progress),
        "lifetime_total": str(paid + pending),
        "trip_count": len(trips),
    }


@router.get("/earnings")
def transport_earnings(user=Depends(_transport), db: Session = Depends(get_db)):
    """Per-trip delivery earnings + paid/pending/in-progress totals for the courier."""
    return _earnings(db, user)


@router.get("/earnings.csv")
def transport_earnings_csv(user=Depends(_transport), db: Session = Depends(get_db)):
    import csv
    import io

    rep = _earnings(db, user)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["order", "commodity", "quantity", "unit", "amount_inr", "status", "batch"])
    for t in rep["trips"]:
        w.writerow([t["public_id"], t["commodity"], t["quantity"], t["unit"],
                    t["amount"], t["status"], t["batch_id"] or ""])
    w.writerow([])
    w.writerow(["paid_total", rep["paid_total"]])
    w.writerow(["pending_total", rep["pending_total"]])
    w.writerow(["in_progress_total", rep["in_progress_total"]])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="transport-earnings.csv"'})


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
    if (shipment.carrier_id is not None and shipment.carrier_id != user.id
            and user.role == Role.TRANSPORT):
        raise HTTPException(403, "This delivery is assigned to another courier.")
    shipment.last_lat = body.lat
    shipment.last_lng = body.lng
    shipment.last_location_at = utcnow()

    # Ping the buyer once when the courier gets close to the delivery address.
    nearby_km = None
    try:
        from app.core.config import settings
        from app.models.location import Mandal
        from app.services.distance import haversine_km
        from app.services import notify

        terms = order.accepted_terms or {}
        dest_id = terms.get("destination_mandal_id") or terms.get("mandal_id")
        m = db.get(Mandal, dest_id) if dest_id else None
        if m and m.latitude is not None and m.longitude is not None:
            nearby_km = round(haversine_km(body.lat, body.lng, float(m.latitude), float(m.longitude)), 1)
            pod = dict(shipment.proof_of_delivery or {})
            if nearby_km <= settings.courier_nearby_km and not pod.get("nearby_notified"):
                notify.send(db, user_id=order.buyer_id, title="Your courier is nearby",
                            body=f"Your delivery is about {nearby_km} km away. Keep your delivery code ready.",
                            object_type="order", object_id=order.public_id)
                pod["nearby_notified"] = True
                shipment.proof_of_delivery = pod
    except Exception:
        pass  # a tracking ping must never fail on the nearby-notify side effect

    db.commit()
    return {"ok": True, "at": shipment.last_location_at.isoformat(), "distance_km": nearby_km}
