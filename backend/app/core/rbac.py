"""Role-based access control + scope helpers.

Roles mirror the PRD (section 2). RBAC here is coarse (role gating); fine-grained
scope (state/district/mandal/assigned-order/organisation) is enforced inside each
endpoint using the user's profile where it matters.
"""
from enum import StrEnum


class Role(StrEnum):
    FARMER = "farmer"
    FPO = "fpo"
    BUYER_HOUSEHOLD = "buyer_household"
    BUYER_BUSINESS = "buyer_business"
    FIELD_AGENT = "field_agent"
    AGRONOMIST = "agronomist"
    TRANSPORT = "transport"
    SUPPORT = "support"
    MANDAL_MANAGER = "mandal_manager"
    FINANCE = "finance"
    SUPERADMIN = "superadmin"


SELLER_ROLES = {Role.FARMER, Role.FPO}
BUYER_ROLES = {Role.BUYER_HOUSEHOLD, Role.BUYER_BUSINESS}
STAFF_ROLES = {
    Role.FIELD_AGENT,
    Role.AGRONOMIST,
    Role.TRANSPORT,
    Role.SUPPORT,
    Role.MANDAL_MANAGER,
    Role.FINANCE,
    Role.SUPERADMIN,
}
# Operational roles that may configure or override things (subject to further checks).
PRIVILEGED_ROLES = {Role.MANDAL_MANAGER, Role.FINANCE, Role.SUPERADMIN}
