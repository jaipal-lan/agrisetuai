"""Safe serializers — never leak PII the workflow has not disclosed (PRD 2.1, 13.1).

Phone numbers, payout beneficiary refs, bank details and precise locations are not
returned in listings/search or to unrelated users.
"""
from app.models.user import User


def public_user(user: User) -> dict:
    """Minimal seller/buyer card — safe for cross-party display."""
    return {
        "id": user.id,
        "name": user.name,
        "role": user.role,
    }


def self_user(user: User) -> dict:
    """The authenticated user's own profile."""
    return {
        "id": user.id,
        "phone": user.phone,
        "name": user.name,
        "role": user.role,
        "preferred_language": user.preferred_language,
        "status": user.status,
        "onboarding_complete": user.onboarding_complete,
        "organisation_id": user.organisation_id,
    }
