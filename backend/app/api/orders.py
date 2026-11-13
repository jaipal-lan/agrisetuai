from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
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
    Inspection,
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
    staff = user.role in (Role.SUPERADMIN, Role.FIELD_MANAGER, Role.FIELD_LEADER)
    if staff:
        return
    if buyer and user.id == order.buyer_id:
        return
    if seller and user.id == order.seller_id:
        return
    if not buyer and not seller and user.id in (order.buyer_id, order.seller_id):
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted for this order")


def _order_json(order: Order, db: Session, viewer=None) -> dict:
    inspections = db.scalars(
        select(Inspection).where(Inspection.order_id == order.id).order_by(Inspection.id)
    )
    shipment = db.scalar(select(Shipment).where(Shipment.order_id == order.id))
    out = {
        "id": order.id,
        "public_id": order.public_id,
        "buyer_id": order.buyer_id,
        "seller_id": order.seller_id,
        "assigned_agent_id": order.assigned_agent_id,
        "status": order.status,
        "accepted_terms": order.accepted_terms,
        "quote": order.quote,
        "packing_video": order.packing_video,
        "buyer_total": None if order.buyer_total is None else str(order.buyer_total),
        "seller_payable": None if order.seller_payable is None else str(order.seller_payable),
        "inspections": [
            {
                "id": i.id,
                "outcome": i.outcome,
                "net_qty": None if i.net_qty is None else str(i.net_qty),
                "gross_weight": None if i.gross_weight is None else str(i.gross_weight),
                "tare_weight": None if i.tare_weight is None else str(i.tare_weight),
                "checklist": i.checklist,
                "evidence": i.evidence,
                "reason_codes": i.reason_codes,
            }
            for i in inspections
        ],
        "shipment": None
        if shipment is None
        else {
            "public_id": shipment.public_id,
            "status": shipment.status,
            "vehicle_class": shipment.vehicle_class,
            "courier_id": shipment.courier_id,
            "courier_name": shipment.courier_name,
        },
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
    # Delivery OTP is only shown to the buyer / staff, never to unrelated roles.
    if shipment and shipment.proof_of_delivery and viewer is not None:
        staff = viewer.role in (Role.SUPERADMIN, Role.FIELD_MANAGER, Role.FIELD_LEADER, Role.TRANSPORT)
        if staff or viewer.id == order.buyer_id:
            out["delivery_otp"] = shipment.proof_of_delivery.get("otp")
    return out


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
    return [_order_json(o, db, user) for o in rows]


@router.get("/{order_id}")
def get_order(order_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    order = _get_order(order_id, db)
    _require_party(order, user)
    return _order_json(order, db, user)


@router.post("/{order_id}/reorder")
def reorder(order_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Buy the same product again: re-open a negotiation on the source listing at
    the previous terms. If that lot is gone, point the buyer to the product page."""
    from datetime import timedelta
    from app.core.money import qty as _qty
    from app.models.common import OfferStatus, utcnow
    from app.models.marketplace import Offer, OfferVersion
    from app.services import notify

    order = _get_order(order_id, db)
    _require_party(order, user, buyer=True)
    terms = order.accepted_terms or {}
    line = order.lines[0] if order.lines else None
    listing = db.get(Listing, line.listing_id) if line and line.listing_id else None
    commodity_id = terms.get("commodity_id") or (listing.commodity_id if listing else None)

    # Prefer the original lot; if it's gone, fall back to any active listing of the
    # same commodity (the original seller first, then the cheapest) so a returning
    # buyer can always reorder.
    if not listing or listing.status != "open" or _qty(listing.available_qty) <= _qty(0):
        alts = [l for l in db.scalars(select(Listing).where(
            Listing.commodity_id == commodity_id, Listing.status == "open"))
            if l.seller_id != user.id and _qty(l.available_qty) > _qty(0)] if commodity_id else []
        if not alts:
            return {"reorderable": False, "commodity_id": commodity_id,
                    "reason": "No active listing for this product right now. Post a requirement (RFQ) to source it."}
        alts.sort(key=lambda l: (l.seller_id != order.seller_id, float(l.asking_price)))
        listing = alts[0]

    want = _qty(terms.get("quantity") or 0)
    avail = _qty(listing.available_qty)
    want = min(want, avail) if want > _qty(0) else avail  # clamp to what's left

    offer = Offer(listing_id=listing.id, buyer_id=user.id, seller_id=listing.seller_id,
                  status=OfferStatus.OPEN)
    db.add(offer)
    db.flush()
    now = utcnow()
    db.add(OfferVersion(
        offer_id=offer.id, version_no=1, proposer_role="buyer", proposer_id=user.id,
        price_per_unit=D(terms.get("price_per_unit") or listing.asking_price),
        quantity=want, unit=listing.unit,
        grade_spec_id=terms.get("grade_spec_id") or listing.grade_spec_id,
        expires_at=now + timedelta(hours=48), created_at=now,
    ))
    notify.send(db, user_id=listing.seller_id, title="Repeat offer received",
                body=f"A returning buyer re-ordered {want} {listing.unit}.",
                object_type="offer", object_id=offer.id)
    db.commit()
    return {"reorderable": True, "offer_id": offer.id, "listing_id": listing.id,
            "commodity_id": listing.commodity_id}


# --- AgriSetu Verified Lot Certificate ------------------------------------

# Attributes a physical field inspection can establish vs. those that need a lab.
_NOT_TESTED_NOTE = (
    "This certificate records what the field agent observed and measured on site. "
    "It does NOT test for pesticide residues, chemical adulteration, aflatoxins or "
    "microbial safety; those require accredited laboratory analysis. This is an "
    "AgriSetu verification, not a government or statutory certification."
)


@router.get("/{order_id}/certificate")
def verified_lot_certificate(order_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """The AgriSetu Verified Lot Certificate shown to the buyer before payment.

    Transparently separates what was observed, what was measured, and what was
    NOT tested. Never implies statutory certification.
    """
    from app.models.catalog import Commodity, GradeSpec, Variety

    order = _get_order(order_id, db)
    _require_party(order, user)

    insp = db.scalar(
        select(Inspection)
        .where(Inspection.order_id == order.id,
               Inspection.outcome.in_([InspectionOutcome.PASS, InspectionOutcome.PASS_WITH_ADJUSTMENT]))
        .order_by(Inspection.id.desc())
    )
    if insp is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No passed inspection yet; certificate not available")

    terms = order.accepted_terms or {}
    commodity = db.get(Commodity, terms.get("commodity_id")) if terms.get("commodity_id") else None
    variety = None
    grade = db.get(GradeSpec, terms.get("grade_spec_id")) if terms.get("grade_spec_id") else None
    lot = db.scalar(select(Lot).where(Lot.id.in_([l.lot_id for l in order.lines if l.lot_id]))) if order.lines else None

    checklist = insp.checklist or {}
    return {
        "certificate_id": f"ASVL-{order.public_id}",
        "order_public_id": order.public_id,
        "issued_for_buyer_id": order.buyer_id,
        "product": {
            "commodity": commodity.name if commodity else None,
            "commodity_te": commodity.name_te if commodity else None,
            "grade": grade.label if grade else None,
            "grade_attributes": grade.attributes if grade else None,
            "claim_status": terms.get("claim_status"),
        },
        "observed": {
            "outcome": insp.outcome,
            "checklist": checklist,
            "reason_codes": insp.reason_codes,
            "evidence_refs": (insp.evidence or {}).get("refs", []),
        },
        "measured": {
            "declared_qty": None if insp.declared_qty is None else str(insp.declared_qty),
            "gross_weight_kg": None if insp.gross_weight is None else str(insp.gross_weight),
            "tare_weight_kg": None if insp.tare_weight is None else str(insp.tare_weight),
            "net_qty_kg": None if insp.net_qty is None else str(insp.net_qty),
            "moisture_pct": checklist.get("moisture_pct"),
            "scale_ref": insp.scale_ref,
        },
        "lot": None if lot is None else {"public_id": lot.public_id, "seal_ref": lot.seal_ref},
        "inspected_by_agent_id": insp.agent_id,
        "inspected_at": insp.created_at.isoformat() if insp.created_at else None,
        "not_tested_note": _NOT_TESTED_NOTE,
    }


@router.get("/{order_id}/invoice.pdf")
def order_invoice_pdf(order_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """A4 tax-invoice / receipt PDF for the order's parties (and staff)."""
    from fastapi.responses import Response

    from app.models.catalog import Commodity
    from app.models.user import User
    from app.services.invoice_pdf import build_invoice_pdf

    order = _get_order(order_id, db)
    _require_party(order, user)
    if order.quote is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Invoice unavailable until the quote is confirmed")

    terms = order.accepted_terms or {}
    commodity = db.get(Commodity, terms.get("commodity_id")) if terms.get("commodity_id") else None
    buyer = db.get(User, order.buyer_id)
    seller = db.get(User, order.seller_id)
    paid_states = (S.PAID, S.PACKING, S.READY_FOR_PICKUP, S.PICKED_UP, S.IN_TRANSIT,
                   S.OUT_FOR_DELIVERY, S.DELIVERED_PENDING_ACCEPTANCE, S.COMPLETED, S.SETTLED)
    pdf = build_invoice_pdf(
        order=order,
        buyer_name=(buyer.name if buyer else None) or (buyer.phone if buyer else ""),
        seller_name=(seller.name if seller else None) or (seller.phone if seller else ""),
        commodity_name=commodity.name if commodity else "Produce",
        paid=order.status in paid_states,
    )
    filename = f"agrisetu-invoice-{order.public_id}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# --- Inspection assignment & buyer approval ------------------------------

class AssignInspection(BaseModel):
    agent_id: int


@router.post("/{order_id}/assign-inspection")
def assign_inspection(
    order_id: int,
    body: AssignInspection,
    user=Depends(require_roles(Role.FIELD_LEADER, Role.SUPERADMIN)),
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
    return _order_json(order, db, user)


class ReassignBody(BaseModel):
    agent_id: int
    reason: str


@router.post("/{order_id}/reassign-inspection")
def reassign_inspection(
    order_id: int,
    body: ReassignBody,
    user=Depends(require_roles(Role.FIELD_LEADER, Role.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    order = _get_order(order_id, db)
    if order.status not in (S.INSPECTION_ASSIGNED, S.INSPECTION_IN_PROGRESS, S.INSPECTION_HOLD):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot reassign in this state")
    old = order.assigned_agent_id
    order.assigned_agent_id = body.agent_id
    audit.record(
        db,
        actor_id=user.id,
        action="inspection.reassign",
        object_type="order",
        object_id=order.public_id,
        reason=body.reason,
        old_values={"agent_id": old},
        new_values={"agent_id": body.agent_id},
    )
    db.commit()
    return _order_json(order, db, user)


class ApproveBody(BaseModel):
    accepted_quantity: float | None = None


@router.post("/{order_id}/buyer-approve")
def buyer_approve(
    order_id: int,
    body: ApproveBody | None = Body(default=None),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = _get_order(order_id, db)
    _require_party(order, user, buyer=True)
    if order.status != S.BUYER_APPROVAL_PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Order not awaiting buyer approval")
    terms = dict(order.accepted_terms or {})
    if terms.get("adjustment_pending"):
        proposed = D(terms.get("proposed_quantity") or terms["quantity"])
        accepted = D(body.accepted_quantity) if body and body.accepted_quantity is not None else proposed
        original = D(terms["quantity"])
        # Update reserved stock to the accepted net quantity (never overwrite history: keep original).
        delta = original - accepted
        for line in order.lines:
            if line.listing_id:
                listing = db.get(Listing, line.listing_id, with_for_update=True)
                if listing and delta != D(0):
                    listing.reserved_qty = max(D("0"), D(listing.reserved_qty) - delta)
            line.accepted_quantity = accepted
            line.quantity = accepted
        terms["original_quantity"] = str(original)
        terms["quantity"] = str(accepted)
        terms["adjustment_pending"] = False
        terms["adjustment_accepted"] = True
        order.accepted_terms = terms
    _safe_transition(db, order, S.CONFIRMED, actor_id=user.id, reason_code="buyer_approved")
    db.commit()
    return _order_json(order, db, user)


# --- Confirmation (snapshot quote) ---------------------------------------

class ConfirmBody(BaseModel):
    # Omit route_km (or send null) to let the server compute it from mandal
    # coordinates. An explicit value is treated as a manual override.
    route_km: float | None = None
    # Delivery destination. Prefer address_id (one of the buyer's saved
    # addresses, which also carries the street line for the courier); to_mandal_id
    # is the lower-level fallback when the buyer has no saved address.
    address_id: int | None = None
    to_mandal_id: int | None = None


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
    from app.services import distance
    from app.services.pricing_engine import QuoteInput, compute

    order = _get_order(order_id, db)
    _require_party(order, user, buyer=True)
    if order.status != S.CONFIRMED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Order is not in CONFIRMED state")
    if order.quote is not None:
        return _order_json(order, db, user)  # idempotent: already quoted

    terms = order.accepted_terms
    product_value = D(terms["price_per_unit"]) * D(terms["quantity"])
    mandal_id, handling_class = order_pricing_context(db, order)

    rule = active_rule_for(db, mandal_id=mandal_id, handling_class=handling_class)
    if not rule:
        raise HTTPException(status.HTTP_409_CONFLICT, "No published pricing rule applies")

    # Delivery destination, in priority order: a chosen saved address (which also
    # supplies the street line for the courier), then an explicit mandal, then
    # whatever was already on the order, finally the produce's own mandal.
    delivery_label = terms.get("delivery_label")
    delivery_address_line = terms.get("delivery_address_line")
    chosen_mandal_id = body.to_mandal_id
    if body.address_id is not None:
        from app.models.account import SavedAddress
        addr = db.get(SavedAddress, body.address_id)
        if addr is None or addr.user_id != order.buyer_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Saved address not found")
        chosen_mandal_id = addr.mandal_id
        delivery_label = addr.label
        delivery_address_line = addr.address_line

    # Resolve the billable distance server-side: origin = the produce's mandal,
    # destination = the buyer's delivery mandal (defaults to the order mandal).
    to_mandal_id = chosen_mandal_id or terms.get("destination_mandal_id") or mandal_id
    route = distance.route_km_between(
        db, mandal_id, to_mandal_id, override=body.route_km,
    )

    # Persist the resolved delivery destination onto the order so the courier and
    # the tracking timeline route to the right door (JSON column: reassign to flag
    # the change for SQLAlchemy).
    order.accepted_terms = {
        **terms,
        "destination_mandal_id": to_mandal_id,
        "delivery_label": delivery_label,
        "delivery_address_line": delivery_address_line,
    }

    quote = compute(rule, QuoteInput(
        product_value=product_value, billable_kg=D(terms["quantity"]), route_km=route.route_km,
        commission_discount_pct=D(0),
    ))
    qjson = quote.to_json()
    qjson["route_km_source"] = route.source
    order.quote = qjson
    order.pricing_rule_version = rule.version
    order.buyer_total = money(quote.buyer_total)
    order.seller_payable = money(quote.seller_payable)
    _safe_transition(db, order, S.PAYMENT_PENDING, actor_id=user.id, reason_code="quote_locked")
    db.commit()
    return _order_json(order, db, user)


# --- Payment capture (shared by mock /pay and the provider webhook) -------

def capture_order_payment(db: Session, order: Order, *, idempotency_key: str,
                          provider: str = "mock", provider_ref: str | None = None,
                          actor_id: int | None = None) -> bool:
    """Idempotently capture an order's payment and post the full ledger.

    Returns True if a capture was performed, False on idempotent replay. Does NOT
    commit — the caller commits. The same path backs the mock /pay endpoint and a
    real/sandbox provider webhook, so swapping the provider is isolated.
    """
    existing = db.scalar(select(Payment).where(Payment.idempotency_key == idempotency_key))
    if existing:
        return False
    if order.status != S.PAYMENT_PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Order not awaiting payment")
    if order.quote is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No locked quote to pay")

    q = order.quote
    buyer_total = money(order.buyer_total)
    txn = f"pay:{order.public_id}"
    platform_rev = money(q["service_fee"]) + money(q.get("seller_commission", "0"))
    legs = [
        Leg("cash_clearing", LedgerDirection.DEBIT, buyer_total, "buyer payment captured"),
        Leg("seller_payable", LedgerDirection.CREDIT, money(order.seller_payable), "seller proceeds"),
        Leg("platform_revenue", LedgerDirection.CREDIT, platform_rev, "service fee + commission"),
        Leg("transport_payable", LedgerDirection.CREDIT, money(q["transport_charge"]), "transport"),
        Leg("agent_fee_payable", LedgerDirection.CREDIT, money(q["inspection_fee"]), "inspection"),
        Leg("packing_revenue", LedgerDirection.CREDIT, money(q["packing_fee"]), "packing"),
        Leg("tax_payable", LedgerDirection.CREDIT, money(q["tax"]), "tax"),
    ]
    legs = [l for l in legs if money(l.amount) != money(0)]
    ledger.post(db, txn_group=txn, legs=legs, order_id=order.id, currency=q["currency"])
    db.add(Payment(
        order_id=order.id, provider=provider, provider_ref=provider_ref or txn,
        idempotency_key=idempotency_key, amount=buyer_total, currency=q["currency"], status="paid",
    ))
    _safe_transition(db, order, S.PAID, actor_id=actor_id, reason_code="payment_captured")
    audit.record(db, actor_id=actor_id, action="order.pay", object_type="order",
                 object_id=order.public_id, new_values={"amount": str(buyer_total), "provider": provider})
    return True


@router.post("/{order_id}/pay")
def pay(
    order_id: int,
    idempotency_key: str | None = Header(default=None),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mock payment capture (in-app). Posts the full double-entry ledger."""
    order = _get_order(order_id, db)
    _require_party(order, user, buyer=True)
    idem = idempotency_key or gen_idem()
    capture_order_payment(db, order, idempotency_key=idem, provider="mock", actor_id=user.id)
    db.commit()
    return _order_json(order, db, user)


# --- Packing -> lot + package --------------------------------------------

class PackingComplete(BaseModel):
    packing_video: str | None = None  # object key of the ≤2-min packing clip


@router.post("/{order_id}/packing-complete")
def packing_complete(
    order_id: int,
    body: PackingComplete | None = None,
    user=Depends(require_roles(Role.FIELD_AGENT, Role.FIELD_LEADER, Role.SUPERADMIN)),
    db: Session = Depends(get_db),
):
    order = _get_order(order_id, db)
    if order.status != S.PAID:
        raise HTTPException(status.HTTP_409_CONFLICT, "Order not paid")
    if body and body.packing_video:
        order.packing_video = body.packing_video
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
    return {"order": _order_json(order, db, user), "lot_id": lot.public_id, "qr": pkg.qr_code}


# --- Courier assignment + tracking ---------------------------------------

class AssignCourier(BaseModel):
    courier_id: int
    vehicle_class: str | None = None


@router.post("/{order_id}/assign-courier")
def assign_courier(
    order_id: int,
    body: AssignCourier,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Assign a tied-up transport courier to the order's shipment.

    Logistics are buyer-paid, so the buyer may choose the courier for their own
    order; staff and transport operators can also assign.
    """
    from app.models.carrier import Carrier

    order = _get_order(order_id, db)
    staff = user.role in (Role.FIELD_LEADER, Role.SUPERADMIN, Role.TRANSPORT)
    if not staff and user.id != order.buyer_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the buyer or staff can assign a courier")
    carrier = db.get(Carrier, body.courier_id)
    if not carrier or not carrier.active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Carrier not available")
    if carrier.kyc_status != "verified":
        raise HTTPException(status.HTTP_409_CONFLICT, "Carrier KYC not verified")

    shipment = db.scalar(select(Shipment).where(Shipment.order_id == order.id))
    if shipment is None:
        shipment = Shipment(public_id=gen_shipment(), order_id=order.id, status="assigned")
        db.add(shipment)
        db.flush()
    shipment.courier_id = carrier.id
    shipment.courier_name = carrier.name
    if body.vehicle_class:
        shipment.vehicle_class = body.vehicle_class
    audit.record(db, actor_id=user.id, action="shipment.assign_courier", object_type="order",
                 object_id=order.public_id, new_values={"courier": carrier.code})
    db.commit()
    return {"order": _order_json(order, db, user), "shipment_id": shipment.public_id,
            "courier": carrier.name}


# The buyer-facing delivery journey (shipment-centric milestones).
_TRACK_STEPS = [
    ("packed", "Packed & sealed"),
    ("picked_up", "Picked up"),
    ("in_transit", "In transit"),
    ("out_for_delivery", "Out for delivery"),
    ("delivered", "Delivered"),
]


def _estimate_eta(order: Order, picked_at, packed_at):
    """Rough ETA from the quote's route distance. Returns (iso, basis) or (None, None)."""
    q = order.quote or {}
    raw = (q.get("breakdown") or {}).get("route_km", q.get("route_km"))
    try:
        dist = float(raw) if raw is not None else None
    except (TypeError, ValueError):
        dist = None
    if dist is None:
        return None, None
    from datetime import timedelta
    # ~40 km/h effective on rural routes + a 1h handling buffer, min 2h.
    hours = max(2.0, dist / 40.0 + 1.0)
    base = picked_at or packed_at
    if base is None:
        return None, "pending_pickup"
    return (base + timedelta(hours=hours)).isoformat(), "estimated"


@router.get("/{order_id}/tracking")
def tracking(order_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Live delivery timeline (milestones, ETA, courier, delivery code) for the
    buyer, seller and staff."""
    from app.models.location import Mandal

    order = _get_order(order_id, db)
    _require_party(order, user)
    shipment = db.scalar(select(Shipment).where(Shipment.order_id == order.id))

    ship_at: dict[str, object] = {}
    events = []
    if shipment is not None:
        for e in db.scalars(
            select(ShipmentEvent).where(ShipmentEvent.shipment_id == shipment.id).order_by(ShipmentEvent.at)
        ):
            ship_at.setdefault(e.event, e.at)
            events.append({"event": e.event, "at": e.at.isoformat(), "evidence_ref": e.evidence_ref})

    # "packed" / terminal times come from the order's own status log.
    order_at: dict[str, object] = {}
    for ev in order.status_events:
        order_at[ev.to_status] = ev.at
    packed_at = order_at.get(S.READY_FOR_PICKUP)
    delivered_at = ship_at.get("delivered") or order_at.get(S.DELIVERED_PENDING_ACCEPTANCE)

    at_for = {
        "packed": packed_at,
        "picked_up": ship_at.get("picked_up"),
        "in_transit": ship_at.get("in_transit"),
        "out_for_delivery": ship_at.get("out_for_delivery"),
        "delivered": delivered_at,
    }
    steps = []
    current_set = False
    accepted = order.status in (S.COMPLETED, S.SETTLED)
    for key, label in _TRACK_STEPS:
        when = at_for.get(key)
        done = when is not None
        step = {"key": key, "label": label, "done": done,
                "at": when.isoformat() if done else None, "current": False}
        if not done and not current_set and not accepted:
            step["current"] = True
            current_set = True
        steps.append(step)

    eta, eta_basis = _estimate_eta(order, ship_at.get("picked_up"), packed_at)
    if delivered_at is not None:
        eta, eta_basis = delivered_at.isoformat(), "delivered"

    # Pickup + delivery places (from the accepted-terms snapshot) and a maps
    # navigation link for the courier — door-to-door routing.
    terms = order.accepted_terms or {}

    def _place(mandal_id):
        m = db.get(Mandal, mandal_id) if mandal_id else None
        if not m:
            return None, None
        coord = None
        if m.latitude is not None and m.longitude is not None:
            coord = {"lat": float(m.latitude), "lng": float(m.longitude)}
        return m.name, coord

    from_place, from_coord = _place(terms.get("mandal_id"))
    to_place, to_coord = _place(terms.get("destination_mandal_id") or terms.get("mandal_id"))
    nav_url = None
    if from_coord and to_coord:
        nav_url = ("https://www.google.com/maps/dir/?api=1"
                   f"&origin={from_coord['lat']},{from_coord['lng']}"
                   f"&destination={to_coord['lat']},{to_coord['lng']}&travelmode=driving")

    out = {
        "order_public_id": order.public_id,
        "order_status": order.status,
        "shipment": None if shipment is None else {
            "public_id": shipment.public_id,
            "status": shipment.status,
            "courier_name": shipment.courier_name,
            "vehicle_class": shipment.vehicle_class,
        },
        "steps": steps,
        "events": events,
        "from_place": from_place,
        "to_place": to_place,
        "to_label": terms.get("delivery_label"),
        "to_address_line": terms.get("delivery_address_line"),
        "from_coord": from_coord,
        "to_coord": to_coord,
        "nav_url": nav_url,
        "eta": eta,
        "eta_basis": eta_basis,
    }
    # Courier live position (if the courier app has been sharing it) + straight-line
    # distance to the destination, for the buyer's live map.
    if shipment is not None and shipment.last_lat is not None and shipment.last_lng is not None \
            and delivered_at is None:
        clat, clng = float(shipment.last_lat), float(shipment.last_lng)
        loc = {"lat": clat, "lng": clng,
               "at": shipment.last_location_at.isoformat() if shipment.last_location_at else None}
        if to_coord:
            from app.core.config import settings
            from app.services.distance import haversine_km
            d = round(haversine_km(clat, clng, to_coord["lat"], to_coord["lng"]), 1)
            loc["distance_km"] = d
            # Live ETA from distance-to-door at the assumed last-mile speed.
            spd = settings.courier_speed_kmph or 25.0
            loc["eta_minutes"] = max(1, round(d / spd * 60)) if d > 0 else 0
        out["courier_location"] = loc

    # Delivery code: the buyer shows it to the courier at handoff. Only the
    # buyer/staff ever see it, and only once the courier is out for delivery.
    pod = (shipment.proof_of_delivery or {}) if shipment else {}
    staff = user.role in (Role.SUPERADMIN, Role.FIELD_MANAGER, Role.FIELD_LEADER, Role.TRANSPORT)
    if pod.get("otp") and (staff or user.id == order.buyer_id) and not pod.get("otp_ok"):
        out["delivery_code"] = pod["otp"]
    if delivered_at is not None:
        out["proof"] = {
            "otp_ok": bool(pod.get("otp_ok")),
            "has_photo": bool(pod.get("photo_ref")),
            "has_signature": bool(pod.get("signature_ref")),
            "recipient_note": pod.get("recipient_note"),
        }
    return out
# --- Shipment milestones --------------------------------------------------

_SHIP_FLOW = {
    "picked_up": S.PICKED_UP,
    "in_transit": S.IN_TRANSIT,
    "out_for_delivery": S.OUT_FOR_DELIVERY,
    "delivered": S.DELIVERED_PENDING_ACCEPTANCE,
    "failed_delivery": S.DISPUTED,
}


class ShipEvent(BaseModel):
    event: str
    evidence_ref: str | None = None


@router.post("/{order_id}/shipment/event")
def shipment_event(
    order_id: int,
    body: ShipEvent,
    user=Depends(require_roles(Role.TRANSPORT, Role.FIELD_LEADER, Role.SUPERADMIN)),
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
    # The transport partner who works the milestones is the delivery-payout payee.
    if shipment.carrier_id is None and user.role == Role.TRANSPORT:
        shipment.carrier_id = user.id
    shipment.status = body.event
    if body.event == "out_for_delivery":
        import secrets as _secrets
        otp = f"{_secrets.randbelow(1_000_000):06d}"
        shipment.proof_of_delivery = {**(shipment.proof_of_delivery or {}), "otp": otp, "otp_issued": True}
    db.add(ShipmentEvent(shipment_id=shipment.id, event=body.event, actor_id=user.id,
                         evidence_ref=body.evidence_ref, at=utcnow()))
    _safe_transition(db, order, to, actor_id=user.id, reason_code=f"ship_{body.event}")
    db.commit()
    return {"order": _order_json(order, db, user), "shipment_id": shipment.public_id}


class ProofBody(BaseModel):
    otp: str | None = None
    signature_ref: str | None = None
    photo_ref: str | None = None
    recipient_note: str | None = None


@router.post("/{order_id}/shipment/proof-of-delivery")
def proof_of_delivery(
    order_id: int,
    body: ProofBody,
    user=Depends(require_roles(Role.TRANSPORT, Role.FIELD_LEADER, Role.SUPERADMIN, Role.FIELD_AGENT)),
    db: Session = Depends(get_db),
):
    order = _get_order(order_id, db)
    shipment = db.scalar(select(Shipment).where(Shipment.order_id == order.id))
    if not shipment:
        raise HTTPException(status.HTTP_409_CONFLICT, "No shipment yet")
    expected = (shipment.proof_of_delivery or {}).get("otp")
    if expected and body.otp and body.otp != expected:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid delivery OTP")
    shipment.proof_of_delivery = {
        **(shipment.proof_of_delivery or {}),
        "otp_ok": bool(expected and body.otp == expected),
        "signature_ref": body.signature_ref,
        "photo_ref": body.photo_ref,
        "recipient_note": body.recipient_note,
        "captured_by": user.id,
    }
    if order.status == S.OUT_FOR_DELIVERY:
        _safe_transition(db, order, S.DELIVERED_PENDING_ACCEPTANCE, actor_id=user.id, reason_code="pod")
    db.commit()
    return {"order": _order_json(order, db, user), "proof": shipment.proof_of_delivery}


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

    # Settle the seller: reclassify the seller_payable liability to a clearing
    # account and accrue a PENDING payout. Actual disbursement happens later when
    # finance runs a scheduled payout batch (/admin/payouts/run), which moves
    # seller_clearing -> cash_clearing and marks the payout processed.
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
                    Leg("seller_payable", LedgerDirection.DEBIT, payable, "accrue seller payout"),
                    Leg("seller_clearing", LedgerDirection.CREDIT, payable, "payout awaiting disbursement"),
                ],
            )
            db.add(Payout(order_id=order.id, seller_id=order.seller_id, amount=payable,
                          status="pending", idempotency_key=idem))

    # Accrue the transport partner's payout the same way: reclassify the
    # transport_payable liability to a clearing account and record a pending
    # payout for the courier user who handled the shipment.
    q = order.quote or {}
    charge = money(q.get("transport_charge", 0))
    shipment = db.scalar(select(Shipment).where(Shipment.order_id == order.id))
    transport_user = shipment.carrier_id if shipment else None
    if charge > money(0) and transport_user:
        tidem = f"tpayout:{order.public_id}"
        if not db.scalar(select(Payout).where(Payout.idempotency_key == tidem)):
            ledger.post(
                db,
                txn_group=f"settle-transport:{order.public_id}",
                order_id=order.id,
                currency=q.get("currency", "INR"),
                legs=[
                    Leg("transport_payable", LedgerDirection.DEBIT, charge, "accrue transport payout"),
                    Leg("transport_clearing", LedgerDirection.CREDIT, charge, "transport payout awaiting disbursement"),
                ],
            )
            db.add(Payout(order_id=order.id, seller_id=transport_user, payee_type="transport",
                          amount=charge, status="pending", idempotency_key=tidem))
    _safe_transition(db, order, S.SETTLED, actor_id=user.id, reason_code="settled")
    audit.record(db, actor_id=user.id, action="order.settle", object_type="order",
                 object_id=order.public_id, new_values={"seller_payout": str(payable)})
    db.commit()
    return _order_json(order, db, user)


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
    return _order_json(order, db, user)
