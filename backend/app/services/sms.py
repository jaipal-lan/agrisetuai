"""SMS delivery abstraction.

The pilot default is a "console" provider that logs the message. Real gateways
plug in behind send() with no caller changes — set SMS_PROVIDER and the keys:

  2factor   — India, RECOMMENDED; SMS_API_KEY = your 2Factor API key. Ships a
              pre-approved DLT OTP template, so OTP works with no DLT registration.
              Optional TWOFACTOR_TEMPLATE_NAME for a custom approved template.
  fast2sms  — India, cheap; SMS_API_KEY = your authorization key.
  msg91     — SMS_API_KEY = authkey, MSG91_TEMPLATE_ID, SMS_SENDER_ID.
  twilio    — TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, SMS_SENDER_ID = From number.

Sending never raises; a failure is logged and returns False (the OTP is still
stored server-side). Uses httpx (already a dependency).
"""
import logging

import httpx

from app.core.config import settings

log = logging.getLogger("agrisetu.sms")

_TIMEOUT = 10.0


def _digits(phone: str) -> str:
    return "".join(c for c in phone if c.isdigit())


def _fast2sms(phone: str, message: str) -> bool:
    # Transactional/quick route; strips country code to the 10-digit number.
    num = _digits(phone)[-10:]
    r = httpx.get(
        "https://www.fast2sms.com/dev/bulkV2",
        params={"authorization": settings.sms_api_key, "route": "q",
                "message": message, "numbers": num, "flash": "0"},
        timeout=_TIMEOUT,
    )
    ok = r.status_code == 200 and r.json().get("return") is True
    if not ok:
        log.warning("fast2sms send failed: %s %s", r.status_code, r.text[:200])
    return ok


def _fast2sms_otp(phone: str, code: str) -> bool:
    # Fast2SMS dedicated OTP route: DLT-exempt, no template approval needed.
    # Sends a standard "<code> is your verification code" message.
    num = _digits(phone)[-10:]
    r = httpx.get(
        "https://www.fast2sms.com/dev/bulkV2",
        params={"authorization": settings.sms_api_key, "route": "otp",
                "variables_values": code, "numbers": num},
        timeout=_TIMEOUT,
    )
    ok = r.status_code == 200 and r.json().get("return") is True
    if not ok:
        log.warning("fast2sms OTP send failed: %s %s", r.status_code, r.text[:200])
    return ok


def _2factor_otp(phone: str, code: str) -> bool:
    """2Factor.in transactional OTP: delivers OUR server-generated code via
    2Factor's pre-approved DLT OTP template (no DLT registration on our side).

    GET https://2factor.in/API/V1/{key}/SMS/{phone}/{otp}[/{template_name}]
    -> {"Status":"Success","Details":"<session_id>"} on success.
    """
    num = _digits(phone)[-10:]
    url = f"https://2factor.in/API/V1/{settings.sms_api_key}/SMS/{num}/{code}"
    if settings.twofactor_template_name:
        url += f"/{settings.twofactor_template_name}"
    r = httpx.get(url, timeout=_TIMEOUT)
    ok = False
    try:
        ok = r.status_code == 200 and r.json().get("Status") == "Success"
    except Exception:  # noqa: BLE001 - non-JSON / network body
        ok = False
    if not ok:
        log.warning("2factor OTP send failed: %s %s", r.status_code, r.text[:200])
    return ok


def _2factor(phone: str, message: str) -> bool:
    """Generic transactional SMS via 2Factor (needs an approved DLT template name
    in TWOFACTOR_TEMPLATE_NAME). OTP delivery uses _2factor_otp instead; this path
    exists only if non-OTP SMS is ever wired."""
    if not settings.twofactor_template_name:
        log.warning("2factor generic SMS needs TWOFACTOR_TEMPLATE_NAME; not sent")
        return False
    num = _digits(phone)[-10:]
    r = httpx.get(
        f"https://2factor.in/API/V1/{settings.sms_api_key}/ADDON_SERVICES/SEND/TSMS",
        params={"From": settings.sms_sender_id, "To": num,
                "TemplateName": settings.twofactor_template_name, "VAR1": message},
        timeout=_TIMEOUT,
    )
    ok = False
    try:
        ok = r.status_code == 200 and r.json().get("Status") == "Success"
    except Exception:  # noqa: BLE001
        ok = False
    if not ok:
        log.warning("2factor SMS send failed: %s %s", r.status_code, r.text[:200])
    return ok


def _msg91(phone: str, message: str) -> bool:
    num = _digits(phone)
    r = httpx.post(
        "https://api.msg91.com/api/v5/flow/",
        headers={"authkey": settings.sms_api_key, "Content-Type": "application/json"},
        json={"template_id": settings.msg91_template_id, "sender": settings.sms_sender_id,
              "short_url": "0", "recipients": [{"mobiles": num, "var1": message}]},
        timeout=_TIMEOUT,
    )
    ok = r.status_code == 200
    if not ok:
        log.warning("msg91 send failed: %s %s", r.status_code, r.text[:200])
    return ok


def _twilio(phone: str, message: str) -> bool:
    sid = settings.twilio_account_sid
    to = phone if phone.startswith("+") else f"+{_digits(phone)}"
    r = httpx.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        data={"From": settings.sms_sender_id, "To": to, "Body": message},
        auth=(sid, settings.twilio_auth_token),
        timeout=_TIMEOUT,
    )
    ok = r.status_code in (200, 201)
    if not ok:
        log.warning("twilio send failed: %s %s", r.status_code, r.text[:200])
    return ok


_PROVIDERS = {"2factor": _2factor, "fast2sms": _fast2sms, "msg91": _msg91, "twilio": _twilio}


def send(phone: str, message: str) -> bool:
    provider = (settings.sms_provider or "console").lower()
    if provider == "console":
        log.info("[SMS to %s] %s", phone, message)
        print(f"[SMS to {phone}] {message}")
        return True
    fn = _PROVIDERS.get(provider)
    if fn is None:
        log.warning("SMS provider %r not supported; message not sent", provider)
        return False
    try:
        return fn(phone, message)
    except Exception:  # noqa: BLE001 - never let SMS delivery break the OTP flow
        log.exception("SMS send via %s failed", provider)
        return False


def send_otp(phone: str, code: str) -> bool:
    provider = (settings.sms_provider or "console").lower()
    msg = f"Your AgriSetuAI verification code is {code}. Valid for 5 minutes."
    # 2Factor.in: delivers our code through its pre-approved OTP template (no DLT
    # work on our side) — the recommended India path.
    if provider == "2factor":
        try:
            return _2factor_otp(phone, code)
        except Exception:  # noqa: BLE001 - never let SMS delivery break the OTP flow
            log.exception("2factor OTP send failed")
            return False
    # Fast2SMS: the dedicated OTP route needs website verification; the Quick ("q")
    # route works immediately. FAST2SMS_ROUTE selects which to use.
    if provider == "fast2sms":
        try:
            if (settings.fast2sms_route or "otp").lower() == "otp":
                return _fast2sms_otp(phone, code)
            return _fast2sms(phone, msg)  # Quick route (no verification needed)
        except Exception:  # noqa: BLE001 - never let SMS delivery break the OTP flow
            log.exception("fast2sms OTP send failed")
            return False
    return send(phone, msg)
