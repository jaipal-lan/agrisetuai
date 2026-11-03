"""Role-based dashboard — each role gets its own stats + quick actions.

The whole point: a farmer, a buyer, a field agent, a courier, an agronomist
and platform staff must NOT see the same home screen. This endpoint returns a
role-specific payload the frontend renders as that role's dashboard.
"""
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.money import money
from app.core.rbac import Role
from app.models.advisory import AdvisoryLog, CropCase
from app.models.common import OrderStatus as S
from app.models.finance import Payout
from app.models.marketplace import Listing, Offer, RFQ
from app.models.order import Inspection, Order, Shipment
from app.models.support import Dispute, Notification
from app.models.user import BuyerProfile, FarmerProfile, User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_ROLE_LABEL = {
    "farmer": "Farmer", "fpo": "FPO", "buyer_household": "Household buyer",
    "buyer_business": "Business buyer", "field_agent": "Field agent",
    "agronomist": "Agronomist", "transport": "Transport partner",
    "support": "Support", "mandal_manager": "Mandal manager",
    "finance": "Finance", "superadmin": "Superadmin",
}

_TERMINAL = (S.SETTLED, S.CANCELLED, S.REFUNDED)
_INSPECTION_STATES = (S.INSPECTION_ASSIGNED, S.INSPECTION_IN_PROGRESS, S.INSPECTION_HOLD)
_ACTIVE_SHIPMENT = (S.READY_FOR_PICKUP, S.PICKED_UP, S.IN_TRANSIT, S.OUT_FOR_DELIVERY)


def _count(db: Session, stmt) -> int:
    return db.scalar(stmt) or 0


@router.get("")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    role = user.role
    cards: list[dict] = []
    actions: list[dict] = []

    unread = _count(db, select(func.count(Notification.id)).where(
        Notification.user_id == user.id, Notification.read_at.is_(None)))

    if role in (Role.FARMER, Role.FPO):
        active_listings = _count(db, select(func.count(Listing.id)).where(
            Listing.seller_id == user.id, Listing.status == "open"))
        open_negotiations = _count(db, select(func.count(Offer.id)).where(
            Offer.seller_id == user.id, Offer.status == "open"))
        active_orders = _count(db, select(func.count(Order.id)).where(
            Order.seller_id == user.id, Order.status.not_in(_TERMINAL)))
        pending_payout = money(0)
        for p in db.scalars(select(Payout).where(Payout.seller_id == user.id, Payout.status == "pending")):
            pending_payout += money(p.amount)
        cards = [
            {"label": "Active listings", "value": active_listings, "href": "/sell"},
            {"label": "Open negotiations", "value": open_negotiations, "href": "/offers", "alert": open_negotiations > 0},
            {"label": "Orders in progress", "value": active_orders, "href": "/orders"},
            {"label": "Awaiting payout", "value": f"₹{pending_payout}", "href": "/earnings"},
        ]
        actions = [
            {"label": "List produce", "href": "/sell", "primary": True},
            {"label": "My offers", "href": "/offers"},
            {"label": "My orders", "href": "/orders"},
            {"label": "Earnings", "href": "/earnings"},
            {"label": "Invoices", "href": "/invoices"},
            {"label": "Crop advice", "href": "/advisory"},
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
        ]

    elif role == Role.FIELD_AGENT:
        jobs = _count(db, select(func.count(Order.id)).where(
            Order.assigned_agent_id == user.id, Order.status.in_(_INSPECTION_STATES)))
        advisories = _count(db, select(func.count(AdvisoryLog.id)).where(AdvisoryLog.agent_id == user.id))
        cards = [
            {"label": "Inspections to do", "value": jobs, "href": "/agent", "alert": jobs > 0},
            {"label": "Advisories logged", "value": advisories, "href": "/agent"},
        ]
        actions = [
            {"label": "Inspection jobs", "href": "/agent", "primary": True},
            {"label": "Crop advice", "href": "/advisory"},
        ]

    elif role == Role.AGRONOMIST:
        to_review = _count(db, select(func.count(CropCase.id)).where(
            CropCase.status == "open", CropCase.escalated.is_(True)))
        cards = [
            {"label": "Cases to review", "value": to_review, "href": "/advisory", "alert": to_review > 0},
        ]
        actions = [{"label": "Review crop cases", "href": "/advisory", "primary": True}]

    elif role == Role.TRANSPORT:
        active = _count(db, select(func.count(Shipment.id)).where(Shipment.status.in_(_ACTIVE_SHIPMENT)))
        cards = [
            {"label": "Active shipments", "value": active, "href": "/transport", "alert": active > 0},
        ]
        actions = [{"label": "Transport jobs", "href": "/transport", "primary": True}]

    else:  # staff: support, mandal_manager, finance, superadmin
        total_orders = _count(db, select(func.count(Order.id)))
        open_listings = _count(db, select(func.count(Listing.id)).where(Listing.status == "open"))
        gmv = money(0)
        for o in db.scalars(select(Order).where(Order.status == S.SETTLED)):
            t = o.accepted_terms or {}
            gmv += money(float(t.get("price_per_unit", 0)) * float(t.get("quantity", 0)))
        pending_kyc = (_count(db, select(func.count(FarmerProfile.user_id)).where(FarmerProfile.verification_status == "pending"))
                       + _count(db, select(func.count(BuyerProfile.user_id)).where(BuyerProfile.verification_status == "pending")))
        open_disputes = _count(db, select(func.count(Dispute.id)).where(Dispute.status != "decided"))
        pending_payouts = _count(db, select(func.count(Payout.id)).where(Payout.status == "pending"))
        cards = [
            {"label": "Total orders", "value": total_orders, "href": "/admin"},
            {"label": "GMV (settled)", "value": f"₹{gmv}", "href": "/admin"},
            {"label": "Open listings", "value": open_listings, "href": "/"},
            {"label": "Pending KYC", "value": pending_kyc, "href": "/admin", "alert": pending_kyc > 0},
            {"label": "Open disputes", "value": open_disputes, "href": "/support", "alert": open_disputes > 0},
            {"label": "Pending payouts", "value": pending_payouts, "href": "/admin", "alert": pending_payouts > 0},
        ]
        actions = [{"label": "Admin console", "href": "/admin", "primary": True},
                   {"label": "Disputes & refunds", "href": "/support"}]
        if role in (Role.MANDAL_MANAGER, Role.SUPERADMIN):
            actions.append({"label": "Inspection jobs", "href": "/agent"})

    cards.append({"label": "Unread alerts", "value": unread, "href": "/inbox", "alert": unread > 0})

    return {
        "role": role,
        "role_label": _ROLE_LABEL.get(role, role),
        "name": user.name,
        "onboarding_complete": user.onboarding_complete,
        "cards": cards,
        "actions": actions,
        "today": date.today().isoformat(),
    }
