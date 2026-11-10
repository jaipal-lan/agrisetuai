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
    db: Session = Depends(get_db),
):
    """Provider → platform payment confirmation. Signature-verified; on
    payment.succeeded it captures the order via the shared ledger path.

    This is the real-provider integration point; the signing scheme and header
    name map to whatever provider is configured.
    """
    raw = await request.body()
    if not payments.verify_webhook(raw, x_webhook_signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed payload")

    if event.get("type") != "payment.succeeded":
        return {"ignored": event.get("type")}

    data = event.get("data", {})
    public_id = data.get("order_public_id")
    order = db.scalar(select(Order).where(Order.public_id == public_id))
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")

    # Idempotency keyed on the provider reference so replays are safe.
    from app.api.orders import capture_order_payment
    idem = data.get("reference") or f"wh:{public_id}"
    captured = capture_order_payment(db, order, idempotency_key=idem,
                                     provider="sandbox", provider_ref=idem)
    db.commit()
    return {"ok": True, "captured": captured, "order_status": order.status}
