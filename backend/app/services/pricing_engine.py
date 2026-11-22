"""Server-side pricing engine (PRD section 7 & 8).

Produces a fully itemised, auditable quote. Clients never compute fees; they only
display the server's breakdown. The same function powers the admin "simulate"
preview and live order quoting, so previews match real charges exactly.
"""
from dataclasses import asdict, dataclass
from decimal import Decimal

from app.core.money import money, qty
from app.models.pricing import PricingRule

# Convert a sale quantity to chargeable transport weight (kg). Weight units are
# exact; non-weight units (piece/dozen) have no reliable weight in the pilot, so
# they fall back to the quantity (documented limitation — real logistics pricing
# would carry a weight-per-unit).
_UNIT_TO_KG = {"kg": Decimal("1"), "quintal": Decimal("100"), "litre": Decimal("1"),
               "ton": Decimal("1000"), "tonne": Decimal("1000")}


def billable_kg_for(unit: str | None, quantity) -> Decimal:
    factor = _UNIT_TO_KG.get((unit or "kg").lower(), Decimal("1"))
    return qty(Decimal(str(quantity)) * factor)


@dataclass
class QuoteInput:
    product_value: Decimal       # price_per_unit * quantity
    billable_kg: Decimal         # chargeable weight for transport
    route_km: Decimal            # road distance pickup -> destination
    include_inspection: bool = True
    include_packing: bool = True
    # Subscription fee discount applied to the seller commission (0-100).
    commission_discount_pct: Decimal = Decimal("0")


@dataclass
class Quote:
    currency: str
    rule_version: int
    product_value: str
    packing_fee: str
    inspection_fee: str
    transport_charge: str
    service_fee: str
    service_fee_payer: str
    seller_commission: str
    seller_commission_pct: str
    tax: str
    buyer_total: str
    seller_payable: str
    breakdown: dict

    def to_json(self) -> dict:
        return asdict(self)


def _transport(rule: PricingRule, inp: QuoteInput) -> Decimal:
    raw = (
        inp.billable_kg * Decimal(str(rule.rate_per_kg))
        + inp.route_km * Decimal(str(rule.rate_per_km))
        + Decimal(str(rule.fixed_pickup_fee))
    )
    charge = max(Decimal(str(rule.min_transport_charge)), raw)
    if rule.max_transport_charge is not None:
        charge = min(charge, Decimal(str(rule.max_transport_charge)))
    return money(charge)


def compute(rule: PricingRule, inp: QuoteInput) -> Quote:
    product_value = money(inp.product_value)
    packing = money(rule.packing_fee) if inp.include_packing else money(0)
    inspection = money(rule.inspection_fee) if inp.include_inspection else money(0)
    transport = _transport(rule, inp)

    service_fee = money(
        product_value * Decimal(str(rule.service_fee_pct)) / Decimal("100")
        + Decimal(str(rule.service_fee_flat))
    )
    payer = rule.service_fee_payer

    # Seller commission: the platform's cut, always from the seller's proceeds.
    # A subscription fee discount reduces the effective commission rate.
    base_pct = Decimal(str(rule.seller_commission_pct))
    discount = max(Decimal("0"), min(Decimal("100"), Decimal(str(inp.commission_discount_pct))))
    effective_pct = base_pct * (Decimal("100") - discount) / Decimal("100")
    seller_commission = money(product_value * effective_pct / Decimal("100"))

    # GST applies to the platform's taxable services (inspection, packing and the
    # service fee the buyer pays). Transport of agricultural produce is exempt, so
    # it is excluded from the taxable base (per the approved tax blueprint).
    taxable = inspection + packing
    if payer == "buyer":
        taxable += service_fee
    tax = money(taxable * Decimal(str(rule.tax_pct)) / Decimal("100"))

    # Buyer pays product + logistics (buyer-paid logistics is a locked rule).
    buyer_total = product_value + packing + inspection + transport + tax
    # Seller receives product value minus the commission (and the service fee
    # only if the seller is the payer).
    seller_payable = product_value - seller_commission
    if payer == "buyer":
        buyer_total += service_fee
    else:
        seller_payable -= service_fee

    return Quote(
        currency=rule.currency,
        rule_version=rule.version,
        product_value=str(product_value),
        packing_fee=str(packing),
        inspection_fee=str(inspection),
        transport_charge=str(transport),
        service_fee=str(service_fee),
        service_fee_payer=payer,
        seller_commission=str(seller_commission),
        seller_commission_pct=str(effective_pct),
        tax=str(tax),
        buyer_total=str(money(buyer_total)),
        seller_payable=str(money(seller_payable)),
        breakdown={
            "billable_kg": str(inp.billable_kg),
            "route_km": str(inp.route_km),
            "rate_per_kg": str(rule.rate_per_kg),
            "rate_per_km": str(rule.rate_per_km),
            "fixed_pickup_fee": str(rule.fixed_pickup_fee),
            "min_transport_charge": str(rule.min_transport_charge),
            "seller_commission_pct": str(rule.seller_commission_pct),
            "commission_discount_pct": str(discount),
            "service_fee_pct": str(rule.service_fee_pct),
            "service_fee_flat": str(rule.service_fee_flat),
            "tax_pct": str(rule.tax_pct),
        },
    )
