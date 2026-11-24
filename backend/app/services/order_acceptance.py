"""Shared "buyer accepts delivery -> complete -> settle payouts" logic.

Used by both the buyer's explicit acceptance endpoint (POST /orders/{id}/acceptance)
and the scheduler's auto-accept job (when the inspect-at-unboxing window elapses with
no defect reported). Keeping it in one place means the money side of an acceptance is
identical whether a human taps "Accept" or the window simply runs out.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.money import D, money
from app.models.catalog import Commodity
from app.models.common import LedgerDirection
from app.models.common import OrderStatus as S
from app.models.finance import Payout
from app.models.marketplace import Listing
from app.models.order import Lot, Order, OrderStatusEvent, Shipment
from app.services import audit, ledger
from app.services.ledger import Leg
from app.services.state_machine import transition

# Perishability drives the inspect-at-unboxing window. A commodity is "perishable"
# (short window) if its handling class or category points to fresh/cold-chain goods;
# otherwise it's a dry staple (longer window). Matched case-insensitively.
_PERISHABLE_HANDLING = ("perishable", "cold_chain", "cold chain", "cold", "fresh",
                        "refrigerat", "frozen", "chilled", "dairy", "floric")
_PERISHABLE_CATEGORIES = {
    "vegetables", "vegetable", "fruits", "fruit", "leafy", "greens", "flowers",
    "flower", "dairy", "dairy_meat", "meat", "fish", "seafood", "poultry",
    "eggs", "egg", "milk", "perishable", "fresh", "herbs",
}


def _is_perishable(commodity: Commodity | None) -> bool:
    if commodity is None:
        return False
    hc = (getattr(commodity, "handling_class", None) or "").lower()
    cat = (getattr(commodity, "category", None) or "").lower()
    if any(k in hc for k in _PERISHABLE_HANDLING):
        return True
    return cat in _PERISHABLE_CATEGORIES


def window_hours_for_order(db: Session, order: Order) -> int:
    """The inspect-at-unboxing window (hours) that applies to this order: the SHORTEST
    across its line items, so a mixed box is governed by its most perishable item.
    Items whose commodity can't be resolved fall back to the (longer) staple window,
    so an unknown item never silently shortens the buyer's window."""
    from app.core.config import settings

    perishable_h = settings.defect_report_window_hours
    staple_h = settings.defect_report_window_hours_staple

    commodity_ids: set[int] = set()
    for line in order.lines:
        cid = None
        if line.listing_id:
            lst = db.get(Listing, line.listing_id)
            cid = lst.commodity_id if lst else None
        if cid is None and line.lot_id:
            lot = db.get(Lot, line.lot_id)
            cid = lot.commodity_id if lot else None
        if cid:
            commodity_ids.add(cid)

    if not commodity_ids:
        return staple_h
    hours = [perishable_h if _is_perishable(db.get(Commodity, cid)) else staple_h
             for cid in commodity_ids]
    return min(hours)


def delivered_at(db: Session, order: Order) -> datetime | None:
    """When the order entered DELIVERED_PENDING_ACCEPTANCE (latest such event), or
    None if it never has. Anchors the inspect-at-unboxing return window."""
    return db.scalar(
        select(func.max(OrderStatusEvent.at)).where(
            OrderStatusEvent.order_id == order.id,
            OrderStatusEvent.to_status == str(S.DELIVERED_PENDING_ACCEPTANCE),
        )
    )


def accept_and_settle(db: Session, order: Order, *, actor_id: int | None,
                      reason_code: str = "buyer_accepted") -> None:
    """Complete a delivered-pending-acceptance order and release the seller + transport
    payouts (accrued to clearing accounts; disbursed later by the payout batch). The
    caller is responsible for committing, and must ensure the order is currently in
    DELIVERED_PENDING_ACCEPTANCE."""
    transition(db, order, S.COMPLETED, actor_id=actor_id, reason_code=reason_code)

    # Release reserved -> sold on the listing(s).
    for line in order.lines:
        if line.listing_id:
            listing = db.get(Listing, line.listing_id, with_for_update=True)
            if listing:
                dq = D(line.quantity)
                listing.reserved_qty = max(D("0"), D(listing.reserved_qty) - dq)
                listing.sold_qty = D(listing.sold_qty) + dq
        line.allocation_status = "delivered"

    # Accrue the seller payout: reclassify the seller_payable liability to a clearing
    # account and record a PENDING payout (disbursed later by /admin/payouts/run).
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

    # Accrue the transport partner's payout the same way.
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

    transition(db, order, S.SETTLED, actor_id=actor_id, reason_code="settled")
    audit.record(db, actor_id=actor_id, action="order.settle", object_type="order",
                 object_id=order.public_id, new_values={"seller_payout": str(payable)})
