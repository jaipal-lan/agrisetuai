"""Field leader / manager console: monitor field agents and the verification
pipeline, and pass (assign) orders to agents. A field leader runs a mandal's
agents; a field manager oversees leaders across a district."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.rbac import Role
from app.models.catalog import Commodity
from app.models.common import OrderStatus as S
from app.models.order import Inspection, Order
from app.models.user import User

router = APIRouter(prefix="/team", tags=["team"])

_lead = require_roles(Role.FIELD_LEADER, Role.FIELD_MANAGER, Role.SUPERADMIN)

_INSPECTION_STATES = (S.INSPECTION_ASSIGNED, S.INSPECTION_IN_PROGRESS, S.INSPECTION_HOLD)
_ACTIVE = (S.CONFIRMED, S.PAYMENT_PENDING, S.PAID, S.PACKING, S.READY_FOR_PICKUP,
           S.PICKED_UP, S.IN_TRANSIT, S.OUT_FOR_DELIVERY)


@router.get("/overview")
def overview(user=Depends(_lead), db: Session = Depends(get_db)):
    """Agents with their workload, and the orders currently needing verification."""
    names = {u.id: (u.name or f"user {u.id}") for u in db.scalars(select(User))}

    # Field agents + how many inspections each has done / has open now.
    agents = []
    for a in db.scalars(select(User).where(User.role == str(Role.FIELD_AGENT))):
        done = db.scalar(select(func.count(Inspection.id)).where(Inspection.agent_id == a.id)) or 0
        open_jobs = db.scalar(select(func.count(Order.id)).where(
            Order.assigned_agent_id == a.id, Order.status.in_(_INSPECTION_STATES))) or 0
        agents.append({"id": a.id, "name": a.name, "inspections_done": done, "open_jobs": open_jobs})
    agents.sort(key=lambda x: (-x["open_jobs"], x["name"] or ""))

    # Orders in the inspection stage (assigned or waiting to be assigned).
    pipeline = []
    for o in db.scalars(select(Order).where(Order.status.in_(_INSPECTION_STATES))
                        .order_by(Order.created_at)):
        t = o.accepted_terms or {}
        c = db.get(Commodity, t.get("commodity_id")) if t.get("commodity_id") else None
        pipeline.append({
            "order_id": o.id, "public_id": o.public_id, "status": o.status,
            "commodity": c.name if c else None,
            "quantity": t.get("quantity"), "unit": t.get("unit", "kg"),
            "assigned_agent_id": o.assigned_agent_id,
            "assigned_agent_name": names.get(o.assigned_agent_id) if o.assigned_agent_id else None,
        })

    active_orders = db.scalar(select(func.count(Order.id)).where(Order.status.in_(_ACTIVE))) or 0
    return {
        "agents": agents,
        "pipeline": pipeline,
        "unassigned": sum(1 for p in pipeline if not p["assigned_agent_id"]),
        "active_orders": active_orders,
    }
