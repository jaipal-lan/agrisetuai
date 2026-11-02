"""SMS delivery abstraction.

The pilot uses a "console" provider that logs the message. A real gateway
(Twilio / MSG91 / Gupshup) plugs in behind send() using settings.sms_* keys —
no caller changes needed.
"""
import logging

from app.core.config import settings

log = logging.getLogger("agrisetu.sms")


def send(phone: str, message: str) -> bool:
    provider = settings.sms_provider
    if provider == "console":
        log.info("[SMS to %s] %s", phone, message)
        print(f"[SMS to {phone}] {message}")
        return True
    # Real providers would be dispatched here using settings.sms_api_key etc.
    # e.g. if provider == "msg91": requests.post(...)
    log.warning("SMS provider %r not configured; message not sent", provider)
    return False


def send_otp(phone: str, code: str) -> bool:
    return send(phone, f"Your AgriSetuAI verification code is {code}. Valid for 5 minutes.")
