"""Inventory allocation helpers.

A single place for returning reserved stock to a listing's availability, so
cancellation, a full refund and a failed inspection all release stock the same
way (and we never leak reserved quantity that can no longer be sold).
"""
from decimal import Decimal as D

from sqlalchemy.orm import Session

from app.models.marketplace import Listing


def release_reserved(db: Session, order) -> int:
    """Return any still-reserved/packed line quantities to listing availability.

    Only lines that have NOT yet been handed over (allocation_status in
    reserved/packed) are released; delivered/sold stock is left alone. Safe to
    call more than once — an already-released line is skipped. Returns the number
    of lines released.
    """
    released = 0
    for line in order.lines:
        if line.listing_id and line.allocation_status in ("reserved", "packed"):
            listing = db.get(Listing, line.listing_id, with_for_update=True)
            if listing:
                listing.reserved_qty = max(D("0"), D(listing.reserved_qty) - D(line.quantity))
            line.allocation_status = "released"
            released += 1
    return released
