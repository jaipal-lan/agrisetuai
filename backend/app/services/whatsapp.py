"""WhatsApp notifications — gated, with a dummy "mock" provider for demo/dev.

Two providers (settings.whatsapp_provider):
  * "mock"    — records each message to an in-memory outbox (viewable in Admin)
                and returns True, with no network call. Lets the whole WhatsApp
                flow run end to end before a real BSP is connected.
  * "gupshup" — real Gupshup BSP over HTTP; also needs whatsapp_enabled + keys.

Both are best-effort: a messaging side effect must never break an order
transition or a payout, so failures return False and nothing raises. Business-
initiated messages outside the 24h session window need Gupshup-approved
templates; see WHATSAPP_SETUP.md.
"""
import json
import logging
import time

import httpx

from app.core.config import settings

log = logging.getLogger("agrisetu.whatsapp")

GUPSHUP_URL = "https://api.gupshup.io/wa/api/v1/msg"

# In-memory dummy outbox (most-recent last), capped. Per-process only — a demo
# aid, not durable storage.
_OUTBOX: list[dict] = []
_OUTBOX_MAX = 100


def _record(kind: str, phone: str, body: str, meta: dict | None = None) -> None:
    _OUTBOX.append({
        "kind": kind, "phone": phone, "body": body,
        "meta": meta or {}, "at": time.time(),
    })
    if len(_OUTBOX) > _OUTBOX_MAX:
        del _OUTBOX[:-_OUTBOX_MAX]


def outbox() -> list[dict]:
    """Recent mock messages, most recent first."""
    return list(reversed(_OUTBOX))


def outbox_clear() -> None:
    _OUTBOX.clear()


def _mock() -> bool:
    return settings.whatsapp_provider == "mock"


def enabled() -> bool:
    """True when a message would actually be delivered (or recorded, in mock)."""
    if _mock():
        return True
    return bool(settings.whatsapp_enabled and settings.gupshup_api_key and settings.gupshup_source)


def send_text(phone: str, body: str) -> bool:
    """Send a WhatsApp text to `phone` (E.164 digits, e.g. 919000000003)."""
    if not enabled() or not phone:
        return False
    if _mock():
        _record("text", phone, body)
        log.info("whatsapp(mock) text -> %s: %s", phone, body[:80])
        return True
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

    `doc_url` must be publicly reachable (a signed, short-lived invoice link).
    Gated and best-effort; never raises.
    """
    if not enabled() or not phone or not doc_url:
        return False
    if _mock():
        _record("document", phone, caption or filename,
                {"filename": filename, "url": doc_url})
        log.info("whatsapp(mock) document -> %s: %s", phone, filename)
        return True
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
