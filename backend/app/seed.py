"""Seed reference data + demo users for local development.

Idempotent: safe to run repeatedly. Run with `python -m app.seed`.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, run_migrations
from app.core.money import D
from app.core.rbac import Role
from app.models.catalog import Commodity, GradeSpec, Variety
from app.models.common import ListingStatus, utcnow
from app.models.marketplace import Listing, ListingMedia
from app.models.location import District, Mandal, State
from app.models.pricing import PricingRule
from app.models.subscription import SubscriptionPlan
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
    # (latitude, longitude) centroids let the distance service compute route_km.
    data = {
        "Andhra Pradesh": ("AP", {
            "Guntur": [("Tenali", 16.2430, 80.6400), ("Mangalagiri", 16.4300, 80.5500)],
            "Krishna": [("Gudivada", 16.4333, 80.9950)],
        }),
        "Telangana": ("TG", {
            "Nalgonda": [("Miryalaguda", 16.8716, 79.5650)],
            "Karimnagar": [("Huzurabad", 18.1950, 79.4050)],
        }),
    }
    mandals: dict[str, Mandal] = {}
    for state_name, (code, districts) in data.items():
        state, _ = _get_or_create(db, State, name=state_name, code=code)
        for dname, mnames in districts.items():
            district, _ = _get_or_create(db, District, name=dname, state_id=state.id)
            for mname, lat, lon in mnames:
                m, created = _get_or_create(
                    db, Mandal, name=mname, district_id=district.id,
                    defaults={"serviceable": True, "latitude": D(lat), "longitude": D(lon)},
                )
                # Backfill coordinates for mandals seeded before this column existed.
                if m.latitude is None:
                    m.latitude = D(lat)
                    m.longitude = D(lon)
                mandals[mname] = m
    return mandals


# (category, name, product_form, name_te, handling_class, [varieties], [grades])
_CATALOG = [
    ("paddy", "Paddy", "paddy", "వరి ధాన్యం", "dry_grain",
     [("BPT 5204", "బీపీటీ 5204"), ("MTU 1010", "ఎంటీయూ 1010"), ("Sona Masoori", "సోనా మసూరి")],
     [("FAQ", "Fair Average Quality", {"max_moisture_pct": 17, "max_foreign_matter_pct": 2})]),
    ("rice", "Milled Rice", "milled_rice", "బియ్యం", "dry_grain",
     [("Sona Masoori", "సోనా మసూరి"), ("HMT", "హెచ్ఎంటీ")],
     [("A", "Grade A", {"max_broken_pct": 5, "max_moisture_pct": 14})]),
    ("pulses", "Toor Dal", "whole", "కందిపప్పు", "dry_grain",
     [("LRG 41", "ఎల్ఆర్‌జీ 41")],
     [("FAQ", "Fair Average Quality", {"max_moisture_pct": 12, "max_foreign_matter_pct": 2})]),
    ("pulses", "Green Gram", "whole", "పెసలు", "dry_grain",
     [("WGG 42", "డబ్ల్యూజీజీ 42")],
     [("FAQ", "Fair Average Quality", {"max_moisture_pct": 12})]),
    ("pulses", "Bengal Gram", "whole", "శనగలు", "dry_grain",
     [("JG 11", "జేజీ 11")],
     [("FAQ", "Fair Average Quality", {"max_moisture_pct": 12})]),
    ("oilseeds", "Groundnut", "pods", "వేరుశెనగ", "dry_grain",
     [("K6", "కే6"), ("TMV 2", "టీఎంవీ 2")],
     [("FAQ", "Fair Average Quality", {"max_moisture_pct": 8, "max_oil_content_pct": None})]),
    ("cereals", "Maize", "grain", "మొక్కజొన్న", "dry_grain",
     [("DKC 9108", "డీకేసీ 9108")],
     [("FAQ", "Fair Average Quality", {"max_moisture_pct": 14, "max_foreign_matter_pct": 2})]),
    # ---- spices ----
    ("spices", "Red Chilli", "dried", "ఎండు మిర్చి", "dry_spice",
     [("Teja S17", "తేజా"), ("Byadgi", "బ్యాడ్గి"), ("334", "334")],
     [("FAQ", "Fair Average Quality", {"max_moisture_pct": 11, "min_colour_asta": 40})]),
    ("spices", "Turmeric", "dried_finger", "పసుపు", "dry_spice",
     [("Salem", "సేలం"), ("Rajapuri", "రాజాపురి"), ("Duggirala", "దుగ్గిరాల")],
     [("Finger", "Finger", {"min_curcumin_pct": 3, "max_moisture_pct": 10}),
      ("Bulb", "Bulb", {"min_curcumin_pct": 2.5, "max_moisture_pct": 10})]),
    ("spices", "Black Pepper", "dried_berry", "మిరియాలు", "dry_spice",
     [("Malabar Garbled", "మలబార్"), ("Tellicherry", "తెల్లిచెర్రి")],
     [("MG1", "Malabar Garbled 1", {"min_bulk_density_g_l": 500, "max_moisture_pct": 11})]),
    ("spices", "Coriander Seed", "dried_seed", "ధనియాలు", "dry_spice",
     [("Eagle", "ఈగల్"), ("Sadhana", "సాధన")],
     [("FAQ", "Fair Average Quality", {"max_moisture_pct": 9, "max_foreign_matter_pct": 2})]),
    ("spices", "Cumin Seed", "dried_seed", "జీలకర్ర", "dry_spice",
     [("Gujarat Local", "గుజరాత్")],
     [("99%", "99% Purity", {"min_purity_pct": 99, "max_moisture_pct": 9})]),
    ("spices", "Tamarind", "deseeded", "చింతపండు", "dry_spice",
     [("Seedless", "విత్తనరహిత")],
     [("FAQ", "Fair Average Quality", {"max_moisture_pct": 18})]),
    ("spices", "Dry Ginger", "dried", "సొంఠి", "dry_spice",
     [("Local", "లోకల్")],
     [("FAQ", "Fair Average Quality", {"max_moisture_pct": 10})]),
    ("spices", "Mustard", "dried_seed", "ఆవాలు", "dry_spice",
     [("Yellow", "పసుపు ఆవాలు")],
     [("FAQ", "Fair Average Quality", {"max_moisture_pct": 8})]),
]


# Minimum order quantity (kg) by category — the locked pilot MOQ rules.
_MOQ_BY_CATEGORY = {
    "rice": 25, "paddy": 25, "cereals": 25,
    "pulses": 10, "oilseeds": 10,
    "spices": 5, "vegetables": 2, "fruits": 2,
}


def seed_catalog(db: Session) -> dict:
    out = {}
    for category, name, form, name_te, hc, varieties, grades in _CATALOG:
        moq = _MOQ_BY_CATEGORY.get(category, 5)
        c, created = _get_or_create(
            db, Commodity, category=category, name=name, product_form=form,
            defaults={"name_te": name_te, "unit": "kg", "handling_class": hc,
                      "min_order_qty": D(moq)},
        )
        # Backfill MOQ for commodities seeded before this column existed.
        if not created and (c.min_order_qty is None or D(c.min_order_qty) == D(0)):
            c.min_order_qty = D(moq)
        for vname, vte in varieties:
            _get_or_create(db, Variety, commodity_id=c.id, name=vname, defaults={"name_te": vte})
        for code, label, attrs in grades:
            _get_or_create(db, GradeSpec, commodity_id=c.id, code=code,
                           defaults={"label": label, "attributes": attrs})
        out[name] = c
    # legacy keys used elsewhere in seeding
    out.update(paddy=out["Paddy"], rice=out["Milled Rice"],
               toor=out["Toor Dal"], chilli=out["Red Chilli"])
    return out


def seed_listings(db: Session, catalog: dict, mandals: dict) -> int:
    """A spread of OPEN demo listings across commodities, mandals and farmers —
    multiple test rows for the marketplace. Idempotent."""
    import itertools

    farmer_defs = [
        ("919000000011", "Sita (Farmer)", "Tenali", "Kolakaluru"),
        ("919000000012", "Ramana (Farmer)", "Mangalagiri", "Nidamarru"),
        ("919000000013", "Anjali (Farmer)", "Gudivada", "Pedana"),
        ("919000000014", "Venkat (Farmer)", "Miryalaguda", "Vemulapalli"),
        ("919000000015", "Prasad (Farmer)", "Huzurabad", "Jammikunta"),
    ]
    farmers = []
    for phone, name, mandal_name, village in farmer_defs:
        u, _ = _get_or_create(db, User, phone=phone,
                              defaults={"name": name, "role": str(Role.FARMER),
                                        "onboarding_complete": True})
        m = mandals.get(mandal_name)
        if not db.scalar(select(FarmerProfile).where(FarmerProfile.user_id == u.id)):
            db.add(FarmerProfile(user_id=u.id, mandal_id=m.id if m else None,
                                 village=village, verification_status="verified"))
        farmers.append((u, m))
    db.flush()

    def first(model, cid):
        return db.scalar(select(model).where(model.commodity_id == cid))

    # (commodity name, qty kg, price/kg, claim). Several farmers list the SAME
    # product so the product page shows multiple offerings from multiple places.
    listing_defs = [
        # Paddy — 4 farmers, 4 mandals, different prices (one sold out).
        ("Paddy", 20000, 22.5, "conventional"),
        ("Paddy", 15000, 23.0, "conventional"),
        ("Paddy", 8000, 24.0, "organic"),
        ("Paddy", 12000, 22.0, "conventional"),
        # Red Chilli — 3 farmers/places.
        ("Red Chilli", 6000, 185.0, "conventional"),
        ("Red Chilli", 3000, 240.0, "organic"),
        ("Red Chilli", 4500, 178.0, "conventional"),
        # Turmeric — 3 farmers/places.
        ("Turmeric", 4000, 92.0, "conventional"),
        ("Turmeric", 2500, 112.0, "organic"),
        ("Turmeric", 3200, 98.0, "conventional"),
        # Toor Dal — 2 farmers/places.
        ("Toor Dal", 5000, 98.0, "conventional"),
        ("Toor Dal", 3500, 104.0, "conventional"),
        # Singles for breadth.
        ("Black Pepper", 800, 520.0, "conventional"),
        ("Coriander Seed", 3500, 95.0, "conventional"),
        ("Cumin Seed", 1200, 290.0, "conventional"),
        ("Dry Ginger", 1500, 140.0, "conventional"),
        ("Tamarind", 2000, 85.0, "conventional"),
        ("Groundnut", 8000, 68.0, "conventional"),
        ("Green Gram", 4000, 86.0, "conventional"),
        ("Maize", 10000, 21.0, "conventional"),
    ]
    agent = db.scalar(select(User).where(User.phone == "919000000002"))
    fcycle = itertools.cycle(farmers)
    created = 0
    for i, (cname, qty, price, claim) in enumerate(listing_defs):
        c = catalog.get(cname)
        if not c:
            continue
        u, m = next(fcycle)
        if db.scalar(select(Listing).where(Listing.seller_id == u.id,
                                           Listing.commodity_id == c.id,
                                           Listing.asking_price == D(price))):
            continue
        v = first(Variety, c.id)
        g = first(GradeSpec, c.id)
        evidence = {"certificate_no": f"NPOP-DEMO-{i}", "scope": "organic"} if claim == "organic" else None
        # Every fourth listing is sold out, to demonstrate the out-of-stock state.
        sold_out = (i % 4 == 3)
        # Most listings are agent-verified at the farm gate (skip every 3rd).
        verified = (i % 3 != 2)
        slug = cname.lower().replace(" ", "-")
        spec = (
            f"{'Certified/claimed organic. ' if claim == 'organic' else ''}"
            f"Moisture within {g.attributes.get('max_moisture_pct', 12) if g and g.attributes else 12}%. "
            "Well dried, cleaned and sorted; machine-filled bags of 25-50 kg; single filling, current season."
        )
        lst = Listing(
            seller_id=u.id, commodity_id=c.id,
            variety_id=v.id if v else None, grade_spec_id=g.id if g else None,
            total_qty=D(qty), reserved_qty=D(0),
            sold_qty=D(qty) if sold_out else D(0),
            min_order_qty=D(round(qty * 0.05, 3)),
            asking_price=D(price), negotiable=True, claim_status=claim, claim_evidence=evidence,
            mandal_id=m.id if m else None,
            status=str(ListingStatus.SOLD_OUT if sold_out else ListingStatus.OPEN),
            pickup_terms="Farm-gate pickup; bags included.", harvest_year=2026,
            specifications=spec,
            agent_verified=verified,
            verified_by=agent.id if (verified and agent) else None,
            verified_at=utcnow() if verified else None,
            verification_note=(
                "Farm-gate visual check done: representative sample weighed on a calibrated "
                "scale, moisture spot-checked, grade and cleanliness consistent with the listing."
            ) if verified else None,
        )
        db.add(lst)
        db.flush()
        # Attach 3 sample images (placeholders rendered by /media/file/sample/...).
        for n in range(1, 4):
            db.add(ListingMedia(listing_id=lst.id, object_key=f"sample/{slug}-{n}.svg",
                                media_type="image", access_class="public"))
        created += 1
    db.flush()
    return created


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
    existing = db.scalar(select(PricingRule).where(PricingRule.status == "published"))
    if existing:
        # Keep the pilot rule aligned with the locked commercial rules: the
        # platform's cut is a 0.7% seller commission, and the buyer pays logistics
        # (no separate buyer service fee in the pilot).
        if D(existing.seller_commission_pct) == D(0) and D(existing.service_fee_pct) != D(0):
            existing.seller_commission_pct = 0.7
            existing.service_fee_pct = 0.0
            existing.reason = "Pilot tariff — 0.7% seller commission, buyer-paid logistics"
        return
    rule = PricingRule(
        version=1, status="published", handling_class=None, currency="INR",
        rate_per_kg=0.80, rate_per_km=12.0, fixed_pickup_fee=150, min_transport_charge=300,
        max_transport_charge=None, seller_commission_pct=0.7, service_fee_pct=0.0,
        service_fee_flat=0, service_fee_payer="buyer", inspection_fee=300, packing_fee=500,
        tax_pct=0, effective_from=utcnow(),
        reason="Pilot tariff — 0.7% seller commission, buyer-paid logistics",
    )
    db.add(rule)


_PLANS = [
    # (code, name, name_te, audience, price, period_days, sort, benefits)
    ("farmer_free", "Basic", "బేసిక్", "farmer", 0, 30, 0, {
        "max_active_listings": 3, "fee_discount_pct": 0, "featured_listings": 0,
        "advisory_full": False, "priority_support": False, "rfq_boost": False,
    }),
    ("farmer_grow", "Grow", "గ్రో", "farmer", 199, 30, 1, {
        "max_active_listings": 15, "fee_discount_pct": 10, "featured_listings": 2,
        "advisory_full": True, "priority_support": False, "rfq_boost": True,
    }),
    ("farmer_pro", "Pro", "ప్రో", "farmer", 499, 30, 2, {
        "max_active_listings": 100, "fee_discount_pct": 25, "featured_listings": 10,
        "advisory_full": True, "priority_support": True, "rfq_boost": True,
    }),
    ("buyer_free", "Basic", "బేసిక్", "buyer", 0, 30, 0, {
        "max_active_rfqs": 3, "fee_discount_pct": 0, "advisory_full": False,
        "priority_support": False, "rfq_boost": False,
    }),
    ("buyer_trade", "Trade", "ట్రేడ్", "buyer", 299, 30, 1, {
        "max_active_rfqs": 20, "fee_discount_pct": 10, "advisory_full": True,
        "priority_support": False, "rfq_boost": True,
    }),
    ("buyer_enterprise", "Enterprise", "ఎంటర్‌ప్రైజ్", "buyer", 999, 30, 2, {
        "max_active_rfqs": 200, "fee_discount_pct": 20, "advisory_full": True,
        "priority_support": True, "rfq_boost": True,
    }),
]


def seed_subscription_plans(db: Session) -> int:
    for code, name, name_te, audience, price, period, sort, benefits in _PLANS:
        _get_or_create(
            db, SubscriptionPlan, code=code,
            defaults={
                "name": name, "name_te": name_te, "audience": audience,
                "price": D(price), "period_days": period, "sort": sort,
                "benefits": benefits, "active": True,
            },
        )
    return len(_PLANS)


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


def seed_carriers(db: Session) -> int:
    from app.models.carrier import Carrier

    carriers = [
        ("Krishna Logistics", "KRL", "919500000001",
         ["bike", "auto", "mini_truck"], ["Guntur", "Krishna"], "verified"),
        ("Deccan Freight", "DEC", "919500000002",
         ["mini_truck", "truck"], ["Nalgonda", "Karimnagar", "Hyderabad"], "verified"),
        ("AgriMove Couriers", "AGM", "919500000003",
         ["bike", "auto"], ["Guntur"], "pending"),
    ]
    n = 0
    for name, code, phone, vclasses, areas, kyc in carriers:
        _, created = _get_or_create(
            db, Carrier, code=code,
            defaults={"name": name, "contact_phone": phone, "vehicle_classes": vclasses,
                      "service_areas": areas, "kyc_status": kyc, "active": True},
        )
        n += 1
    return n


def seed_demo_activity(db: Session, catalog: dict, mandals: dict) -> int:
    """Open offers + RFQs (and a listing for the primary demo farmer) so the
    role dashboards show real numbers out of the box. Idempotent — skips once
    any offer exists."""
    from datetime import timedelta

    from sqlalchemy import func

    from app.models.common import OfferStatus, RFQStatus
    from app.models.marketplace import Offer, OfferVersion, RFQ, Watch

    if db.scalar(select(func.count(Offer.id))):
        return 0

    buyer = db.scalar(select(User).where(User.phone == "919000000004"))
    ravi = db.scalar(select(User).where(User.phone == "919000000003"))
    if not buyer:
        return 0

    created = 0

    # Give the primary demo farmer (Ravi) an open listing so his seller
    # dashboard shows an active listing + an incoming negotiation.
    ravi_listing = None
    if ravi:
        paddy = catalog.get("Paddy")
        ravi_listing = db.scalar(select(Listing).where(Listing.seller_id == ravi.id))
        if paddy and ravi_listing is None:
            v = db.scalar(select(Variety).where(Variety.commodity_id == paddy.id))
            g = db.scalar(select(GradeSpec).where(GradeSpec.commodity_id == paddy.id))
            tenali = mandals.get("Tenali")
            ravi_listing = Listing(
                seller_id=ravi.id, commodity_id=paddy.id,
                variety_id=v.id if v else None, grade_spec_id=g.id if g else None,
                total_qty=D(10000), reserved_qty=D(0), sold_qty=D(0),
                min_order_qty=D(500), asking_price=D(23.5), negotiable=True,
                claim_status="conventional", mandal_id=tenali.id if tenali else None,
                status=str(ListingStatus.OPEN), pickup_terms="Farm-gate pickup.",
                harvest_year=2026, specifications="Well dried, cleaned, 25-50kg bags.",
                agent_verified=False,
            )
            db.add(ravi_listing)
            db.flush()
            for n in range(1, 4):
                db.add(ListingMedia(listing_id=ravi_listing.id, object_key=f"sample/paddy-{n}.svg",
                                    media_type="image", access_class="public"))

    # Open offers from the demo buyer: one on Ravi's listing, two on others.
    targets = []
    if ravi_listing is not None:
        targets.append(ravi_listing)
    others = db.scalars(
        select(Listing).where(Listing.status == "open", Listing.seller_id != buyer.id)
        .order_by(Listing.id).limit(6)
    ).all()
    for lst in others:
        if ravi_listing is None or lst.id != ravi_listing.id:
            targets.append(lst)
        if len(targets) >= 3:
            break

    exp = utcnow() + timedelta(days=3)
    for lst in targets[:3]:
        off = Offer(listing_id=lst.id, buyer_id=buyer.id, seller_id=lst.seller_id,
                    status=str(OfferStatus.OPEN))
        db.add(off)
        db.flush()
        qty = float(lst.min_order_qty) or 500.0
        db.add(OfferVersion(
            offer_id=off.id, version_no=1, proposer_role="buyer", proposer_id=buyer.id,
            price_per_unit=D(round(float(lst.asking_price) * 0.96, 2)), quantity=D(qty),
            unit="kg", grade_spec_id=lst.grade_spec_id, expires_at=exp, created_at=utcnow(),
        ))
        created += 1

    # A couple of open RFQs so the buyer's "Open requests" is non-zero.
    for cname, qty, tp in [("Turmeric", 2000, 95.0), ("Groundnut", 5000, 66.0)]:
        c = catalog.get(cname)
        if c:
            db.add(RFQ(buyer_id=buyer.id, commodity_id=c.id, requested_qty=D(qty),
                       unit="kg", target_price=D(tp), status=str(RFQStatus.OPEN),
                       inspection_required=True))
            created += 1

    db.flush()
    return created


def seed_demo_watches(db: Session, catalog: dict) -> int:
    """Demo buyer watches a couple of products (one with a price-alert target).
    Idempotent per watch, so it runs even when offers already exist."""
    from app.models.marketplace import Watch

    buyer = db.scalar(select(User).where(User.phone == "919000000004"))
    if not buyer:
        return 0
    n = 0
    for cname, tgt in [("Paddy", 23.0), ("Turmeric", None)]:
        c = catalog.get(cname)
        if c and not db.scalar(select(Watch).where(Watch.user_id == buyer.id, Watch.commodity_id == c.id)):
            db.add(Watch(user_id=buyer.id, commodity_id=c.id, target_price=D(tgt) if tgt else None))
            n += 1
    db.flush()
    return n


def seed_demo_fpo(db: Session, mandals: dict) -> int:
    """A demo FPO lead with its own organisation and two member farmers, so the
    group console shows a populated roster + pooled listings. Idempotent."""
    from app.models.user import Organisation

    lead = db.scalar(select(User).where(User.phone == "919000000008"))
    created = 0
    tenali = mandals.get("Tenali")
    if lead is None:
        lead = User(phone="919000000008", name="Green Valley FPO",
                    role=str(Role.FPO), onboarding_complete=True)
        db.add(lead)
        db.flush()
        db.add(FarmerProfile(user_id=lead.id, mandal_id=tenali.id if tenali else None,
                             village="Kolakaluru", verification_status="verified"))
        created += 1
    if lead.organisation_id is None:
        org = Organisation(type="fpo", legal_name="Green Valley Farmer Producer Co.",
                           verification_status="verified")
        db.add(org)
        db.flush()
        lead.organisation_id = org.id
    # Fold two demo farmers (from seed_listings) into the group if they are free.
    for phone in ("919000000011", "919000000012"):
        m = db.scalar(select(User).where(User.phone == phone))
        if m and m.organisation_id is None:
            m.organisation_id = lead.organisation_id
            created += 1
    db.flush()
    return created


def main() -> None:
    run_migrations()
    db = SessionLocal()
    try:
        mandals = seed_locations(db)
        catalog = seed_catalog(db)
        seed_users(db, mandals)
        n_listings = seed_listings(db, catalog, mandals)
        seed_pricing(db)
        n_plans = seed_subscription_plans(db)
        n_carriers = seed_carriers(db)
        seed_advisory(db)
        seed_insights(db, mandals)
        seed_demo_fpo(db, mandals)
        n_activity = seed_demo_activity(db, catalog, mandals)
        n_activity += seed_demo_watches(db, catalog)
        db.commit()
        print(f"Seeded locations, catalog ({len(catalog) - 4} commodities), demo users, "
              f"{n_listings} listings, pricing, {n_plans} subscription plans, "
              f"{n_carriers} couriers, advisory + insights, {n_activity} demo offers/RFQs.")
        print(f"Superadmin phone: {settings.superadmin_phone} (dev OTP: {settings.master_otp})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
