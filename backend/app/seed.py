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
        ("919000000001", "Field Leader (Mandal)", Role.FIELD_LEADER),
        ("919000000002", "Field Agent", Role.FIELD_AGENT),
        ("919000000003", "Ravi (Farmer)", Role.FARMER),
        ("919000000004", "Lakshmi Traders", Role.BUYER_BUSINESS),
        ("919000000005", "Transport Co", Role.TRANSPORT),
        ("919000000006", "Field Manager (District)", Role.FIELD_MANAGER),
        ("919000000009", "Household Buyer", Role.BUYER_HOUSEHOLD),
    ]
    from app.core.security import hash_password

    # Shared demo password so every seeded account can use phone+password login
    # in dev/sandbox (never seeded in production — these are demo users only).
    demo_pw = hash_password("demo1234")
    users = {}
    for phone, name, role in defs:
        first = name.split(" ", 1)[0]
        last = name.split(" ", 1)[1] if " " in name else None
        u, created = _get_or_create(db, User, phone=phone,
                                    defaults={"name": name, "role": str(role),
                                              "first_name": first, "last_name": last,
                                              "password_hash": demo_pw,
                                              "onboarding_complete": True})
        if not created:
            # Keep demo accounts aligned with the current role set (the pivot
            # renamed/removed several roles).
            u.role = str(role)
            u.name = name
            if not u.first_name:
                u.first_name = first
                u.last_name = last
            if not u.password_hash:
                u.password_hash = demo_pw
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
    # Demo payout accounts, both awaiting verification so the admin verify queue
    # has something to act on (one UPI, one bank).
    from app.models.account import PayoutAccount
    transport_u = users[Role.TRANSPORT]
    if not db.scalar(select(PayoutAccount).where(PayoutAccount.user_id == farmer.id)):
        db.add(PayoutAccount(user_id=farmer.id, method="upi", upi_id="ravi@okaxis", verified=False))
    if not db.scalar(select(PayoutAccount).where(PayoutAccount.user_id == transport_u.id)):
        db.add(PayoutAccount(user_id=transport_u.id, method="bank", account_name="Transport Co",
                             account_number="123456789012", ifsc="HDFC0001234", verified=False))
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
    from app.models.marketplace import Offer, OfferVersion, RFQ

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


def seed_demo_reviews(db: Session, catalog: dict) -> int:
    """A few buyer reviews of demo farmers so seller ratings are visible at the
    browse/decision stage (product cards, discovery, product detail). Each review
    is anchored to a minimal SETTLED demo order (reviews require a delivered order).
    Idempotent — skips once any review exists."""
    from sqlalchemy import func

    from app.models.common import OrderStatus
    from app.models.order import Order
    from app.models.review import Review

    if db.scalar(select(func.count(Review.id))):
        return 0

    buyer = db.scalar(select(User).where(User.phone == "919000000004"))
    if not buyer:
        return 0

    # Reviewed sellers: distinct demo farmers who have an open listing, spread
    # across different commodities so several product cards light up.
    open_listings = db.scalars(
        select(Listing).where(Listing.status == str(ListingStatus.OPEN),
                              Listing.seller_id != buyer.id)
        .order_by(Listing.id)
    ).all()
    picks: list[Listing] = []
    seen_sellers: set[int] = set()
    seen_commodities: set[int] = set()
    for l in open_listings:
        if l.seller_id in seen_sellers:
            continue
        # Prefer variety of commodity, but still allow repeats once we run low.
        if l.commodity_id in seen_commodities and len(picks) < 4:
            continue
        picks.append(l)
        seen_sellers.add(l.seller_id)
        seen_commodities.add(l.commodity_id)
        if len(picks) >= 5:
            break

    ratings = [
        (5, "Clean, well-dried grain exactly as described. Smooth pickup."),
        (4, "Good quality and fair weight. Packaging could be tighter."),
        (5, "Reliable farmer — second time buying, consistent produce."),
        (4, "Quantity matched the order; a little moisture but acceptable."),
        (5, "Excellent lot, agent-verified and delivered on time."),
    ]

    created = 0
    for i, l in enumerate(picks):
        rating, comment = ratings[i % len(ratings)]
        moq = float(l.min_order_qty) or 500.0
        order = Order(
            public_id=f"ODREV{l.seller_id}",
            buyer_id=buyer.id,
            seller_id=l.seller_id,
            status=str(OrderStatus.SETTLED),
            accepted_terms={
                "commodity_id": l.commodity_id,
                "mandal_id": l.mandal_id,
                "price_per_unit": float(l.asking_price),
                "quantity": moq,
            },
            buyer_total=D(round(float(l.asking_price) * moq, 2)),
            seller_payable=D(round(float(l.asking_price) * moq * 0.993, 2)),
        )
        db.add(order)
        db.flush()
        db.add(Review(author_id=buyer.id, order_id=order.id, subject_type="farmer",
                      subject_id=l.seller_id, rating=rating, comment=comment))
        created += 1

    db.flush()
    return created


