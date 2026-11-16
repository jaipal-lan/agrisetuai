"""Safe serializers — never leak PII the workflow has not disclosed (PRD 2.1, 13.1).

Phone numbers, payout beneficiary refs, bank details and precise locations are not
returned in listings/search or to unrelated users.
"""
from app.models.user import User


def _avatar_url(user: User) -> str | None:
    key = getattr(user, "avatar_object_key", None)
    if not key:
        return None
    # Cloudinary URLs are stored whole; local keys are served via /media/file.
    return key if key.startswith("http") else f"/media/file/{key}"


def _mask(v: str | None) -> str | None:
    if not v:
        return None
    v = v.strip()
    return ("*" * max(0, len(v) - 4)) + v[-4:] if len(v) > 4 else v


def public_user(user: User) -> dict:
    """Minimal seller/buyer card — safe for cross-party display."""
    return {
        "id": user.id,
        "name": user.name,
        "role": user.role,
        "avatar_url": _avatar_url(user),
    }


def self_user(user: User) -> dict:
    """The authenticated user's own profile."""
    return {
        "id": user.id,
        "phone": user.phone,
        "name": user.name,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "avatar_url": _avatar_url(user),
        "role": user.role,
        "preferred_language": user.preferred_language,
        "status": user.status,
        "onboarding_complete": user.onboarding_complete,
        "organisation_id": user.organisation_id,
        "district": user.district,
        "state": user.state,
        "pincode": user.pincode,
        "aadhaar_masked": _mask(user.aadhaar),
        "pan_masked": _mask(user.pan),
        "has_aadhaar": bool(user.aadhaar),
        "has_pan": bool(user.pan),
    }
