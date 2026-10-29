from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.core.ids import idempotency_key as gen_idem
from app.core.ids import lot_id as gen_lot
from app.core.ids import shipment_id as gen_shipment
from app.core.money import D, money
from app.core.rbac import Role
from app.models.common import InspectionOutcome, LedgerDirection
from app.models.common import OrderStatus as S
from app.models.common import utcnow
from app.models.finance import Payment, Payout
from app.models.marketplace import Listing
from app.models.order import (
    Lot,
    Order,
    OrderLine,
    Package,
    Shipment,
    ShipmentEvent,
)
from app.services import audit
from app.services import ledger
from app.services.ledger import Leg
from app.services.state_machine import InvalidTransition, transition

router = APIRouter(prefix="/orders", tags=["orders"])


def _get_order(order_id: int, db: Session) -> Order:
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


def _require_party(order: Order, user, *, buyer=False, seller=False):
    staff = user.role in (Role.SUPERADMIN, Role.FINANCE, Role.MANDAL_MANAGER)
    if staff:
        return
    if buyer and user.id == order.buyer_id:
        return
    if seller and user.id == order.seller_id:
        return
    if not buyer and not seller and user.id in (order.buyer_id, order.seller_id):
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted for this order")


def _order_json(order: Order, db: Session) -> dict:
    return {
        "id": order.id,
        "public_id": order.public_id,
        "buyer_id": order.buyer_id,
        "seller_id": order.seller_id,
        "status": order.status,
        "accepted_terms": order.accepted_terms,
        "quote": order.quote,
        "buyer_total": None if order.buyer_total is None else str(order.buyer_total),
        "seller_payable": None if order.seller_payable is None else str(order.seller_payable),
        "history": [
            {
                "from": e.from_status,
                "to": e.to_status,
                "actor_id": e.actor_id,
                "reason_code": e.reason_code,
                "at": e.at.isoformat(),
            }
            for e in order.status_events
        ],
    }


def _safe_transition(db, order, to, **kw):
    try:
        transition(db, order, to, **kw)
    except InvalidTransition as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))


@router.get("")
def my_orders(user=Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Order).where(or_(Order.buyer_id == user.id, Order.seller_id == user.id))
        .order_by(Order.created_at.desc())
    )
    return [_order_json(o, db) for o in rows]


