from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.money import money
from app.core.rbac import Role
from app.models.advisory import CropCase
from app.models.audit import AuditLog
from app.models.catalog import Commodity
from app.models.common import OrderStatus as S
from app.models.finance import LedgerEntry
from app.models.location import District, Mandal, State
from app.models.marketplace import Listing, Offer, RFQ
from app.models.order import Inspection, Order
from app.models.support import Dispute, SupportTicket
from app.models.user import AgentProfile, User

router = APIRouter(prefix="/admin", tags=["admin"])

_staff = require_roles(Role.SUPERADMIN, Role.FINANCE, Role.MANDAL_MANAGER)


@router.get("/kpis")
def kpis(user=Depends(_staff), db: Session = Depends(get_db)):
    total_orders = db.scalar(select(func.count(Order.id))) or 0
    settled = db.scalar(select(func.count(Order.id)).where(Order.status == S.SETTLED)) or 0
    cancelled = db.scalar(select(func.count(Order.id)).where(Order.status == S.CANCELLED)) or 0
    open_listings = db.scalar(select(func.count(Listing.id)).where(Listing.status == "open")) or 0

    # GMV = product value of settled trades (from accepted terms).
    gmv = money(0)
    for o in db.scalars(select(Order).where(Order.status == S.SETTLED)):
        t = o.accepted_terms
        gmv += money(float(t["price_per_unit"]) * float(t["quantity"]))

    return {
        "total_orders": total_orders,
        "settled_orders": settled,
        "cancelled_orders": cancelled,
        "open_listings": open_listings,
        "gmv_settled": str(gmv),
    }


@router.get("/reports")
def reports(user=Depends(_staff), db: Session = Depends(get_db)):
    """GMV and order counts broken down by commodity, mandal, state and agent.

    GMV is the product value of PAID-or-beyond trades (revenue-recognised).
    """
    paid_states = [S.PAID, S.PACKING, S.READY_FOR_PICKUP, S.PICKED_UP, S.IN_TRANSIT,
                   S.OUT_FOR_DELIVERY, S.DELIVERED_PENDING_ACCEPTANCE, S.COMPLETED, S.SETTLED]

    # Lookups.
    commodities = {c.id: c.name for c in db.scalars(select(Commodity))}
    mandals = {}
    for m in db.scalars(select(Mandal)):
        mandals[m.id] = m
    districts = {d.id: d for d in db.scalars(select(District))}
    states = {s.id: s.name for s in db.scalars(select(State))}
    agent_names = {u.id: u.name for u in db.scalars(select(User))}

    def blank():
        return {"gmv": 0.0, "orders": 0}

    by_commodity: dict = {}
    by_mandal: dict = {}
    by_state: dict = {}
    by_agent: dict = {}
    total_gmv = 0.0
    total_orders = 0

    for o in db.scalars(select(Order).where(Order.status.in_(paid_states))):
        t = o.accepted_terms or {}
        value = float(t.get("price_per_unit", 0)) * float(t.get("quantity", 0))
        total_gmv += value
        total_orders += 1

        cname = commodities.get(t.get("commodity_id"), "—")
        c = by_commodity.setdefault(cname, blank()); c["gmv"] += value; c["orders"] += 1

        m = mandals.get(t.get("mandal_id"))
        mname = m.name if m else "—"
        mm = by_mandal.setdefault(mname, blank()); mm["gmv"] += value; mm["orders"] += 1

        sname = "—"
        if m:
            d = districts.get(m.district_id)
            if d:
                sname = states.get(d.state_id, "—")
        ss = by_state.setdefault(sname, blank()); ss["gmv"] += value; ss["orders"] += 1

        if o.assigned_agent_id:
            an = agent_names.get(o.assigned_agent_id, f"agent {o.assigned_agent_id}")
            aa = by_agent.setdefault(an, blank()); aa["gmv"] += value; aa["orders"] += 1

    def fmt(d: dict) -> list:
        return sorted(
            [{"key": k, "gmv": str(money(v["gmv"])), "orders": v["orders"]} for k, v in d.items()],
            key=lambda r: float(r["gmv"]), reverse=True,
        )

    return {
        "total_gmv": str(money(total_gmv)),
        "total_orders": total_orders,
        "by_commodity": fmt(by_commodity),
        "by_mandal": fmt(by_mandal),
        "by_state": fmt(by_state),
        "by_agent": fmt(by_agent),
    }


@router.get("/ledger/accounts")
def ledger_accounts(user=Depends(_staff), db: Session = Depends(get_db)):
    """Net balance per account + global balance check (should be zero)."""
    rows = db.scalars(select(LedgerEntry))
    balances: dict[str, float] = {}
    for r in rows:
        amt = float(r.amount)
        balances[r.account] = balances.get(r.account, 0.0) + (amt if r.direction == "credit" else -amt)
    net = sum(balances.values())
    return {
        "accounts": {k: str(money(v)) for k, v in sorted(balances.items())},
        "net_balance": str(money(net)),
        "balanced": money(net) == money(0),
    }


@router.get("/audit-logs")
def audit_logs(limit: int = 100, user=Depends(_staff), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))
    return [
        {
            "id": a.id,
            "actor_id": a.actor_id,
            "action": a.action,
            "object_type": a.object_type,
            "object_id": a.object_id,
            "reason": a.reason,
            "at": a.at.isoformat(),
        }
        for a in rows
    ]
