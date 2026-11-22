"""WhatsApp notifications via Gupshup (BSP), gated on configuration.

A thin, dependency-free client over Gupshup's HTTP API. It is deliberately
best-effort: if WhatsApp is not configured, or a send fails, it quietly returns
False — a messaging side effect must never break an order transition or a
payout. Business-initiated messages outside the 24h customer session window
require Gupshup-approved templates; this sends a plain text message, which works
for session messages and the Gupshup sandbox. See WHATSAPP_SETUP.md.
"""
import json
import logging

import httpx

from app.core.config import settings

log = logging.getLogger("agrisetu.whatsapp")

GUPSHUP_URL = "https://api.gupshup.io/wa/api/v1/msg"


def enabled() -> bool:
    """True only when WhatsApp is switched on AND the Gupshup credentials exist."""
    return bool(settings.whatsapp_enabled and settings.gupshup_api_key and settings.gupshup_source)


def send_text(phone: str, body: str) -> bool:
    """Send a WhatsApp text to `phone` (E.164 digits, e.g. 919000000003).

    Returns True on apparent success, False if disabled/misconfigured or on any
    error. Never raises.
    """
    if not enabled() or not phone:
        return False
    try:
        destination = phone.lstrip("+")
        data = {
            "channel": "whatsapp",
            "source": settings.gupshup_source,
            "destination": destination,
            "message": json.dumps({"type": "text", "text": body}),
            "src.name": settings.gupshup_src_name or "",
        }
        headers = {
            "apikey": settings.gupshup_api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        r = httpx.post(GUPSHUP_URL, data=data, headers=headers, timeout=6.0)
        if r.status_code >= 300:
            log.warning("gupshup send failed: %s %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception:
        log.exception("whatsapp send errored")
        return False


def send_document(phone: str, doc_url: str, filename: str, caption: str = "") -> bool:
    """Send a WhatsApp document (e.g. an invoice PDF) by public URL.

    Provider-agnostic in spirit, Gupshup under the hood. Gated and best-effort:
    returns False if disabled/misconfigured or on any error, and never raises, so
    invoice delivery can never break a payment. `doc_url` must be publicly
    reachable (a signed, short-lived invoice link). Business-initiated sends
    outside the 24h session window need a Gupshup-approved template.
    """
    if not enabled() or not phone or not doc_url:
        return False
    try:
        destination = phone.lstrip("+")
        message = {"type": "file", "url": doc_url, "filename": filename}
        if caption:
            message["caption"] = caption
        data = {
            "channel": "whatsapp",
            "source": settings.gupshup_source,
            "destination": destination,
            "message": json.dumps(message),
            "src.name": settings.gupshup_src_name or "",
        }
        headers = {
            "apikey": settings.gupshup_api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        r = httpx.post(GUPSHUP_URL, data=data, headers=headers, timeout=6.0)
        if r.status_code >= 300:
            log.warning("gupshup doc send failed: %s %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception:
        log.exception("whatsapp document send errored")
        return False
