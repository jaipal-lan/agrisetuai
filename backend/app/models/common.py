from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_aware(dt: datetime | None) -> datetime | None:
    """Coerce a possibly-naive datetime (e.g. read back from SQLite) to UTC-aware."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utcnow,
        onupdate=utcnow,
    )


class ListingStatus(StrEnum):
    DRAFT = "draft"
    OPEN = "open"            # published and visible with available quantity
    PAUSED = "paused"
    SOLD_OUT = "sold_out"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"


class RFQStatus(StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    MATCHED = "matched"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class OfferStatus(StrEnum):
    OPEN = "open"            # awaiting a response from the other side
    COUNTERED = "countered"  # superseded by a newer version
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"


class ClaimStatus(StrEnum):
    CONVENTIONAL = "conventional"
    ORGANIC = "organic"
    IN_CONVERSION = "in_conversion"
    OTHER = "other"


class OrderStatus(StrEnum):
    PROVISIONAL_AGREEMENT = "provisional_agreement"
    INSPECTION_ASSIGNED = "inspection_assigned"
    INSPECTION_IN_PROGRESS = "inspection_in_progress"
    INSPECTION_PASS = "inspection_pass"
    INSPECTION_HOLD = "inspection_hold"
    INSPECTION_FAIL = "inspection_fail"
    BUYER_APPROVAL_PENDING = "buyer_approval_pending"
    CONFIRMED = "confirmed"
    PAYMENT_PENDING = "payment_pending"
    PAID = "paid"
    PACKING = "packing"
    READY_FOR_PICKUP = "ready_for_pickup"
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED_PENDING_ACCEPTANCE = "delivered_pending_acceptance"
    COMPLETED = "completed"
    SETTLED = "settled"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class InspectionOutcome(StrEnum):
    PASS = "pass"
    PASS_WITH_ADJUSTMENT = "pass_with_adjustment"
    HOLD = "hold"
    FAIL = "fail"


class LedgerDirection(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"
