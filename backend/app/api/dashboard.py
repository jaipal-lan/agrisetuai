"""Role-based dashboard — each role gets its own stats + quick actions.

A farmer, a buyer, a field agent / leader / manager, a transport partner and the
superadmin each see a home screen tailored to what they do.
"""
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.money import money
from app.core.rbac import Role
from app.models.common import OrderStatus as S
from app.models.finance import Payout
from app.models.marketplace import Listing, Offer, RFQ
from app.models.order import Order, Shipment
from app.models.support import Dispute, Notification
from app.models.team import AgentTarget, TeamMeeting
from app.models.user import BuyerProfile, FarmerProfile, User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_ROLE_LABEL = {
    "farmer": "Farmer",
    "buyer_household": "Household buyer",
    "buyer_business": "Business buyer",
    "field_agent": "Field agent",
    "field_leader": "Field leader",
    "field_manager": "Field manager",
    "transport": "Transport partner",
    "superadmin": "Superadmin",
}

# Per-card icon (keyed by label) so the dashboard reads richly without the
# frontend hard-coding emoji against localized strings.
_CARD_ICONS = {
    "Active listings": "🌾", "Open negotiations": "🤝", "Orders selling": "📦",
    "Awaiting payout": "💰", "Orders buying": "🛒", "Open offers": "🤝",
    "Orders in progress": "📦", "Open requests (RFQ)": "📋",
    "Inspections to do": "🔍", "My targets": "🎯", "Upcoming meetings": "📅",
    "Unassigned inspections": "📥", "In inspection": "🔎", "Field agents": "👥",
    "Active targets": "🎯", "GMV (settled)": "📈", "Open disputes": "⚖️",
    "Pending payouts": "💸", "Active deliveries": "🚚", "Earnings (paid)": "💰",
    "Total orders": "📦", "Open listings": "🌾", "Pending KYC": "🪪",
    "Held at warehouse": "🏬", "Unread alerts": "🔔",
}

_TERMINAL = (S.SETTLED, S.CANCELLED, S.REFUNDED)
_INSPECTION_STATES = (S.INSPECTION_ASSIGNED, S.INSPECTION_IN_PROGRESS, S.INSPECTION_HOLD)
_ACTIVE_SHIPMENT = (S.READY_FOR_PICKUP, S.PICKED_UP, S.IN_TRANSIT, S.OUT_FOR_DELIVERY)


def _count(db: Session, stmt) -> int:
    return db.scalar(stmt) or 0


def _settled_gmv(db: Session) -> object:
    gmv = money(0)
    for o in db.scalars(select(Order).where(Order.status == S.SETTLED)):
        t = o.accepted_terms or {}
        gmv += money(float(t.get("price_per_unit", 0)) * float(t.get("quantity", 0)))
    return gmv


