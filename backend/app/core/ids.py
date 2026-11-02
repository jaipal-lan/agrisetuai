"""Human-readable, collision-resistant public identifiers.

Lot IDs and order IDs appear on labels, QR codes and receipts, so they are short,
uppercase and prefixed by type rather than raw UUIDs.
"""
import secrets
import string

_ALPHABET = string.ascii_uppercase + string.digits
# Drop ambiguous characters for anything a human/scanner might read back.
_SAFE = "".join(c for c in _ALPHABET if c not in "O0I1")


def _rand(n: int) -> str:
    return "".join(secrets.choice(_SAFE) for _ in range(n))


def public_id(prefix: str, n: int = 8) -> str:
    return f"{prefix}-{_rand(n)}"


def order_id() -> str:
    return public_id("ORD", 8)


def lot_id() -> str:
    return public_id("LOT", 8)


def shipment_id() -> str:
    return public_id("SHP", 8)


def ticket_id() -> str:
    return public_id("TCK", 8)


def dispute_id() -> str:
    return public_id("DSP", 8)


def case_id() -> str:
    return public_id("CSE", 8)


def quality_id() -> str:
    return public_id("QTY", 8)


def idempotency_key() -> str:
    return secrets.token_hex(16)
