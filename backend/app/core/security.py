"""Stateless signed tokens (stdlib only) + in-memory OTP store.

Token = base64url(payload).signature where signature = HMAC-SHA256(payload, secret).
No external JWT dependency. Swap the OTP store for Redis in multi-worker prod.
"""
import base64
import hashlib
import hmac
import json
import os
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


def issue_token(user_id: int, token_version: int = 0) -> str:
    payload = {
        "sub": user_id,
        "ver": int(token_version),
        "exp": int(time.time()) + settings.token_ttl_seconds,
    }
    payload_b64 = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    return f"{payload_b64}.{_sign(payload_b64)}"


def decode_token(token: str) -> dict | None:
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
    return payload


def verify_token(token: str) -> int | None:
    payload = decode_token(token)
    if payload is None:
        return None
    return int(payload["sub"])


# --- Passwords (stdlib PBKDF2; no external bcrypt dependency) ---------------
# Chosen to match the project's stdlib-only ethos (see tokens above). Format is
# self-describing so the iteration count can be raised later without a migration.
_PBKDF2_ITERATIONS = 180_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${_b64e(salt)}${_b64e(dk)}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), _b64d(salt_b64), int(iters))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(_b64e(dk), hash_b64)


# --- Short-lived phone-ownership token -------------------------------------
# Issued once an OTP is verified, so multi-step registration / password reset
# can prove phone ownership on a later request without re-sending the OTP (which
# is single-use). Purpose-scoped ("pv") so it can't be used as an auth token.
def issue_phone_token(phone: str) -> str:
    payload = {
        "ph": phone,
        "pur": "pv",
        "exp": int(time.time()) + settings.phone_token_ttl_seconds,
    }
    payload_b64 = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    return f"{payload_b64}.{_sign(payload_b64)}"


def verify_phone_token(token: str) -> str | None:
    payload = decode_token(token)  # validates signature + expiry
    if not payload or payload.get("pur") != "pv":
        return None
    return payload.get("ph")


# --- OTP store ------------------------------------------------------------
# phone -> (code, expires_at)
_otp: dict[str, tuple[str, float]] = {}
# phone -> request timestamps (rate limit)
_otp_hits: dict[str, list[float]] = {}


def otp_rate_ok(phone: str) -> bool:
    now = time.time()
    window = settings.otp_window_seconds
    hits = [t for t in _otp_hits.get(phone, []) if now - t < window]
    if len(hits) >= settings.otp_max_per_window:
        _otp_hits[phone] = hits
        return False
    hits.append(now)
    _otp_hits[phone] = hits
    return True


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
