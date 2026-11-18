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


def _media_url(key: str | None) -> str | None:
    if not key:
        return None
    return key if key.startswith("http") else f"/media/file/{key}"


def _secure_media_url(key: str | None) -> str | None:
    """A signed, expiring view-link for a PRIVATE file (KYC / ID doc). Cloudinary
    private assets are already stored as a signed https URL; local keys are routed
    through the token-gated /media/secure endpoint. Minted only inside auth-gated
    responses (the owner's /auth/me, staff's /admin/kyc)."""
    if not key:
        return None
    if key.startswith("http"):
        return key  # Cloudinary authenticated asset — already a signed URL
    from urllib.parse import quote

    from app.core.security import issue_media_token
    return f"/media/secure/{quote(key, safe='/')}?token={issue_media_token(key)}"


def _id_documents(user: User) -> list:
    docs = getattr(user, "id_documents", None) or []
    out = []
    for d in docs:
        if not isinstance(d, dict):
            continue
        out.append({
            "object_key": d.get("object_key"),
            "url": _secure_media_url(d.get("object_key")),
            "doc_type": d.get("doc_type"),
            "uploaded_at": d.get("uploaded_at"),
        })
    return out


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
        "id_documents": _id_documents(user),
    }