@router.get("/{order_id}")
def get_order(order_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    order = _get_order(order_id, db)
    _require_party(order, user)
    return _order_json(order, db)


# --- Inspection assignment & buyer approval ------------------------------

class AssignInspection(BaseModel):
    agent_id: int


@router.post("/{order_id}/assign-inspection")
def assign_inspection(
    order_id: int,
    body: AssignInspection,
    user=Depends(require_roles(Role.MANDAL_MANAGER, Role.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    order = _get_order(order_id, db)
    order.assigned_agent_id = body.agent_id
    _safe_transition(db, order, S.INSPECTION_ASSIGNED, actor_id=user.id,
                     reason_code="agent_assigned", note=f"agent={body.agent_id}")
    audit.record(db, actor_id=user.id, action="inspection.assign",
                 object_type="order", object_id=order.public_id,
                 new_values={"agent_id": body.agent_id})
    db.commit()
    return _order_json(order, db)


@router.post("/{order_id}/buyer-approve")
def buyer_approve(order_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    order = _get_order(order_id, db)
    _require_party(order, user, buyer=True)
    if order.status != S.BUYER_APPROVAL_PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Order not awaiting buyer approval")
    _safe_transition(db, order, S.CONFIRMED, actor_id=user.id, reason_code="buyer_approved")
    db.commit()
    return _order_json(order, db)


# --- Confirmation (snapshot quote) ---------------------------------------

class ConfirmBody(BaseModel):
    route_km: float = 0


@router.post("/{order_id}/confirm-quote")
def confirm_quote(
    order_id: int,
    body: ConfirmBody,
    idempotency_key: str | None = Header(default=None),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lock the server-computed quote onto a CONFIRMED order and move to PAYMENT_PENDING."""
    from app.api.pricing import active_rule_for, order_pricing_context
    from app.services.pricing_engine import QuoteInput, compute

    order = _get_order(order_id, db)
    _require_party(order, user, buyer=True)
    if order.status != S.CONFIRMED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Order is not in CONFIRMED state")
    if order.quote is not None:
        return _order_json(order, db)  # idempotent: already quoted

    terms = order.accepted_terms
    product_value = D(terms["price_per_unit"]) * D(terms["quantity"])
    mandal_id, handling_class = order_pricing_context(db, order)

    rule = active_rule_for(db, mandal_id=mandal_id, handling_class=handling_class)
    if not rule:
        raise HTTPException(status.HTTP_409_CONFLICT, "No published pricing rule applies")

    quote = compute(rule, QuoteInput(
        product_value=product_value, billable_kg=D(terms["quantity"]), route_km=D(body.route_km),
    ))
    order.quote = quote.to_json()
    order.pricing_rule_version = rule.version
    order.buyer_total = money(quote.buyer_total)
    order.seller_payable = money(quote.seller_payable)
    _safe_transition(db, order, S.PAYMENT_PENDING, actor_id=user.id, reason_code="quote_locked")
    db.commit()
    return _order_json(order, db)


# --- Payment (mock provider) ---------------------------------------------

@router.post("/{order_id}/pay")
def pay(
    order_id: int,
    idempotency_key: str | None = Header(default=None),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mock payment capture. Posts the full double-entry ledger for the order.

    A real provider webhook would do this server-side; the mock keeps the same
    idempotent, ledger-backed path so swapping it in is isolated.
    """
    order = _get_order(order_id, db)
    _require_party(order, user, buyer=True)

    # Idempotent replay: a repeated key returns the (already paid) order, even
    # though the order has moved past PAYMENT_PENDING.
    idem = idempotency_key or gen_idem()
    existing = db.scalar(select(Payment).where(Payment.idempotency_key == idem))
    if existing:
        return _order_json(order, db)

    if order.status != S.PAYMENT_PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Order not awaiting payment")
    if order.quote is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No locked quote to pay")

    q = order.quote
    buyer_total = money(order.buyer_total)
    txn = f"pay:{order.public_id}"

    legs = [
        Leg("cash_clearing", LedgerDirection.DEBIT, buyer_total, "buyer payment captured"),
        Leg("seller_payable", LedgerDirection.CREDIT, money(order.seller_payable), "seller proceeds"),
        Leg("platform_revenue", LedgerDirection.CREDIT, money(q["service_fee"]), "service fee"),
        Leg("transport_payable", LedgerDirection.CREDIT, money(q["transport_charge"]), "transport"),
        Leg("agent_fee_payable", LedgerDirection.CREDIT, money(q["inspection_fee"]), "inspection"),
        Leg("packing_revenue", LedgerDirection.CREDIT, money(q["packing_fee"]), "packing"),
        Leg("tax_payable", LedgerDirection.CREDIT, money(q["tax"]), "tax"),
    ]
    # Drop zero legs to keep the ledger tidy (balance is preserved).
    legs = [l for l in legs if money(l.amount) != money(0)]
    ledger.post(db, txn_group=txn, legs=legs, order_id=order.id, currency=q["currency"])

    db.add(Payment(
        order_id=order.id, provider="mock", provider_ref=txn, idempotency_key=idem,
        amount=buyer_total, currency=q["currency"], status="paid",
    ))
    _safe_transition(db, order, S.PAID, actor_id=user.id, reason_code="payment_captured")
    audit.record(db, actor_id=user.id, action="order.pay", object_type="order",
                 object_id=order.public_id, new_values={"amount": str(buyer_total)})
    db.commit()
    return _order_json(order, db)


# --- Packing -> lot + package --------------------------------------------

@router.post("/{order_id}/packing-complete")
def packing_complete(
    order_id: int,
    user=Depends(require_roles(Role.FIELD_AGENT, Role.MANDAL_MANAGER, Role.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    order = _get_order(order_id, db)
    if order.status != S.PAID:
        raise HTTPException(status.HTTP_409_CONFLICT, "Order not paid")
    terms = order.accepted_terms
    line = order.lines[0] if order.lines else None
    listing = db.get(Listing, line.listing_id) if line and line.listing_id else None

    commodity_id = (listing.commodity_id if listing else None) or terms.get("commodity_id")
    lot = Lot(
        public_id=gen_lot(),
        source_listing_id=listing.id if listing else None,
        seller_id=order.seller_id,
        commodity_id=commodity_id,
        quantity=D(terms["quantity"]),
        grade_spec_id=terms.get("grade_spec_id"),
        seal_ref=gen_lot(),
        status="packed",
    )
    db.add(lot)
    db.flush()
    pkg = Package(
        lot_id=lot.id,
        qr_code=lot.public_id,
        net_weight=D(terms["quantity"]),
        package_count=1,
        label_data={"order": order.public_id, "grade": terms.get("grade_spec_id")},
        packing_status="packed",
    )
    db.add(pkg)
    if line:
        line.lot_id = lot.id
        line.allocation_status = "packed"
    _safe_transition(db, order, S.PACKING, actor_id=user.id, reason_code="packing_started")
    _safe_transition(db, order, S.READY_FOR_PICKUP, actor_id=user.id, reason_code="lot_sealed")
    db.commit()
    return {"order": _order_json(order, db), "lot_id": lot.public_id, "qr": pkg.qr_code}


# --- Shipment milestones --------------------------------------------------

_SHIP_FLOW = {
    "picked_up": S.PICKED_UP,
    "in_transit": S.IN_TRANSIT,
    "out_for_delivery": S.OUT_FOR_DELIVERY,
    "delivered": S.DELIVERED_PENDING_ACCEPTANCE,
}


class ShipEvent(BaseModel):
    event: str
    evidence_ref: str | None = None


@router.post("/{order_id}/shipment/event")
def shipment_event(
    order_id: int,
    body: ShipEvent,
    user=Depends(require_roles(Role.TRANSPORT, Role.MANDAL_MANAGER, Role.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    order = _get_order(order_id, db)
    to = _SHIP_FLOW.get(body.event)
    if not to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown shipment event")

    shipment = db.scalar(select(Shipment).where(Shipment.order_id == order.id))
    if shipment is None:
        shipment = Shipment(public_id=gen_shipment(), order_id=order.id,
                            carrier_id=user.id, status="created")
        db.add(shipment)
        db.flush()
    shipment.status = body.event
    db.add(ShipmentEvent(shipment_id=shipment.id, event=body.event, actor_id=user.id,
                         evidence_ref=body.evidence_ref, at=utcnow()))
    _safe_transition(db, order, to, actor_id=user.id, reason_code=f"ship_{body.event}")
    db.commit()
    return {"order": _order_json(order, db), "shipment_id": shipment.public_id}


# --- Buyer acceptance -> settlement --------------------------------------

@router.post("/{order_id}/acceptance")
def acceptance(order_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    order = _get_order(order_id, db)
    _require_party(order, user, buyer=True)
    if order.status != S.DELIVERED_PENDING_ACCEPTANCE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Order not awaiting acceptance")

    _safe_transition(db, order, S.COMPLETED, actor_id=user.id, reason_code="buyer_accepted")

    # Release reserved -> sold on the listing(s).
    for line in order.lines:
        if line.listing_id:
            listing = db.get(Listing, line.listing_id, with_for_update=True)
            if listing:
                dq = D(line.quantity)
                listing.reserved_qty = max(D("0"), D(listing.reserved_qty) - dq)
                listing.sold_qty = D(listing.sold_qty) + dq
        line.allocation_status = "delivered"

    # Settle the seller: move seller_payable liability to cash out + Payout record.
    payable = money(order.seller_payable or 0)
    if payable > money(0):
        idem = f"payout:{order.public_id}"
        if not db.scalar(select(Payout).where(Payout.idempotency_key == idem)):
            ledger.post(
                db,
                txn_group=f"settle:{order.public_id}",
                order_id=order.id,
                currency=(order.quote or {}).get("currency", "INR"),
                legs=[
                    Leg("seller_payable", LedgerDirection.DEBIT, payable, "release to seller"),
                    Leg("cash_clearing", LedgerDirection.CREDIT, payable, "seller payout"),
                ],
            )
            db.add(Payout(order_id=order.id, seller_id=order.seller_id, amount=payable,
                          status="processed", idempotency_key=idem))
    _safe_transition(db, order, S.SETTLED, actor_id=user.id, reason_code="settled")
    audit.record(db, actor_id=user.id, action="order.settle", object_type="order",
                 object_id=order.public_id, new_values={"seller_payout": str(payable)})
    db.commit()
    return _order_json(order, db)


# --- Cancellation ---------------------------------------------------------

class CancelBody(BaseModel):
    reason_code: str = "buyer_cancelled"
    note: str | None = None


@router.post("/{order_id}/cancel")
def cancel(order_id: int, body: CancelBody, user=Depends(get_current_user), db: Session = Depends(get_db)):
    order = _get_order(order_id, db)
    _require_party(order, user)
    try:
        transition(db, order, S.CANCELLED, actor_id=user.id,
                   reason_code=body.reason_code, note=body.note)
    except InvalidTransition:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot cancel from {order.status}")

    # Release reserved quantity back to availability.
    for line in order.lines:
        if line.listing_id and line.allocation_status in ("reserved", "packed"):
            listing = db.get(Listing, line.listing_id, with_for_update=True)
            if listing:
                listing.reserved_qty = max(D("0"), D(listing.reserved_qty) - D(line.quantity))
            line.allocation_status = "released"
    audit.record(db, actor_id=user.id, action="order.cancel", object_type="order",
                 object_id=order.public_id, reason=body.reason_code)
    db.commit()
    return _order_json(order, db)
