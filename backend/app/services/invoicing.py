"""Invoice numbering + records.

One continuous, gap-free series shared by every document type. A number looks
like ``KS/LAN/2026-27/200000000001`` — brand/operator prefix, Indian financial
year, then a 12-digit sequence that starts in the billions. Numbers are assigned
only when a document is finalised (never reused), under a row lock so concurrent
payments cannot collide.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.finance import Invoice, InvoiceCounter

_COUNTER_KEY = "ALL"


def fy_label(dt: datetime | None = None) -> str:
    """Indian financial year label (Apr–Mar) for a datetime, e.g. '2026-27'."""
    d = dt or datetime.now(timezone.utc)
    y = d.year
    if d.month >= 4:
        return f"{y}-{str(y + 1)[-2:]}"
    return f"{y - 1}-{str(y)[-2:]}"


def _next_seq(db: Session) -> int:
    """Allocate the next sequence value atomically, gap-free."""
    ctr = db.get(InvoiceCounter, _COUNTER_KEY, with_for_update=True)
    if ctr is None:
        ctr = InvoiceCounter(key=_COUNTER_KEY, last_seq=int(settings.invoice_seq_start) - 1)
        db.add(ctr)
        db.flush()
        # Re-read under lock now that the row exists (no-op lock on SQLite).
        ctr = db.get(InvoiceCounter, _COUNTER_KEY, with_for_update=True)
    ctr.last_seq = int(ctr.last_seq) + 1
    db.flush()
    return int(ctr.last_seq)


def format_number(seq: int, fy: str) -> str:
    return f"{settings.invoice_number_prefix}/{fy}/{seq}"


def get_or_create_order_invoice(db: Session, order) -> Invoice:
    """Return the order's invoice, creating (and numbering) it on first call.

    Idempotent: one invoice per order (``order_id`` is unique). Does not commit —
    the caller owns the transaction.
    """
    inv = db.scalar(select(Invoice).where(Invoice.order_id == order.id))
    if inv is not None:
        return inv
    fy = fy_label()
    seq = _next_seq(db)
    inv = Invoice(
        number=format_number(seq, fy),
        seq=seq,
        fy=fy,
        kind="order",
        order_id=order.id,
        buyer_id=order.buyer_id,
        amount=order.buyer_total,
    )
    db.add(inv)
    db.flush()
    return inv
