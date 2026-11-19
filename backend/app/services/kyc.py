"""Identity-KYC gating.

Identity verification (a government photo-ID approved by staff) gates money
*leaving* the platform: a payee's accrued payout / withdrawal is held until their
identity is verified, mirroring the existing verified-payout-account gate.

Only payees that carry a profile with a verification_status are subject to this
(farmers/sellers, household/business buyers). Transport partners have no such
profile, so identity-KYC is N/A for them and the verified-payout-account gate
(enforced separately) governs their disbursement.
"""
from app.models.user import User


def identity_applicable(user: User | None) -> bool:
    """True when identity-KYC applies to this user (they have a verifiable profile)."""
    return bool(user and (user.farmer_profile or user.buyer_profile))


def identity_verified(user: User | None) -> bool:
    """True when the payee may receive money: either identity-KYC does not apply
    (no verifiable profile, e.g. transport) or their profile is verified."""
    if user is None:
        return False
    prof = user.farmer_profile or user.buyer_profile
    if prof is None:
        return True  # identity-KYC N/A (e.g. transport) — account gate still applies
    return prof.verification_status == "verified"
