"""Order state machine (PRD section 5).

Transitions are explicit and validated. Every transition appends an
OrderStatusEvent so the order history is auditable and the current status is
never silently changed.
"""
from sqlalchemy.orm import Session

from app.models.common import OrderStatus as S
from app.models.common import utcnow
from app.models.order import Order, OrderStatusEvent

# Allowed transitions. Terminal states map to an empty set.
TRANSITIONS: dict[S, set[S]] = {
    S.PROVISIONAL_AGREEMENT: {S.INSPECTION_ASSIGNED, S.CANCELLED},
    S.INSPECTION_ASSIGNED: {S.INSPECTION_IN_PROGRESS, S.CANCELLED},
    S.INSPECTION_IN_PROGRESS: {
        S.INSPECTION_PASS,
        S.INSPECTION_HOLD,
        S.INSPECTION_FAIL,
    },
    S.INSPECTION_PASS: {S.BUYER_APPROVAL_PENDING, S.CANCELLED},
    S.INSPECTION_HOLD: {
        S.INSPECTION_IN_PROGRESS,  # re-inspection
        S.BUYER_APPROVAL_PENDING,
        S.CANCELLED,
    },
    S.INSPECTION_FAIL: {S.CANCELLED, S.DISPUTED},
    S.BUYER_APPROVAL_PENDING: {S.CONFIRMED, S.CANCELLED},
    S.CONFIRMED: {S.PAYMENT_PENDING, S.CANCELLED},
    S.PAYMENT_PENDING: {S.PAID, S.CANCELLED},
    S.PAID: {S.PACKING, S.REFUNDED, S.DISPUTED},
    S.PACKING: {S.READY_FOR_PICKUP, S.DISPUTED},
    S.READY_FOR_PICKUP: {S.PICKED_UP, S.DISPUTED},
    S.PICKED_UP: {S.IN_TRANSIT, S.DISPUTED},
    S.IN_TRANSIT: {S.OUT_FOR_DELIVERY, S.DISPUTED},
    S.OUT_FOR_DELIVERY: {S.DELIVERED_PENDING_ACCEPTANCE, S.DISPUTED},
    S.DELIVERED_PENDING_ACCEPTANCE: {
        S.COMPLETED,
        S.DISPUTED,
        S.PARTIALLY_REFUNDED,
    },
    S.COMPLETED: {S.SETTLED, S.DISPUTED},
    S.SETTLED: set(),
    S.CANCELLED: set(),
    S.REFUNDED: set(),
    S.PARTIALLY_REFUNDED: {S.COMPLETED, S.SETTLED, S.DISPUTED},
    S.DISPUTED: {
        S.COMPLETED,
        S.CANCELLED,
        S.REFUNDED,
        S.PARTIALLY_REFUNDED,
        S.SETTLED,
    },
}


class InvalidTransition(Exception):
    def __init__(self, frm: str, to: str):
        super().__init__(f"Invalid order transition: {frm} -> {to}")
        self.frm = frm
        self.to = to


def can_transition(frm: S, to: S) -> bool:
    return to in TRANSITIONS.get(S(frm), set())


def transition(
    db: Session,
    order: Order,
    to: S,
    *,
    actor_id: int | None = None,
    reason_code: str | None = None,
    note: str | None = None,
) -> Order:
    frm = S(order.status)
    to = S(to)
    if not can_transition(frm, to):
        raise InvalidTransition(frm, to)
    order.status = to
    db.add(
        OrderStatusEvent(
            order_id=order.id,
            from_status=frm,
            to_status=to,
            actor_id=actor_id,
            reason_code=reason_code,
            note=note,
            at=utcnow(),
        )
    )
    return order
