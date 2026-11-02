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
        ("919000000006", "Dr. Suresh (Agronomist)", Role.AGRONOMIST),
        ("919000000007", "Support Desk", Role.SUPPORT),
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


def seed_advisory(db: Session) -> None:
    from app.models.advisory import KnowledgeSource

    items = [
        {
            "slug": "paddy-bpt-blast",
            "crop": "paddy",
            "title": "Rice blast — scouting & IPM-first management",
            "title_te": "వరి అగ్గి తెగులు — IPM నిర్వహణ",
            "keywords": ["blast", "leaf spot", "neck", "lesion", "paddy", "rice", "spots"],
            "source_name": "State Agriculture Dept / ANGRAU advisory",
            "source_url": "https://angrau.ac.in/",
            "reviewed_by": "Dr. Suresh (Senior Agronomy Reviewer)",
            "reviewed_on": "2026-09-15",
            "content": {
                "confidence": "medium",
                "category": "fungal_disease",
                "likely_causes": [
                    {"label": "Rice blast (Magnaporthe oryzae)", "likelihood": "likely", "uncertainty": "medium", "category": "fungal_disease"},
                    {"label": "Brown spot (nutrient/abiotic stress)", "likelihood": "possible", "uncertainty": "medium", "category": "nutrient"},
                ],
                "immediate_steps": [
                    "Scout 10 random spots; count affected tillers vs healthy.",
                    "Avoid excess nitrogen; drain and re-flood to reduce humidity in the canopy.",
                    "Remove and destroy severely affected debris.",
                ],
                "ipm_order": [
                    "Confirm blast vs brown spot (neck/leaf lesions, spindle shape).",
                    "Balanced nutrition + water management first.",
                    "Use resistant varieties next season.",
                    "Only a reviewed, label-consistent fungicide if the economic threshold is crossed — with agronomist escalation.",
                ],
                "pesticide": {"label_sourced": False},
            },
        },
        {
            "slug": "chilli-thrips",
            "crop": "red chilli",
            "title": "Chilli thrips & leaf curl — monitoring and IPM",
            "title_te": "మిర్చి తామర పురుగు — పర్యవేక్షణ",
            "keywords": ["thrips", "leaf curl", "chilli", "curl", "silvering", "mites"],
            "source_name": "KVK / State Horticulture advisory",
            "source_url": "https://krishi.icar.gov.in/",
            "reviewed_by": "Dr. Suresh (Senior Agronomy Reviewer)",
            "reviewed_on": "2026-09-20",
            "content": {
                "confidence": "medium",
                "category": "insect_pest",
                "likely_causes": [
                    {"label": "Thrips (leaf curl complex)", "likelihood": "likely", "uncertainty": "medium", "category": "insect_pest"},
                ],
                "immediate_steps": [
                    "Install blue sticky traps to monitor thrips numbers.",
                    "Remove curled, infested shoots; avoid staggered sowing nearby.",
                ],
                "pesticide": {"label_sourced": False},
            },
        },
    ]
    for it in items:
        defaults = {k: v for k, v in it.items() if k != "slug"}
        _get_or_create(db, KnowledgeSource, slug=it["slug"], defaults=defaults)


def seed_insights(db: Session, mandals: dict) -> None:
    from app.models.advisory import (
        CropCalendarTask,
        MarketPrice,
        Scheme,
        WeatherSnapshot,
    )

    tenali = mandals.get("Tenali")
    if tenali and not db.scalar(
        select(WeatherSnapshot).where(WeatherSnapshot.mandal_id == tenali.id)
    ):
        db.add(WeatherSnapshot(
            mandal_id=tenali.id, provider="Pilot IMD-style snapshot",
            observed_at="2026-11-02T06:00+05:30", forecast_horizon="3d",
            payload={"rain_prob_pct": 40, "temp_max_c": 31, "temp_min_c": 23,
                     "wind_kmph": 12, "alert": None},
        ))

    for row in [
        ("Guntur Market Yard", "Paddy", "BPT 5204", 2100, 2450, 2300, "₹/qtl"),
        ("Guntur Market Yard", "Red Chilli", "Teja", 17000, 21000, 19000, "₹/qtl"),
        ("Tenali", "Toor Dal", None, 9000, 10500, 9800, "₹/qtl"),
    ]:
        market, commodity, variety, lo, hi, modal, unit = row
        if not db.scalar(select(MarketPrice).where(
            MarketPrice.market == market, MarketPrice.commodity == commodity
        )):
            db.add(MarketPrice(
                market=market, commodity=commodity, variety=variety,
                min_price=lo, max_price=hi, modal_price=modal, unit=unit,
                arrivals="moderate", as_of="2026-11-01",
                source_name="AGMARKNET (pilot sample)", source_url="https://agmarknet.gov.in/",
            ))

    for crop, window, task, task_te, kind in [
        ("paddy", "Nursery (June–July)", "Raise nursery; treat seed; 25-30 day seedlings", "నారుమడి", "reviewed"),
        ("paddy", "Tillering (+30d)", "First top-dressing of N; keep 2-3 cm water", "మొదటి ఎరువు", "reviewed"),
        ("paddy", "Panicle (+65d)", "Scout for blast/BPH; avoid excess N", "అగ్గి/దోమ పర్యవేక్షణ", "reviewed"),
    ]:
        if not db.scalar(select(CropCalendarTask).where(
            CropCalendarTask.crop == crop, CropCalendarTask.window == window
        )):
            db.add(CropCalendarTask(crop=crop, window=window, task=task,
                                    task_te=task_te, kind=kind,
                                    source="ANGRAU crop calendar (pilot)"))

    if not db.scalar(select(Scheme).where(Scheme.name.like("PM-KISAN%"))):
        db.add(Scheme(
            name="PM-KISAN Samman Nidhi", name_te="పీఎం-కిసాన్",
            department="Dept. of Agriculture & Farmers Welfare, GoI",
            eligibility="Landholding farmer families, subject to exclusion criteria.",
            documents="Aadhaar, land records, bank account",
            apply_route="Village revenue officer / PM-KISAN portal",
            deadline=None, source_url="https://pmkisan.gov.in/",
            last_checked="2026-10-30",
        ))
    if not db.scalar(select(Scheme).where(Scheme.name.like("Rythu Bharosa%"))):
        db.add(Scheme(
            name="Rythu Bharosa (AP)", name_te="రైతు భరోసా",
            department="Govt. of Andhra Pradesh — Agriculture",
            eligibility="Eligible farmer families per state guidelines.",
            documents="Aadhaar, land/tenancy records, bank account",
            apply_route="Rythu Bharosa Kendram / state portal",
            deadline=None, source_url="https://www.ap.gov.in/",
            last_checked="2026-10-30",
        ))


def main() -> None:
    run_migrations()
    db = SessionLocal()
    try:
        mandals = seed_locations(db)
        seed_catalog(db)
        seed_users(db, mandals)
        seed_pricing(db)
        seed_advisory(db)
        seed_insights(db, mandals)
        db.commit()
        print("Seeded locations, catalog, demo users, pricing, advisory + insights.")
        print(f"Superadmin phone: {settings.superadmin_phone} (dev OTP: {settings.master_otp})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
