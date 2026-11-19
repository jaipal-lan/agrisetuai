"""Payment provider abstraction.

"mock"    — payment is captured in-app via POST /orders/{id}/pay (dev/demo only).
"sandbox" — the client creates a payment intent, then the provider calls our
            signed webhook (POST /payments/webhook) to confirm. Same shape as a
            real marketplace provider; no live API call.
"razorpay"— create_intent() creates a REAL Razorpay Order (razorpay_key_id /
            razorpay_key_secret) and returns key_id + order_id for Razorpay
            Checkout; confirmation arrives on the same webhook (Razorpay signs
            X-Razorpay-Signature = HMAC-SHA256 hex of the raw body with the
            webhook secret — exactly what verify_webhook() already checks).
"""
import hashlib
import hmac
import json
import logging

import httpx

from app.core.config import settings

log = logging.getLogger("agrisetu.payments")


def _razorpay_order(order) -> dict | None:
    """Create a live Razorpay Order; None on any failure (caller falls back)."""
    if not (settings.razorpay_key_id and settings.razorpay_key_secret):
        return None
    amount_paise = int(round(float(order.buyer_total) * 100))
    try:
        r = httpx.post(
            "https://api.razorpay.com/v1/orders",
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
            json={"amount": amount_paise, "currency": (order.quote or {}).get("currency", "INR"),
                  "receipt": order.public_id, "notes": {"order_public_id": order.public_id}},
            timeout=20,
        )
        if r.status_code in (200, 201):
            return r.json()
        log.warning("razorpay order create failed: %s %s", r.status_code, r.text[:200])
    except Exception:  # noqa: BLE001 — never break checkout; fall back to a plain intent
        log.exception("razorpay order create error")
    return None


def create_intent(order) -> dict:
    """A payment intent the client hands to the provider's checkout."""
    ref = f"intent_{order.public_id}"
    base = {
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
    if settings.payment_provider == "razorpay":
        rp = _razorpay_order(order)
        if rp:
            base.update({
                "provider_order_id": rp.get("id"),      # order_xxx for Checkout
                "key_id": settings.razorpay_key_id,     # publishable; safe for client
                "amount_minor": rp.get("amount"),       # paise
                "reference": rp.get("id") or ref,
            })
    return base


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
