"""Stateless signed tokens (stdlib only) + in-memory OTP store.

Token = base64url(payload).signature where signature = HMAC-SHA256(payload, secret).
No external JWT dependency. Swap the OTP store for Redis in multi-worker prod.
"""
import base64
import hashlib
import hmac
import json
import time

from app.core.config import settings


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(payload_b64: str) -> str:
    sig = hmac.new(
        settings.effective_secret.encode(), payload_b64.encode(), hashlib.sha256
    ).digest()
    return _b64e(sig)


def issue_token(user_id: int) -> str:
    payload = {"sub": user_id, "exp": int(time.time()) + settings.token_ttl_seconds}
    payload_b64 = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    return f"{payload_b64}.{_sign(payload_b64)}"


def verify_token(token: str) -> int | None:
    try:
        payload_b64, sig = token.split(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(sig, _sign(payload_b64)):
        return None
    try:
        payload = json.loads(_b64d(payload_b64))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return int(payload["sub"])


# --- OTP store ------------------------------------------------------------
# phone -> (code, expires_at)
_otp: dict[str, tuple[str, float]] = {}


def set_otp(phone: str, code: str) -> None:
    _otp[phone] = (code, time.time() + settings.otp_ttl_seconds)


def check_otp(phone: str, code: str) -> bool:
    if settings.dev_mode and code == settings.master_otp:
        return True
    rec = _otp.get(phone)
    if not rec:
        return False
    stored, exp = rec
    if time.time() > exp:
        _otp.pop(phone, None)
        return False
    if hmac.compare_digest(stored, code):
        _otp.pop(phone, None)
        return True
    return False
