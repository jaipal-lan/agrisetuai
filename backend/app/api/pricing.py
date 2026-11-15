from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.core.money import D
from app.core.rbac import Role
from app.models.catalog import Commodity
from app.models.common import utcnow
from app.models.marketplace import Listing
from app.models.order import Order
from app.models.pricing import PricingRule
from app.services import audit
from app.services.pricing_engine import QuoteInput, compute

router = APIRouter(tags=["pricing"])

_superadmin = require_roles(Role.SUPERADMIN)


class RuleDraft(BaseModel):
    service_mandal_id: int | None = None
    handling_class: str | None = None
    currency: str = "INR"
    rate_per_kg: float = 0
    rate_per_km: float = 0
    fixed_pickup_fee: float = 0
    min_transport_charge: float = 0
    max_transport_charge: float | None = None
    seller_commission_pct: float = 0
    service_fee_pct: float = 0
    service_fee_flat: float = 0
    service_fee_payer: str = "buyer"
    inspection_fee: float = 0
    packing_fee: float = 0
    tax_pct: float = 0
    surcharges: dict | None = None
    reason: str | None = None
    requires_second_approval: bool = False


class SimulateInput(BaseModel):
    product_value: float
    billable_kg: float
    route_km: float
    include_inspection: bool = True
    include_packing: bool = True


def _rule_json(r: PricingRule) -> dict:
    return {
        "id": r.id,
        "version": r.version,
        "status": r.status,
        "service_mandal_id": r.service_mandal_id,
        "handling_class": r.handling_class,
        "currency": r.currency,
        "rate_per_kg": str(r.rate_per_kg),
        "rate_per_km": str(r.rate_per_km),
        "fixed_pickup_fee": str(r.fixed_pickup_fee),
        "min_transport_charge": str(r.min_transport_charge),
        "max_transport_charge": None if r.max_transport_charge is None else str(r.max_transport_charge),
        "seller_commission_pct": str(r.seller_commission_pct),
        "service_fee_pct": str(r.service_fee_pct),
        "service_fee_flat": str(r.service_fee_flat),
        "service_fee_payer": r.service_fee_payer,
        "inspection_fee": str(r.inspection_fee),
        "packing_fee": str(r.packing_fee),
        "tax_pct": str(r.tax_pct),
        "effective_from": r.effective_from.isoformat() if r.effective_from else None,
        "reason": r.reason,
    }


def _next_version(db: Session) -> int:
    current = db.scalar(select(PricingRule.version).order_by(PricingRule.version.desc()))
    return (current or 0) + 1


@router.get("/pricing/rules")
def list_rules(db: Session = Depends(get_db)):
    rows = db.scalars(select(PricingRule).order_by(PricingRule.version.desc()))
    return [_rule_json(r) for r in rows]


@router.post("/admin/pricing-rules/draft", status_code=status.HTTP_201_CREATED)
def create_draft(body: RuleDraft, user=Depends(_superadmin), db: Session = Depends(get_db)):
    rule = PricingRule(
        version=_next_version(db),
        status="draft",
        created_by=user.id,
        **body.model_dump(exclude={"reason", "requires_second_approval"}),
        reason=body.reason,
        requires_second_approval=body.requires_second_approval,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    audit.record(db, actor_id=user.id, action="pricing.draft", object_type="pricing_rule",
                 object_id=rule.id, new_values=_rule_json(rule))
    db.commit()
    return _rule_json(rule)


@router.post("/admin/pricing-rules/{rule_id}/simulate")
def simulate(rule_id: int, body: SimulateInput, user=Depends(_superadmin), db: Session = Depends(get_db)):
    rule = db.get(PricingRule, rule_id)
    if not rule:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    quote = compute(
        rule,
        QuoteInput(
            product_value=D(body.product_value),
            billable_kg=D(body.billable_kg),
            route_km=D(body.route_km),
            include_inspection=body.include_inspection,
            include_packing=body.include_packing,
        ),
    )
    return quote.to_json()


@router.post("/admin/pricing-rules/{rule_id}/publish")
def publish_rule(rule_id: int, user=Depends(_superadmin), db: Session = Depends(get_db)):
    rule = db.get(PricingRule, rule_id)
    if not rule:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    if rule.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only drafts can be published")
    if rule.requires_second_approval and rule.approved_by is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Second approval required")

    # Retire previously published rules of the same scope (confirmed orders keep
    # their snapshotted version, so this never reprices them).
    others = db.scalars(
        select(PricingRule).where(
            PricingRule.status == "published",
            PricingRule.service_mandal_id == rule.service_mandal_id,
            PricingRule.handling_class == rule.handling_class,
        )
    )
    for o in others:
        o.status = "retired"

    rule.status = "published"
    rule.effective_from = utcnow()
    audit.record(db, actor_id=user.id, action="pricing.publish", object_type="pricing_rule",
                 object_id=rule.id, new_values={"version": rule.version})
    db.commit()
    return _rule_json(rule)


def order_pricing_context(db: Session, order: Order) -> tuple[int | None, str | None]:
    """Resolve (mandal_id, handling_class) for an order.

    Prefers the commodity/mandal snapshotted into accepted_terms (works for both
    listing- and RFQ-based orders); falls back to the source listing.
    """
    terms = order.accepted_terms or {}
    commodity_id = terms.get("commodity_id")
    mandal_id = terms.get("mandal_id")
    if commodity_id is None:
        line = order.lines[0] if order.lines else None
        listing = db.get(Listing, line.listing_id) if line and line.listing_id else None
        if listing:
            commodity_id = listing.commodity_id
            mandal_id = listing.mandal_id
    handling_class = None
    if commodity_id:
        commodity = db.get(Commodity, commodity_id)
        handling_class = commodity.handling_class if commodity else None
    return mandal_id, handling_class


def active_rule_for(db: Session, *, mandal_id: int | None, handling_class: str | None) -> PricingRule | None:
    """Most specific published rule: prefer mandal+class match, then class, then global."""
    published = list(db.scalars(select(PricingRule).where(PricingRule.status == "published")))

    def score(r: PricingRule) -> int:
        s = 0
        if r.service_mandal_id is not None and r.service_mandal_id == mandal_id:
            s += 2
        elif r.service_mandal_id is not None:
            return -1  # scoped to a different mandal -> ineligible
        if r.handling_class is not None and r.handling_class == handling_class:
            s += 1
        elif r.handling_class is not None:
            return -1
        return s

    eligible = [(score(r), r.version, r) for r in published if score(r) >= 0]
    if not eligible:
        return None
    eligible.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return eligible[0][2]


@router.get("/pricing/quote")
def quote_for_order(
    order_id: int,
    route_km: float = 0,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    if user.id not in (order.buyer_id, order.seller_id) and user.role not in (
        Role.SUPERADMIN, Role.FIELD_MANAGER, Role.FIELD_LEADER,
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")

    terms = order.accepted_terms
    product_value = D(terms["price_per_unit"]) * D(terms["quantity"])
    from app.services.pricing_engine import billable_kg_for
    billable_kg = billable_kg_for(terms.get("unit"), terms["quantity"])

    mandal_id, handling_class = order_pricing_context(db, order)
    rule = active_rule_for(db, mandal_id=mandal_id, handling_class=handling_class)
    if not rule:
        raise HTTPException(status.HTTP_409_CONFLICT, "No published pricing rule applies")

    quote = compute(
        rule,
        QuoteInput(product_value=product_value, billable_kg=billable_kg, route_km=D(route_km)),
    )
    return quote.to_json()