@router.get("")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    role = user.role
    cards: list[dict] = []
    actions: list[dict] = []

    # Instant unread only — digest-deferred alerts don't ping the bell.
    unread = _count(db, select(func.count(Notification.id)).where(
        Notification.user_id == user.id, Notification.read_at.is_(None),
        Notification.deferred.is_(False)))

    if role == Role.FARMER:
        active_listings = _count(db, select(func.count(Listing.id)).where(
            Listing.seller_id == user.id, Listing.status == "open"))
        open_negotiations = _count(db, select(func.count(Offer.id)).where(
            Offer.seller_id == user.id, Offer.status == "open"))
        active_orders = _count(db, select(func.count(Order.id)).where(
            Order.seller_id == user.id, Order.status.not_in(_TERMINAL)))
        pending_payout = money(0)
        for p in db.scalars(select(Payout).where(Payout.seller_id == user.id, Payout.status == "pending")):
            pending_payout += money(p.amount)
        # A farmer can also buy — surface their buying activity too.
        buying_orders = _count(db, select(func.count(Order.id)).where(
            Order.buyer_id == user.id, Order.status.not_in(_TERMINAL)))
        cards = [
            {"label": "Active listings", "value": active_listings, "href": "/sell"},
            {"label": "Open negotiations", "value": open_negotiations, "href": "/offers", "alert": open_negotiations > 0},
            {"label": "Orders selling", "value": active_orders, "href": "/orders"},
            {"label": "Awaiting payout", "value": f"₹{pending_payout}", "href": "/earnings"},
            {"label": "Orders buying", "value": buying_orders, "href": "/orders"},
        ]
        actions = [
            {"label": "List produce", "href": "/sell", "primary": True},
            {"label": "Buy produce", "href": "/"},
            {"label": "My offers", "href": "/offers"},
            {"label": "My orders", "href": "/orders"},
            {"label": "Earnings", "href": "/earnings"},
            {"label": "Invoices", "href": "/invoices"},
            {"label": "Market prices", "href": "/prices"},
        ]

    elif role in (Role.BUYER_HOUSEHOLD, Role.BUYER_BUSINESS):
        open_offers = _count(db, select(func.count(Offer.id)).where(
            Offer.buyer_id == user.id, Offer.status == "open"))
        active_orders = _count(db, select(func.count(Order.id)).where(
            Order.buyer_id == user.id, Order.status.not_in(_TERMINAL)))
        open_rfqs = _count(db, select(func.count(RFQ.id)).where(
            RFQ.buyer_id == user.id, RFQ.status == "open"))
        cards = [
            {"label": "Open offers", "value": open_offers, "href": "/offers", "alert": open_offers > 0},
            {"label": "Orders in progress", "value": active_orders, "href": "/orders"},
            {"label": "Open requests (RFQ)", "value": open_rfqs, "href": "/requests"},
        ]
        actions = [
            {"label": "Browse market", "href": "/", "primary": True},
            {"label": "Post a requirement", "href": "/requests"},
            {"label": "My offers", "href": "/offers"},
            {"label": "My orders", "href": "/orders"},
            {"label": "Invoices", "href": "/invoices"},
            {"label": "Market prices", "href": "/prices"},
        ]

    elif role == Role.FIELD_AGENT:
        jobs = _count(db, select(func.count(Order.id)).where(
            Order.assigned_agent_id == user.id, Order.status.in_(_INSPECTION_STATES)))
        my_targets = _count(db, select(func.count(AgentTarget.id)).where(
            AgentTarget.agent_id == user.id, AgentTarget.status == "active"))
        meetings = _count(db, select(func.count(TeamMeeting.id)).where(
            TeamMeeting.status == "scheduled"))
        cards = [
            {"label": "Inspections to do", "value": jobs, "href": "/agent", "alert": jobs > 0},
            {"label": "My targets", "value": my_targets, "href": "/agent"},
            {"label": "Upcoming meetings", "value": meetings, "href": "/agent", "alert": meetings > 0},
        ]
        actions = [{"label": "Inspection jobs", "href": "/agent", "primary": True}]

    elif role in (Role.FIELD_LEADER, Role.FIELD_MANAGER):
        # Mandal lead / district manager: oversee verification + the pipeline.
        in_inspection = _count(db, select(func.count(Order.id)).where(
            Order.status.in_(_INSPECTION_STATES)))
        unassigned = _count(db, select(func.count(Order.id)).where(
            Order.status.in_(_INSPECTION_STATES), Order.assigned_agent_id.is_(None)))
        agents = _count(db, select(func.count(User.id)).where(User.role == str(Role.FIELD_AGENT)))
        at_warehouse = _count(db, select(func.count(Order.id)).where(Order.status == S.DELIVERY_FAILED))
        active_orders = _count(db, select(func.count(Order.id)).where(Order.status.not_in(_TERMINAL)))
        active_targets = _count(db, select(func.count(AgentTarget.id)).where(AgentTarget.status == "active"))
        upcoming_meetings = _count(db, select(func.count(TeamMeeting.id)).where(TeamMeeting.status == "scheduled"))
        cards = [
            {"label": "Unassigned inspections", "value": unassigned, "href": "/team", "alert": unassigned > 0},
            {"label": "In inspection", "value": in_inspection, "href": "/team"},
            {"label": "Field agents", "value": agents, "href": "/team"},
            {"label": "Active targets", "value": active_targets, "href": "/team"},
            {"label": "Upcoming meetings", "value": upcoming_meetings, "href": "/team"},
            {"label": "Held at warehouse", "value": at_warehouse, "href": "/orders", "alert": at_warehouse > 0},
            {"label": "Orders in progress", "value": active_orders, "href": "/orders"},
        ]
        actions = [
            {"label": "Team console", "href": "/team", "primary": True},
            {"label": "Inspection jobs", "href": "/agent"},
            {"label": "Market prices", "href": "/prices"},
        ]
        if role == Role.FIELD_MANAGER:
            open_disputes = _count(db, select(func.count(Dispute.id)).where(Dispute.status != "decided"))
            pending_payouts = _count(db, select(func.count(Payout.id)).where(Payout.status == "pending"))
            cards += [
                {"label": "GMV (settled)", "value": f"₹{_settled_gmv(db)}", "href": "/admin"},
                {"label": "Open disputes", "value": open_disputes, "href": "/support", "alert": open_disputes > 0},
                {"label": "Pending payouts", "value": pending_payouts, "href": "/admin", "alert": pending_payouts > 0},
            ]
            actions += [{"label": "Admin console", "href": "/admin"},
                        {"label": "Disputes & refunds", "href": "/support"}]

    elif role == Role.TRANSPORT:
        active = _count(db, select(func.count(Shipment.id)).where(Shipment.status.in_(_ACTIVE_SHIPMENT)))
        paid = money(0)
        pending_pay = money(0)
        for p in db.scalars(select(Payout).where(Payout.payee_type == "transport", Payout.seller_id == user.id)):
            if p.status == "pending":
                pending_pay += money(p.amount)
            else:
                paid += money(p.amount)
        cards = [
            {"label": "Active deliveries", "value": active, "href": "/transport", "alert": active > 0},
            {"label": "Earnings (paid)", "value": f"₹{paid}", "href": "/transport"},
            {"label": "Awaiting payout", "value": f"₹{pending_pay}", "href": "/transport", "alert": pending_pay > money(0)},
        ]
        actions = [{"label": "Delivery jobs", "href": "/transport", "primary": True},
                   {"label": "My earnings", "href": "/transport"}]

    else:  # superadmin
        total_orders = _count(db, select(func.count(Order.id)))
        open_listings = _count(db, select(func.count(Listing.id)).where(Listing.status == "open"))
        pending_kyc = (_count(db, select(func.count(FarmerProfile.user_id)).where(FarmerProfile.verification_status == "pending"))
                       + _count(db, select(func.count(BuyerProfile.user_id)).where(BuyerProfile.verification_status == "pending")))
        open_disputes = _count(db, select(func.count(Dispute.id)).where(Dispute.status != "decided"))
        pending_payouts = _count(db, select(func.count(Payout.id)).where(Payout.status == "pending"))
        at_warehouse = _count(db, select(func.count(Order.id)).where(Order.status == S.DELIVERY_FAILED))
        cards = [
            {"label": "Total orders", "value": total_orders, "href": "/admin"},
            {"label": "Held at warehouse", "value": at_warehouse, "href": "/admin", "alert": at_warehouse > 0},
            {"label": "GMV (settled)", "value": f"₹{_settled_gmv(db)}", "href": "/admin"},
            {"label": "Open listings", "value": open_listings, "href": "/"},
            {"label": "Pending KYC", "value": pending_kyc, "href": "/admin", "alert": pending_kyc > 0},
            {"label": "Open disputes", "value": open_disputes, "href": "/support", "alert": open_disputes > 0},
            {"label": "Pending payouts", "value": pending_payouts, "href": "/admin", "alert": pending_payouts > 0},
        ]
        actions = [{"label": "Admin console", "href": "/admin", "primary": True},
                   {"label": "Team console", "href": "/team"},
                   {"label": "Disputes & refunds", "href": "/support"}]

    cards.append({"label": "Unread alerts", "value": unread, "href": "/inbox", "alert": unread > 0})

    for c in cards:
        c.setdefault("icon", _CARD_ICONS.get(c["label"], "•"))

    return {
        "role": role,
        "role_label": _ROLE_LABEL.get(role, role),
        "name": user.name,
        "onboarding_complete": user.onboarding_complete,
        "cards": cards,
        "actions": actions,
        "today": date.today().isoformat(),
    }
