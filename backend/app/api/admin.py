from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.money import money
from app.core.rbac import Role
from app.models.audit import AuditLog
from app.models.common import OrderStatus as S
from app.models.finance import LedgerEntry
from app.models.marketplace import Listing
from app.models.order import Order

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