def seed_prices(db: Session) -> int:
    """Today's government-declared mandi prices across India, product-wise, so a
    farmer or buyer can see the official price everywhere. Idempotent (skips if
    any price exists). Sample data — wire a live AGMARKNET/data.gov.in feed later."""
    from sqlalchemy import func

    from app.models.prices import MarketPrice

    if db.scalar(select(func.count(MarketPrice.id))):
        return 0

    as_of = "2026-11-10"
    src, url = "AGMARKNET (sample)", "https://agmarknet.gov.in/"
    # (state, market, commodity, variety, min, max, modal)  prices in ₹/qtl
    rows = [
        ("Andhra Pradesh", "Guntur", "Paddy", "BPT 5204", 2100, 2450, 2300),
        ("Telangana", "Karimnagar", "Paddy", "MTU 1010", 2050, 2400, 2250),
        ("Punjab", "Ludhiana", "Paddy", "PR 126", 2150, 2500, 2320),
        ("West Bengal", "Barddhaman", "Paddy", "Swarna", 1980, 2300, 2180),
        ("Tamil Nadu", "Thanjavur", "Paddy", "ADT 43", 2000, 2350, 2200),
        ("Andhra Pradesh", "Guntur", "Red Chilli", "Teja", 17000, 21000, 19000),
        ("Telangana", "Khammam", "Red Chilli", "Teja", 16500, 20500, 18500),
        ("Karnataka", "Byadgi", "Red Chilli", "Byadgi", 24000, 42000, 33000),
        ("Madhya Pradesh", "Indore", "Groundnut", "Bold", 6000, 7200, 6600),
        ("Gujarat", "Rajkot", "Groundnut", "Java", 6200, 7500, 6800),
        ("Andhra Pradesh", "Anantapur", "Groundnut", "TMV-2", 5800, 7000, 6400),
        ("Telangana", "Nizamabad", "Turmeric", "Finger", 12000, 15500, 13800),
        ("Maharashtra", "Sangli", "Turmeric", "Rajapuri", 11500, 16000, 13500),
        ("Tamil Nadu", "Erode", "Turmeric", "Erode", 12500, 16500, 14200),
        ("Maharashtra", "Latur", "Toor Dal", None, 9000, 10800, 9900),
        ("Karnataka", "Kalaburagi", "Toor Dal", None, 8800, 10500, 9700),
        ("Telangana", "Tandur", "Toor Dal", None, 9100, 10900, 10000),
        ("Madhya Pradesh", "Indore", "Maize", None, 1900, 2250, 2050),
        ("Bihar", "Gulabbagh", "Maize", None, 1850, 2150, 1980),
        ("Karnataka", "Davangere", "Maize", None, 1950, 2300, 2100),
    ]
    n = 0
    for state, market, commodity, variety, lo, hi, modal in rows:
        db.add(MarketPrice(
            state=state, market=market, commodity=commodity, variety=variety,
            min_price=lo, max_price=hi, modal_price=modal, unit="₹/qtl",
            arrivals="moderate", as_of=as_of, source_name=src, source_url=url,
        ))
        n += 1
    db.flush()
    return n


def main() -> None:
    run_migrations()
    db = SessionLocal()
    try:
        mandals = seed_locations(db)
        catalog = seed_catalog(db)
        seed_users(db, mandals)
        n_listings = seed_listings(db, catalog, mandals)
        seed_pricing(db)
        n_carriers = seed_carriers(db)
        n_prices = seed_prices(db)
        n_activity = seed_demo_activity(db, catalog, mandals)
        n_reviews = seed_demo_reviews(db, catalog)
        db.commit()
        print(f"Seeded locations, catalog ({len(catalog) - 4} commodities), demo users, "
              f"{n_listings} listings, pricing, {n_carriers} couriers, "
              f"{n_prices} market prices, {n_activity} demo offers/RFQs, "
              f"{n_reviews} demo reviews.")
        print(f"Superadmin phone: {settings.superadmin_phone} (dev OTP: {settings.master_otp})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
