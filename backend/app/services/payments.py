"""Payment provider abstraction.

"mock"    — payment is captured in-app via POST /orders/{id}/pay.
"sandbox" — the client creates a payment intent, then the provider calls our
            signed webhook (POST /payments/webhook) to confirm. Same shape as a
            real marketplace provider (Razorpay/Cashfree/Stripe); real keys and
            the real signing scheme plug in behind these two functions.
"""
import hashlib
import hmac
import json

from app.core.config import settings


def create_intent(order) -> dict:
    """A payment intent the client would hand to the provider's checkout."""
    ref = f"intent_{order.public_id}"
    return {
        "provider": settings.payment_provider,
        "reference": ref,
        "order_public_id": order.public_id,
        "amount": str(order.buyer_total),
        "currency": (order.quote or {}).get("currency", "INR"),
        "status": "requires_payment",
        # In sandbox, the client can POST a signed event to /payments/webhook to
        # simulate the provider confirming payment.
        "sandbox": settings.payment_provider == "sandbox",
    }


def sign(payload: bytes) -> str:
    """HMAC-SHA256 signature over the raw webhook body (hex)."""
    return hmac.new(
        settings.payment_webhook_secret.encode(), payload, hashlib.sha256
    ).hexdigest()


def verify_webhook(payload: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    return hmac.compare_digest(sign(payload), signature)


def make_event(order, event_type: str = "payment.succeeded") -> tuple[bytes, str]:
    """Build a signed sandbox webhook body (used by tests and the sandbox UI)."""
    body = json.dumps({
        "type": event_type,
        "data": {
            "order_public_id": order.public_id,
            "reference": f"intent_{order.public_id}",
            "amount": str(order.buyer_total),
        },
    }).encode()
    return body, sign(body)
