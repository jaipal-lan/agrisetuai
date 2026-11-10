"""Role-based access control + scope helpers.

A simplified role set for the door-to-door produce marketplace:

  farmer          — sells produce (and may also buy)
  buyer_household  / buyer_business — buy produce
  field_agent     — mandal-level field staff who verify produce before dispatch
  field_leader    — mandal-level lead over agents (monitor, assign, set targets)
  field_manager   — district-level manager over field leaders
  transport       — delivery partner (door delivery)
  superadmin      — platform owner
"""
from enum import StrEnum


class Role(StrEnum):
    FARMER = "farmer"
    BUYER_HOUSEHOLD = "buyer_household"
    BUYER_BUSINESS = "buyer_business"
    FIELD_AGENT = "field_agent"
    FIELD_LEADER = "field_leader"
    FIELD_MANAGER = "field_manager"
    TRANSPORT = "transport"
    SUPERADMIN = "superadmin"


SELLER_ROLES = {Role.FARMER}
BUYER_ROLES = {Role.BUYER_HOUSEHOLD, Role.BUYER_BUSINESS}
# Field hierarchy: agents on the ground, leaders (mandal), managers (district).
FIELD_ROLES = {Role.FIELD_AGENT, Role.FIELD_LEADER, Role.FIELD_MANAGER}
STAFF_ROLES = {
    Role.FIELD_AGENT,
    Role.FIELD_LEADER,
    Role.FIELD_MANAGER,
    Role.TRANSPORT,
    Role.SUPERADMIN,
}
# Operational roles that may configure or override things (subject to further checks).
PRIVILEGED_ROLES = {Role.FIELD_LEADER, Role.FIELD_MANAGER, Role.SUPERADMIN}
