"""Order state machine (PRD section 5).

Transitions are explicit and validated. Every transition appends an
OrderStatusEvent so the order history is auditable and the current status is
never silently changed.
"""
from sqlalchemy.orm import Session

from app.models.common import OrderStatus as S
from app.models.common import utcnow
from app.models.order import Order, OrderStatusEvent
from app.services import notify

# Who to alert when an order reaches a state, and the message.
# recipient: "buyer" | "seller" | "agent" | "both".
_ALERTS: dict[S, tuple[str, str, str]] = {
    S.INSPECTION_ASSIGNED: ("agent", "New inspection job", "You have been assigned an inspection."),
    S.BUYER_APPROVAL_PENDING: ("buyer", "Inspection done", "Review the verified lot and approve to proceed."),
    S.PAYMENT_PENDING: ("buyer", "Quote ready", "Your itemised quote is ready — complete payment."),
    S.PAID: ("seller", "Payment received", "The buyer has paid. Prepare the lot for packing."),
    S.READY_FOR_PICKUP: ("buyer", "Packed & ready", "Your order is packed and ready for pickup."),
    S.OUT_FOR_DELIVERY: ("buyer", "Out for delivery", "Your order is out for delivery."),
    S.DELIVERED_PENDING_ACCEPTANCE: ("buyer", "Delivered", "Please confirm delivery to complete the order."),
    S.SETTLED: ("seller", "You've been paid", "Settlement complete — your payout has been released."),
    S.CANCELLED: ("both", "Order cancelled", "This order was cancelled."),
    S.DISPUTED: ("both", "Dispute opened", "A dispute was opened on this order."),
    S.REFUNDED: ("buyer", "Refund issued", "A refund was processed for your order."),
    S.PARTIALLY_REFUNDED: ("buyer", "Partial refund issued", "A partial refund was processed for your order."),
}


def _alert(db: Session, order: Order, to: S) -> None:
    spec = _ALERTS.get(to)
    if not spec:
        return
    recipient, title, body = spec
    targets: list[int] = []
    if recipient in ("buyer", "both") and order.buyer_id:
        targets.append(order.buyer_id)
    if recipient in ("seller", "both") and order.seller_id:
        targets.append(order.seller_id)
    if recipient == "agent" and order.assigned_agent_id:
        targets.append(order.assigned_agent_id)
    for uid in targets:
        try:
            notify.send(db, user_id=uid, title=f"{title} · {order.public_id}",
                        body=body, object_type="order", object_id=order.public_id)
        except Exception:
            pass  # a notification must never break a transition

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
    S.PAID: {S.PACKING, S.REFUNDED, S.PARTIALLY_REFUNDED, S.DISPUTED},
    S.PACKING: {S.READY_FOR_PICKUP, S.DISPUTED, S.REFUNDED, S.PARTIALLY_REFUNDED},
    S.READY_FOR_PICKUP: {S.PICKED_UP, S.DISPUTED, S.REFUNDED, S.PARTIALLY_REFUNDED},
    S.PICKED_UP: {S.IN_TRANSIT, S.DISPUTED, S.REFUNDED, S.PARTIALLY_REFUNDED},
    S.IN_TRANSIT: {S.OUT_FOR_DELIVERY, S.DISPUTED, S.REFUNDED, S.PARTIALLY_REFUNDED},
    S.OUT_FOR_DELIVERY: {S.DELIVERED_PENDING_ACCEPTANCE, S.DISPUTED, S.REFUNDED, S.PARTIALLY_REFUNDED},
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
    _alert(db, order, to)
    return order
