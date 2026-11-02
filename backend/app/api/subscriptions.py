"""Membership subscriptions for farmers/FPOs and buyers.

Plans are a catalog (seeded). Subscribing snapshots the plan's benefits onto the
Subscription row so later plan edits never retroactively change an active member.
Payment is the same MOCK flow the rest of the app uses: subscribing posts a
balanced double-entry ledger transaction (platform subscription revenue), so the
admin ledger stays the single source of truth for money.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.core.money import money
from app.core.rbac import BUYER_ROLES, SELLER_ROLES, Role
from app.models.common import LedgerDirection, ensure_aware, utcnow
from app.models.subscription import Subscription, SubscriptionPlan
from app.models.user import User
from app.services import ledger

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


def _audience_for(user: User) -> str | None:
    """Which plan audience this user may buy, or None if their role can't."""
    if user.role in {str(r) for r in SELLER_ROLES}:
        return "farmer"
    if user.role in {str(r) for r in BUYER_ROLES}:
        return "buyer"
    return None


def _plan_dict(p: SubscriptionPlan) -> dict:
    return {
        "code": p.code,
        "name": p.name,
        "name_te": p.name_te,
        "audience": p.audience,
        "price": float(p.price),
        "period_days": p.period_days,
        "benefits": p.benefits or {},
    }


def _sub_dict(s: Subscription) -> dict:
    return {
        "id": s.id,
        "plan_code": s.plan_code,
        "plan_name": s.plan_name,
        "audience": s.audience,
        "price": float(s.price),
        "benefits": s.benefits or {},
        "status": s.status,
        "started_at": ensure_aware(s.started_at).isoformat(),
        "expires_at": ensure_aware(s.expires_at).isoformat(),
    }


def active_subscription(db: Session, user_id: int) -> Subscription | None:
    """The user's current, non-expired active subscription (latest-expiring)."""
    now = utcnow()
    return db.scalars(
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.status == "active",
            Subscription.expires_at > now,
        )
        .order_by(Subscription.expires_at.desc())
    ).first()


def active_benefits(db: Session, user_id: int) -> dict:
    """Benefits of the user's active subscription (empty dict if none).

    Importable by other routers (e.g. listing caps / fee discounts)."""
    s = active_subscription(db, user_id)
    return (s.benefits or {}) if s else {}


@router.get("/plans")
def list_plans(audience: str | None = None, db: Session = Depends(get_db)):
    stmt = select(SubscriptionPlan).where(SubscriptionPlan.active.is_(True))
    if audience:
        stmt = stmt.where(SubscriptionPlan.audience == audience)
    stmt = stmt.order_by(
        SubscriptionPlan.audience, SubscriptionPlan.sort, SubscriptionPlan.price
    )
    return [_plan_dict(p) for p in db.scalars(stmt).all()]


@router.get("/me")
def my_subscription(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    s = active_subscription(db, user.id)
    return {
        "audience": _audience_for(user),
        "subscription": _sub_dict(s) if s else None,
        "benefits": (s.benefits or {}) if s else {},
    }


class SubscribeBody(BaseModel):
    plan_code: str


@router.post("/subscribe")
def subscribe(
    body: SubscribeBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    audience = _audience_for(user)
    if audience is None:
        raise HTTPException(400, "Only farmers/FPOs or buyers can subscribe")
    plan = db.scalars(
        select(SubscriptionPlan).where(
            SubscriptionPlan.code == body.plan_code,
            SubscriptionPlan.active.is_(True),
        )
    ).first()
    if plan is None:
        raise HTTPException(404, "Plan not found")
    if plan.audience != audience:
        raise HTTPException(400, f"This plan is for {plan.audience} accounts")

    now = utcnow()
    # Supersede any current active subscription (upgrade/downgrade/renew).
    current = active_subscription(db, user.id)
    if current is not None:
        current.status = "cancelled"

    sub = Subscription(
        user_id=user.id,
        plan_code=plan.code,
        plan_name=plan.name,
        audience=plan.audience,
        price=money(plan.price),
        benefits=plan.benefits,
        status="active",
        started_at=now,
        expires_at=now + timedelta(days=plan.period_days),
    )
    db.add(sub)
    db.flush()  # assign sub.id for the txn group
    sub.txn_group = f"sub:{sub.id}"

    # MOCK payment -> balanced ledger entry (skip for free plans).
    if money(plan.price) > money(0):
        ledger.post(
            db,
            txn_group=sub.txn_group,
            legs=[
                ledger.Leg(
                    account="subscription_receipts",
                    direction=LedgerDirection.DEBIT,
                    amount=money(plan.price),
                    memo=f"{plan.name} — {user.phone}",
                ),
                ledger.Leg(
                    account="platform_subscription_revenue",
                    direction=LedgerDirection.CREDIT,
                    amount=money(plan.price),
                    memo=plan.name,
                ),
            ],
        )

    db.commit()
    db.refresh(sub)
    return {"subscription": _sub_dict(sub)}


@router.post("/cancel")
def cancel(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Cancel the current active subscription. Access runs out at expiry; no refund
    in the mock flow."""
    sub = active_subscription(db, user.id)
    if sub is None:
        raise HTTPException(404, "No active subscription")
    sub.status = "cancelled"
    db.commit()
    return {"ok": True}


@router.get("/admin")
def admin_overview(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.SUPERADMIN, Role.FINANCE)),
):
    now = utcnow()
    subs = db.scalars(
        select(Subscription).order_by(Subscription.created_at.desc()).limit(200)
    ).all()
    active_count = sum(
        1 for s in subs if s.status == "active" and ensure_aware(s.expires_at) > now
    )
    total_revenue = db.scalar(
        select(func.coalesce(func.sum(Subscription.price), 0))
    )
    by_plan: dict[str, int] = {}
    for s in subs:
        by_plan[s.plan_code] = by_plan.get(s.plan_code, 0) + 1
    return {
        "active_count": active_count,
        "total_count": len(subs),
        "total_revenue": float(total_revenue or 0),
        "by_plan": by_plan,
        "subscriptions": [_sub_dict(s) for s in subs],
    }
