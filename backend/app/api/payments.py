import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.rbac import Role
from app.models.order import Order
from app.services import payments

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("/intent/{order_id}")
def payment_intent(order_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Create a payment intent for the order (buyer or staff)."""
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    staff = user.role in (Role.SUPERADMIN, Role.FIELD_MANAGER, Role.FIELD_LEADER)
    if not staff and user.id != order.buyer_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    if order.buyer_total is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Lock the quote first")
    return payments.create_intent(order)


@router.post("/webhook")
async def payment_webhook(
    request: Request,
    x_webhook_signature: str | None = Header(default=None),
    x_razorpay_signature: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Provider → platform payment confirmation. Signature-verified; on
    payment.succeeded it captures the order via the shared ledger path.

    Accepts the sandbox header (X-Webhook-Signature) or Razorpay's
    (X-Razorpay-Signature); both are HMAC-SHA256 hex of the raw body with
    payment_webhook_secret, so the same verifier handles either.
    """
    raw = await request.body()
    signature = x_razorpay_signature or x_webhook_signature
    if not payments.verify_webhook(raw, signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed payload")

    # Normalise the event: our sandbox sends {type, data:{order_public_id,...}};
    # Razorpay sends {event:"payment.captured", payload:{payment:{entity:{notes,
    # order_id,...}}}}. Map both to (kind, order_public_id, reference).
    kind = event.get("type") or event.get("event")
    data = event.get("data", {})
    public_id = data.get("order_public_id")
    reference = data.get("reference")
    if public_id is None and "payload" in event:  # Razorpay shape
        entity = (((event.get("payload") or {}).get("payment") or {}).get("entity") or {})
        public_id = (entity.get("notes") or {}).get("order_public_id")
        reference = entity.get("order_id") or entity.get("id")
        if kind == "payment.captured":
            kind = "payment.succeeded"

    if kind != "payment.succeeded":
        return {"ignored": kind}

    order = db.scalar(select(Order).where(Order.public_id == public_id))
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")

    # Idempotency keyed on the provider reference so replays are safe.
    from app.api.orders import capture_order_payment
    idem = reference or f"wh:{public_id}"
    provider = "razorpay" if x_razorpay_signature else "sandbox"
    captured = capture_order_payment(db, order, idempotency_key=idem,
                                     provider=provider, provider_ref=idem)
    db.commit()
    return {"ok": True, "captured": captured, "order_status": order.status}
