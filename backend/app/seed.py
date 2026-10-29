"""Seed reference data + demo users for local development.

Idempotent: safe to run repeatedly. Run with `python -m app.seed`.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, run_migrations
from app.core.rbac import Role
from app.models.catalog import Commodity, GradeSpec, Variety
from app.models.common import utcnow
from app.models.location import District, Mandal, State
from app.models.pricing import PricingRule
from app.models.user import AgentProfile, BuyerProfile, FarmerProfile, User


def _get_or_create(db: Session, model, defaults=None, **keys):
    obj = db.scalar(select(model).filter_by(**keys))
    if obj:
        return obj, False
    obj = model(**keys, **(defaults or {}))
    db.add(obj)
    db.flush()
    return obj, True


def seed_locations(db: Session) -> dict:
    data = {
        "Andhra Pradesh": ("AP", {"Guntur": ["Tenali", "Mangalagiri"], "Krishna": ["Gudivada"]}),
        "Telangana": ("TG", {"Nalgonda": ["Miryalaguda"], "Karimnagar": ["Huzurabad"]}),
    }
    mandals: dict[str, Mandal] = {}
    for state_name, (code, districts) in data.items():
        state, _ = _get_or_create(db, State, name=state_name, code=code)
        for dname, mnames in districts.items():
            district, _ = _get_or_create(db, District, name=dname, state_id=state.id)
            for mname in mnames:
                m, _ = _get_or_create(db, Mandal, name=mname, district_id=district.id,
                                      defaults={"serviceable": True})
                mandals[mname] = m
    return mandals


def seed_catalog(db: Session) -> dict:
    out = {}
    paddy, _ = _get_or_create(
        db, Commodity, category="paddy", name="Paddy", product_form="paddy",
        defaults={"name_te": "వరి ధాన్యం", "unit": "kg", "handling_class": "dry_grain"},
    )
    rice, _ = _get_or_create(
        db, Commodity, category="rice", name="Milled Rice", product_form="milled_rice",
        defaults={"name_te": "బియ్యం", "unit": "kg", "handling_class": "dry_grain"},
    )
    toor, _ = _get_or_create(
        db, Commodity, category="pulses", name="Toor Dal", product_form="whole",
        defaults={"name_te": "కందిపప్పు", "unit": "kg", "handling_class": "dry_grain"},
    )
    chilli, _ = _get_or_create(
        db, Commodity, category="spices", name="Red Chilli", product_form="dried",
        defaults={"name_te": "ఎండు మిర్చి", "unit": "kg", "handling_class": "dry_spice"},
    )
    for c in (paddy, rice, toor, chilli):
        _get_or_create(db, GradeSpec, commodity_id=c.id, code="FAQ",
                       defaults={"label": "Fair Average Quality",
                                 "attributes": {"max_moisture_pct": 14, "max_foreign_matter_pct": 2}})
    _get_or_create(db, Variety, commodity_id=paddy.id, name="BPT 5204",
                   defaults={"name_te": "బీపీటీ 5204"})
    out.update(paddy=paddy, rice=rice, toor=toor, chilli=chilli)
    return out


def seed_users(db: Session, mandals: dict) -> dict:
    tenali = mandals.get("Tenali")
    defs = [
        ("919999999998", "Platform Admin", Role.SUPERADMIN),
        ("919000000001", "Mandal Manager", Role.MANDAL_MANAGER),
        ("919000000002", "Field Agent", Role.FIELD_AGENT),
        ("919000000003", "Ravi (Farmer)", Role.FARMER),
        ("919000000004", "Lakshmi Traders", Role.BUYER_BUSINESS),
        ("919000000005", "Transport Co", Role.TRANSPORT),
    ]
    users = {}
    for phone, name, role in defs:
        u, _ = _get_or_create(db, User, phone=phone,
                              defaults={"name": name, "role": str(role),
                                        "onboarding_complete": True})
        users[role] = u
    # Attach minimal profiles.
    farmer = users[Role.FARMER]
    if not db.scalar(select(FarmerProfile).where(FarmerProfile.user_id == farmer.id)):
        db.add(FarmerProfile(user_id=farmer.id, mandal_id=tenali.id if tenali else None,
                             village="Kolakaluru", verification_status="verified"))
    buyer = users[Role.BUYER_BUSINESS]
    if not db.scalar(select(BuyerProfile).where(BuyerProfile.user_id == buyer.id)):
        db.add(BuyerProfile(user_id=buyer.id, buyer_type="business",
                            verification_status="verified"))
    agent = users[Role.FIELD_AGENT]
    if not db.scalar(select(AgentProfile).where(AgentProfile.user_id == agent.id)):
        db.add(AgentProfile(user_id=agent.id, skill_level="Field Agricultural Advisor",
                            service_mandals=[tenali.id] if tenali else [], languages="te,en"))
    return users


def seed_pricing(db: Session) -> None:
    if db.scalar(select(PricingRule).where(PricingRule.status == "published")):
        return
    rule = PricingRule(
        version=1, status="published", handling_class=None, currency="INR",
        rate_per_kg=0.80, rate_per_km=12.0, fixed_pickup_fee=150, min_transport_charge=300,
        max_transport_charge=None, service_fee_pct=2.0, service_fee_flat=0,
        service_fee_payer="buyer", inspection_fee=300, packing_fee=500, tax_pct=0,
        effective_from=utcnow(), reason="Initial pilot tariff",
    )
    db.add(rule)


def main() -> None:
    run_migrations()
    db = SessionLocal()
    try:
        mandals = seed_locations(db)
        seed_catalog(db)
        seed_users(db, mandals)
        seed_pricing(db)
        db.commit()
        print("Seeded locations, catalog, demo users and pricing rule v1.")
        print(f"Superadmin phone: {settings.superadmin_phone} (dev OTP: {settings.master_otp})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
