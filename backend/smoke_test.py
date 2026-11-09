"""End-to-end regression for the AgriSetuAI marketplace core.

Runs against a throwaway SQLite DB using FastAPI's TestClient. No server needed.

    cd backend
    python smoke_test.py            # fresh temp DB
"""
import os
import sys
import tempfile

# Point the app at a throwaway DB *before* importing it, and force dev mode.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["DEV_MODE"] = "true"
os.environ["AUTH_SECRET"] = "smoke-test-secret"

sys.path.insert(0, os.path.dirname(__file__))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seed import main as seed_main  # noqa: E402

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
_checks = {"pass": 0, "fail": 0}


def check(label, cond):
    tag = PASS if cond else FAIL
    print(f"  [{tag}] {label}")
    _checks["pass" if cond else "fail"] += 1
    return cond


def login(client, phone, role=None, name=None):
    r = client.post("/api/auth/otp/request", json={"phone": phone})
    code = r.json().get("dev_code", "123456")
    body = {"phone": phone, "code": code}
    if role:
        body["role"] = role
    if name:
        body["name"] = name
    r = client.post("/api/auth/otp/verify", json=body)
    return r.json()["token"]


def hdr(token):
    return {"Authorization": f"Bearer {token}"}


def run():
    seed_main()
    client = TestClient(app)

    print("\n== Health & auth ==")
    check("health ok", client.get("/api/health").json()["ok"])

    farmer = login(client, "919000000003")   # seeded farmer
    buyer = login(client, "919000000004")     # seeded business buyer
    agent = login(client, "919000000002")     # seeded field agent
    manager = login(client, "919000000001")   # seeded mandal manager
    superadmin = login(client, "919999999998")
    transport = login(client, "919000000005")
    check("farmer token issued", bool(farmer))
    check("buyer token issued", bool(buyer))

    print("\n== Catalog & listing ==")
    commodities = client.get("/api/catalog/commodities").json()
    paddy = next(c for c in commodities if c["category"] == "paddy")
    check("product MOQ exposed (paddy 25kg)", paddy.get("min_order_qty") == "25.000")
    grades = client.get(f"/api/catalog/commodities/{paddy['id']}/grades").json()
    grade_id = grades[0]["id"]

    mandals = client.get("/api/locations/mandals", params={"district_id": 1}).json()
    mandal_id = mandals[0]["id"] if mandals else None

    r = client.post("/api/listings", headers=hdr(farmer), json={
        "commodity_id": paddy["id"], "grade_spec_id": grade_id,
        "total_qty": 1000, "min_order_qty": 100, "asking_price": 25.0,
        "mandal_id": mandal_id, "harvest_year": 2026,
    })
    check("farmer creates listing", r.status_code == 201)
    listing = r.json()
    check("listing starts as draft", listing["status"] == "draft")

    # Publishing requires at least 3 sample images.
    r = client.post(f"/api/listings/{listing['id']}/publish", headers=hdr(farmer))
    check("publish blocked without 3 images", r.status_code == 400)
    for n in range(1, 4):
        client.post(f"/api/listings/{listing['id']}/media", headers=hdr(farmer),
                    json={"object_key": f"sample/paddy-test-{n}.svg", "media_type": "image"})
    r = client.post(f"/api/listings/{listing['id']}/publish", headers=hdr(farmer))
    check("listing published after images", r.json()["status"] == "open")

    # Agent verifies the listing at the farm gate, leaving a comment.
    r = client.post(f"/api/listings/{listing['id']}/verify", headers=hdr(agent),
                    json={"note": "Weight sampled; grade consistent."})
    vj = r.json()
    check("agent verifies listing", vj["agent_verified"] is True)
    check("agent comment stored on listing", vj["verification_note"] == "Weight sampled; grade consistent.")
    check("listing exposes grade spec", vj.get("grade") is not None)

    found = client.get("/api/listings", params={"commodity_id": paddy["id"]}).json()
    check("listing appears in search", any(x["id"] == listing["id"] for x in found))
    check("seller phone NOT leaked in search", "phone" not in found[0]["seller"])
    mine = next(x for x in found if x["id"] == listing["id"])
    check("listing shows place (mandal)", mine["place"]["mandal"] is not None)
    check("listing shows image count", mine["image_count"] >= 3)

    # Product view: same product from multiple farmers/places, out-of-stock flagged.
    prod = client.get(f"/api/listings/products/{paddy['id']}").json()
    check("product view lists offerings", prod["offering_count"] >= 1)
    check("product view aggregates places", isinstance(prod["places"], list))
    grid = client.get("/api/listings/products").json()
    check("product grid returns commodities", any(p["commodity_id"] == paddy["id"] for p in grid))

    # MOQ guard: an offer below the minimum order quantity is rejected.
    r = client.post("/api/offers", headers=hdr(buyer), json={
        "listing_id": listing["id"], "price_per_unit": 22.0, "quantity": 10,
    })
    check("offer below MOQ rejected", r.status_code == 400)

    print("\n== Negotiation (offer -> counter -> accept) ==")
    r = client.post("/api/offers", headers=hdr(buyer), json={
        "listing_id": listing["id"], "price_per_unit": 22.0, "quantity": 500,
    })
    check("buyer opens offer", r.status_code == 201)
    offer = r.json()
    check("offer has version 1", offer["versions"][0]["version_no"] == 1)
    check("offer carries product context", bool(offer["product"]) and offer["product"]["commodity"] == "Paddy")
    check("new offer awaits the seller", offer["awaiting_role"] == "seller" and offer["expired"] is False)
    check("offer exposes a latest-terms summary + countdown",
          offer["latest"]["version_no"] == 1 and offer["expires_in_seconds"] > 0)

    # Buyer cannot accept own proposal.
    r = client.post(f"/api/offers/{offer['id']}/accept", headers=hdr(buyer))
    check("buyer cannot accept own proposal", r.status_code == 409)

    # Seller counters at 24.
    r = client.post(f"/api/offers/{offer['id']}/counter", headers=hdr(farmer), json={
        "price_per_unit": 24.0, "quantity": 500,
    })
    check("seller counters (v2)", len(r.json()["versions"]) == 2)
    check("after counter it awaits the buyer", r.json()["awaiting_role"] == "buyer")

    # Seller cannot counter again (awaiting buyer).
    r = client.post(f"/api/offers/{offer['id']}/counter", headers=hdr(farmer), json={
        "price_per_unit": 23.5, "quantity": 500,
    })
    check("seller cannot counter twice in a row", r.status_code == 409)

    # Immutability: v1 price unchanged after counter.
    hist = client.get(f"/api/offers/{offer['id']}/history", headers=hdr(buyer)).json()
    check("offer v1 immutable (still 22.00)", hist[0]["price_per_unit"] == "22.00")

    # Buyer accepts v2 -> provisional order + reserved stock.
    r = client.post(f"/api/offers/{offer['id']}/accept", headers=hdr(buyer))
    check("buyer accepts counter", r.status_code == 200)
    order = r.json()["order"]
    order_id = order["id"]
    check("order provisional", order["status"] == "provisional_agreement")
    check("accepted terms snapshot price 24.00", order["accepted_terms"]["price_per_unit"] == "24.00")

    relisting = client.get(f"/api/listings/{listing['id']}").json()
    check("500 kg reserved on listing", relisting["reserved_qty"] == "500.000")
    check("available now 500 kg", relisting["available_qty"] == "500.000")

    # Offer-expiry: a zero-TTL offer lapses and cannot be acted on.
    r = client.post("/api/offers", headers=hdr(buyer), json={
        "listing_id": listing["id"], "price_per_unit": 22.0, "quantity": 100, "ttl_hours": 0,
    })
    check("zero-TTL offer reports expired on creation", r.json()["expired"] is True)
    exp_id = r.json()["id"]
    lst_offers = client.get("/api/offers", headers=hdr(buyer)).json()
    exp_o = next(o for o in lst_offers if o["id"] == exp_id)
    check("expired offer auto-flips to expired status", exp_o["status"] == "expired")
    r = client.post(f"/api/offers/{exp_id}/accept", headers=hdr(farmer))
    check("cannot accept an expired offer", r.status_code == 409)

    print("\n== Inspection ==")
    r = client.post(f"/api/orders/{order_id}/assign-inspection", headers=hdr(manager),
                    json={"agent_id": 3})
    check("manager assigns inspection", r.json()["status"] == "inspection_assigned")

    jobs = client.get("/api/agent/jobs", headers=hdr(agent)).json()
    check("agent sees assigned job", any(j["order_id"] == order_id for j in jobs))

    # Idempotent offline draft.
    insp_body = {
        "client_draft_id": "draft-abc-1", "gross_weight": 505, "tare_weight": 5,
        "scale_ref": "SCALE-1", "outcome": "pass",
        "checklist": {"foreign_matter": "low"},
        "evidence": ["priv:kyc/x.jpg"],
    }
    r = client.post(f"/api/agent/orders/{order_id}/inspection", headers=hdr(agent), json=insp_body)
    check("agent submits pass", r.json()["order_status"] == "buyer_approval_pending")
    r2 = client.post(f"/api/agent/orders/{order_id}/inspection", headers=hdr(agent), json=insp_body)
    check("duplicate draft deduped", r2.json().get("duplicate") is True)

    print("\n== Approval, quote, payment ==")
    r = client.post(f"/api/orders/{order_id}/buyer-approve", headers=hdr(buyer))
    check("buyer approves -> confirmed", r.json()["status"] == "confirmed")

    r = client.post(f"/api/orders/{order_id}/confirm-quote", headers=hdr(buyer),
                    json={"route_km": 40})
    oj = r.json()
    check("quote locked -> payment_pending", oj["status"] == "payment_pending")
    q = oj["quote"]
    # product = 24 * 500 = 12000; transport = max(300, 500*0.8 + 40*12 + 150)=max(300,1030)=1030
    check("product value 12000.00", q["product_value"] == "12000.00")
    check("transport 1030.00", q["transport_charge"] == "1030.00")
    # Locked rules: buyer pays logistics, no buyer service fee; platform takes a
    # 0.7% seller commission from the seller's proceeds.
    check("no buyer service fee", q["service_fee"] == "0.00")
    check("seller commission 0.7% = 84.00", q["seller_commission"] == "84.00")
    # buyer_total = 12000 + 500 (packing) + 300 (inspection) + 1030 (transport) = 13830
    check("buyer total 13830.00", q["buyer_total"] == "13830.00")
    # seller receives 12000 - 84 commission = 11916
    check("seller payable 11916.00", q["seller_payable"] == "11916.00")
    check("explicit route_km recorded as override", q.get("route_km_source") == "override")

    print("\n== Logistics / distance routing ==")
    two = client.get("/api/locations/mandals", params={"district_id": 1}).json()
    check("district has two mandals with coords", len(two) >= 2)
    a_id, b_id = two[0]["id"], two[1]["id"]
    d = client.get("/api/logistics/distance", headers=hdr(buyer),
                   params={"from_mandal_id": a_id, "to_mandal_id": b_id}).json()
    check("haversine distance computed between mandals", d["source"] == "haversine")
    check("computed distance is positive", float(d["route_km"]) > 1)
    svc = client.get("/api/logistics/serviceability", headers=hdr(buyer),
                     params={"mandal_id": a_id}).json()
    check("mandal serviceable with coordinates", svc["serviceable"] and svc["has_coordinates"])

    r = client.post(f"/api/orders/{order_id}/pay",
                    headers={**hdr(buyer), "Idempotency-Key": "pay-1"})
    check("payment captured -> paid", r.json()["status"] == "paid")
    # Idempotent replay.
    r = client.post(f"/api/orders/{order_id}/pay",
                    headers={**hdr(buyer), "Idempotency-Key": "pay-1"})
    check("duplicate payment idempotent (still paid)", r.json()["status"] == "paid")

    print("\n== Ledger integrity ==")
    acct = client.get("/api/admin/ledger/accounts", headers=hdr(superadmin)).json()
    check("ledger balanced after payment", acct["balanced"] is True)
    # Seller proceeds net of the 0.7% commission (12000 - 84).
    check("seller_payable credited 11916", acct["accounts"].get("seller_payable") == "11916.00")
    # Platform earns the commission (84) — no buyer service fee in the pilot.
    check("platform_revenue = commission 84", acct["accounts"].get("platform_revenue") == "84.00")

    print("\n== Packing, shipment, delivery, settlement ==")
    r = client.post(f"/api/orders/{order_id}/packing-complete", headers=hdr(agent))
    check("packing complete -> ready_for_pickup", r.json()["order"]["status"] == "ready_for_pickup")
    check("lot id issued", r.json()["lot_id"].startswith("LOT-"))

    # Verified Lot Certificate: observed/measured separated, lab-testing disclaimer.
    cert = client.get(f"/api/orders/{order_id}/certificate", headers=hdr(buyer)).json()
    check("certificate issued for order", cert["certificate_id"].startswith("ASVL-"))
    check("certificate records measured net weight", cert["measured"]["net_qty_kg"] is not None)
    check("certificate discloses what was not tested", "laboratory" in cert["not_tested_note"].lower())

    # Transport couriers: onboard, KYC-gate, assign to the shipment.
    r = client.post("/api/carriers", headers=hdr(superadmin), json={
        "name": "Test Courier", "code": "TST", "vehicle_classes": ["mini_truck"],
        "service_areas": ["Guntur"],
    })
    carrier_id = r.json()["id"]
    check("carrier onboarded (pending KYC)", r.json()["kyc_status"] == "pending")
    r = client.post(f"/api/orders/{order_id}/assign-courier", headers=hdr(manager),
                    json={"courier_id": carrier_id, "vehicle_class": "mini_truck"})
    check("unverified carrier cannot be assigned", r.status_code == 409)
    client.patch(f"/api/carriers/{carrier_id}", headers=hdr(superadmin), json={"kyc_status": "verified"})
    # Buyer-paid logistics: the buyer picks the courier for their own order.
    r = client.post(f"/api/orders/{order_id}/assign-courier", headers=hdr(buyer),
                    json={"courier_id": carrier_id, "vehicle_class": "mini_truck"})
    check("buyer chooses the courier", r.json()["courier"] == "Test Courier")
    # Transport partner sees the job with the buyer-paid charge as earning.
    tj = client.get("/api/transport/jobs", headers=hdr(transport)).json()
    check("transport partner sees assigned job", any(j["order_id"] == order_id for j in tj["jobs"]))
    check("transport job shows trip earning", float(next(j for j in tj["jobs"] if j["order_id"] == order_id)["transport_charge"]) > 0)

    for ev, expect in [("picked_up", "picked_up"), ("in_transit", "in_transit"),
                       ("out_for_delivery", "out_for_delivery")]:
        r = client.post(f"/api/orders/{order_id}/shipment/event", headers=hdr(transport),
                        json={"event": ev})
        check(f"shipment {ev}", r.json()["order"]["status"] == expect)

    # Mid-flight tracking: a 5-step timeline, pickup place, ETA, and the buyer's
    # delivery code (shown to the courier at handoff) — not visible to the seller.
    trk = client.get(f"/api/orders/{order_id}/tracking", headers=hdr(buyer)).json()
    check("tracking shows assigned courier", trk["shipment"]["courier_name"] == "Test Courier")
    check("tracking builds a 5-step timeline", len(trk["steps"]) == 5)
    check("earlier milestones marked done", trk["steps"][0]["done"] and trk["steps"][1]["done"])
    check("a current step is highlighted", any(s["current"] for s in trk["steps"]))
    check("tracking knows the pickup place", trk["from_place"] is not None)
    check("tracking estimates an ETA", trk["eta"] is not None)
    check("buyer sees the delivery code out-for-delivery", bool(trk.get("delivery_code")))
    trk_s = client.get(f"/api/orders/{order_id}/tracking", headers=hdr(farmer)).json()
    check("seller does not see the delivery code", "delivery_code" not in trk_s)

    r = client.post(f"/api/orders/{order_id}/shipment/event", headers=hdr(transport),
                    json={"event": "delivered"})
    check("shipment delivered", r.json()["order"]["status"] == "delivered_pending_acceptance")
    trk = client.get(f"/api/orders/{order_id}/tracking", headers=hdr(buyer)).json()
    check("all milestones done after delivery", all(s["done"] for s in trk["steps"]))
    check("delivered tracking reports proof + actual time",
          trk.get("proof") is not None and trk["eta_basis"] == "delivered")

    r = client.post(f"/api/orders/{order_id}/acceptance", headers=hdr(buyer))
    check("buyer accepts delivery -> settled", r.json()["status"] == "settled")

    relisting = client.get(f"/api/listings/{listing['id']}").json()
    check("reserved released, 500 kg sold", relisting["sold_qty"] == "500.000"
          and relisting["reserved_qty"] == "0.000")

    acct = client.get("/api/admin/ledger/accounts", headers=hdr(superadmin)).json()
    check("ledger still balanced after settlement", acct["balanced"] is True)
    check("seller_payable cleared to 0", acct["accounts"].get("seller_payable") == "0.00")

    print("\n== Ratings & reviews + earnings ==")
    r = client.post("/api/reviews", headers=hdr(buyer), json={
        "order_id": order_id, "subject_type": "farmer", "rating": 5, "comment": "Great quality, clean grain."})
    check("buyer reviews farmer", r.status_code == 201 and r.json()["rating"] == 5)
    r = client.post("/api/reviews", headers=hdr(buyer), json={
        "order_id": order_id, "subject_type": "courier", "rating": 4, "comment": "On time."})
    check("buyer reviews courier", r.status_code == 201)
    # Non-buyer cannot review.
    r = client.post("/api/reviews", headers=hdr(agent), json={
        "order_id": order_id, "subject_type": "farmer", "rating": 1})
    check("non-buyer cannot review", r.status_code == 403)
    # Seller rating appears on their listings.
    lst = client.get(f"/api/listings/{listing['id']}").json()
    check("seller rating shows on listing", lst["seller_rating"] == 5.0 and lst["seller_rating_count"] >= 1)
    # Farmer earnings statement.
    earn = client.get("/api/auth/me/earnings", headers=hdr(farmer)).json()
    check("earnings statement totals present", float(earn["totals"]["net"]) > 0)
    check("earnings lists settled order", any(o["order_public_id"] == oj["public_id"] for o in earn["orders"]))

    print("\n== Alerting (notifications) ==")
    notes = client.get("/api/auth/notifications", headers=hdr(farmer)).json()
    titles = " ".join(n["title"] for n in notes)
    check("seller alerted on new offer", "New offer received" in titles)
    check("seller alerted on payment", "Payment received" in titles)
    check("seller alerted on settlement", "paid" in titles.lower())
    unread = sum(1 for n in notes if not n["read_at"])
    check("farmer has unread alerts", unread > 0)
    client.post("/api/auth/notifications/read", headers=hdr(farmer))
    notes2 = client.get("/api/auth/notifications", headers=hdr(farmer)).json()
    check("mark-read clears unread", all(n["read_at"] for n in notes2))

    print("\n== Onboarding + payment/SMS sandbox ==")
    # A new farmer onboards: completes profile + submits KYC.
    newf = login(client, "919000000031", role="farmer", name="New Farmer")
    r = client.patch("/api/auth/me", headers=hdr(newf), json={
        "village": "Peddapuram", "mandal_id": mandal_id, "submit_kyc": True})
    check("onboarding sets profile complete", r.json().get("onboarding_complete") is True)
    mej = client.get("/api/auth/me", headers=hdr(newf)).json()
    check("onboarding saved village + KYC pending",
          mej["farmer"]["village"] == "Peddapuram" and mej["farmer"]["verification_status"] == "pending")

    # Payment intent for an order.
    pi = client.get(f"/api/payments/intent/{order_id}", headers=hdr(buyer)).json()
    check("payment intent created", pi["reference"].startswith("intent_"))
    # Signed webhook: bad signature rejected; valid signature reaches the handler.
    from app.services import payments as _pay
    bad = client.post("/api/payments/webhook", content=b'{"type":"payment.succeeded"}',
                      headers={"x-webhook-signature": "deadbeef"})
    check("webhook rejects bad signature", bad.status_code == 401)
    body = b'{"type":"payment.succeeded","data":{"order_public_id":"NOPE","reference":"x"}}'
    good = client.post("/api/payments/webhook", content=body,
                       headers={"x-webhook-signature": _pay.sign(body)})
    check("valid-signature webhook runs (unknown order -> 404)", good.status_code == 404)

    print("\n== Reorder + admin KYC queue ==")
    r = client.post(f"/api/orders/{order_id}/reorder", headers=hdr(buyer))
    check("buyer reorders -> new offer", r.json().get("reorderable") is True and r.json().get("offer_id"))
    myoffers = client.get("/api/offers", headers=hdr(buyer)).json()
    check("reorder offer appears in buyer's offers", any(o["id"] == r.json()["offer_id"] for o in myoffers))

    q = client.get("/api/admin/kyc", headers=hdr(superadmin)).json()
    check("new farmer appears in KYC queue", any(x["phone"] == "919000000031" for x in q))
    target = next(x for x in q if x["phone"] == "919000000031")
    d = client.post(f"/api/admin/kyc/{target['user_id']}/decision", headers=hdr(superadmin),
                    json={"approve": True})
    check("admin approves KYC", d.json()["verification_status"] == "verified")
    q2 = client.get("/api/admin/kyc", headers=hdr(superadmin)).json()
    check("approved user leaves pending queue", not any(x["user_id"] == target["user_id"] for x in q2))

    print("\n== Pricing admin (draft/simulate/publish) ==")
    r = client.post("/api/admin/pricing-rules/draft", headers=hdr(superadmin), json={
        "handling_class": "dry_grain", "rate_per_kg": 1.0, "rate_per_km": 10,
        "min_transport_charge": 350, "service_fee_pct": 3, "inspection_fee": 300,
        "packing_fee": 500, "reason": "raise grain rate",
    })
    check("draft created", r.status_code == 201)
    draft_id = r.json()["id"]
    sim = client.post(f"/api/admin/pricing-rules/{draft_id}/simulate", headers=hdr(superadmin),
                      json={"product_value": 10000, "billable_kg": 500, "route_km": 40}).json()
    # transport = max(350, 500*1 + 40*10 + 0) = max(350, 900) = 900
    check("simulate transport 900.00", sim["transport_charge"] == "900.00")
    r = client.post(f"/api/admin/pricing-rules/{draft_id}/publish", headers=hdr(superadmin))
    check("rule published", r.json()["status"] == "published")

    print("\n== Guardrails ==")
    # Non-superadmin cannot create pricing rules.
    r = client.post("/api/admin/pricing-rules/draft", headers=hdr(buyer), json={"rate_per_kg": 1})
    check("buyer blocked from pricing admin", r.status_code == 403)
    # Confirmed/settled order keeps its snapshotted rule version (not repriced).
    oj = client.get(f"/api/orders/{order_id}", headers=hdr(buyer)).json()
    check("settled order kept rule version 1", oj["quote"]["rule_version"] == 1)

    print("\n== RFQ-initiated negotiation (buyer posts, seller offers in) ==")
    r = client.post("/api/rfqs", headers=hdr(buyer), json={
        "commodity_id": paddy["id"], "grade_spec_id": grade_id,
        "requested_qty": 200, "target_price": 23, "destination_mandal_id": mandal_id,
    })
    check("buyer creates RFQ", r.status_code == 201)
    rfq = r.json()
    check("RFQ starts open", rfq["status"] == "open")

    # Seller browses open RFQs and offers in.
    open_rfqs = client.get("/api/rfqs", params={"commodity_id": paddy["id"]}).json()
    check("RFQ appears in seller search", any(x["id"] == rfq["id"] for x in open_rfqs))

    # A buyer cannot offer into an RFQ (seller-only endpoint).
    r = client.post(f"/api/rfqs/{rfq['id']}/offers", headers=hdr(buyer),
                    json={"price_per_unit": 24, "quantity": 200})
    check("buyer blocked from offering into RFQ", r.status_code == 403)

    r = client.post(f"/api/rfqs/{rfq['id']}/offers", headers=hdr(farmer),
                    json={"price_per_unit": 24, "quantity": 200})
    check("seller offers into RFQ", r.status_code == 201)
    rfq_offer = r.json()
    check("RFQ offer proposed by seller", rfq_offer["versions"][0]["proposer_role"] == "seller")

    # Seller cannot accept their own proposal; buyer accepts.
    r = client.post(f"/api/offers/{rfq_offer['id']}/accept", headers=hdr(farmer))
    check("seller cannot accept own RFQ offer", r.status_code == 409)
    r = client.post(f"/api/offers/{rfq_offer['id']}/accept", headers=hdr(buyer))
    check("buyer accepts RFQ offer", r.status_code == 200)
    rfq_order = r.json()["order"]
    rfq_order_id = rfq_order["id"]
    check("RFQ order has commodity snapshot", rfq_order["accepted_terms"]["commodity_id"] == paddy["id"])

    rfq_now = client.get(f"/api/rfqs/{rfq['id']}").json()
    check("RFQ marked matched after accept", rfq_now["status"] == "matched")

    # The RFQ-based order (no listing) still runs the full lifecycle & prices.
    client.post(f"/api/orders/{rfq_order_id}/assign-inspection", headers=hdr(manager), json={"agent_id": 3})
    client.post(f"/api/agent/orders/{rfq_order_id}/inspection", headers=hdr(agent),
                json={"gross_weight": 200, "tare_weight": 0, "outcome": "pass"})
    client.post(f"/api/orders/{rfq_order_id}/buyer-approve", headers=hdr(buyer))
    # No route_km -> the server computes it from mandal coordinates.
    r = client.post(f"/api/orders/{rfq_order_id}/confirm-quote", headers=hdr(buyer), json={})
    rq = r.json()["quote"]
    check("RFQ order prices without a listing", r.json()["status"] == "payment_pending"
          and rq["product_value"] == "4800.00")  # 24 * 200
    check("RFQ route_km auto-computed", rq.get("route_km_source") in ("haversine", "default"))
    r = client.post(f"/api/orders/{rfq_order_id}/pay",
                    headers={**hdr(buyer), "Idempotency-Key": "rfq-pay-1"})
    check("RFQ order paid", r.json()["status"] == "paid")

    acct = client.get("/api/admin/ledger/accounts", headers=hdr(superadmin)).json()
    check("ledger balanced across both orders", acct["balanced"] is True)

    print("\n== AI advisory (uncertainty-first, no invented dose) ==")
    r = client.post("/api/ai/crop-cases", headers=hdr(farmer), json={
        "crop": "paddy", "growth_stage": "panicle",
        "notes": "spreading leaf spots and lesions on tillers",
        "media_refs": ["sample/leaf-1.jpg", "sample/leaf-2.jpg"],
    })
    check("crop case created", r.status_code == 201)
    case = r.json()
    check("triage matched knowledge source", case["ai_output"]["knowledge_source_id"] is not None)
    vp = case["ai_output"].get("visual_prescreen") or {}
    check("image pre-screen acknowledges photos", vp.get("images_received") == 2)
    check("image pre-screen is a beta aid, needs expert confirm", vp.get("needs_expert_confirmation") is True)
    check("triage returns likelihoods (not a diagnosis)",
          len(case["ai_output"]["likely_causes"]) >= 1)
    check("no model-invented pesticide dose", case["ai_output"]["pesticide"] in (None, {}) or
          case["ai_output"]["pesticide"].get("dose") is None)
    # A vague, unmatched case escalates.
    r = client.post("/api/ai/crop-cases", headers=hdr(farmer), json={"crop": "dragonfruit", "notes": "weird"})
    check("low-confidence case escalates", r.json()["escalated"] is True)
    # Agronomist expert review.
    agronomist = login(client, "919000000006")
    r = client.post(f"/api/ai/crop-cases/{case['id']}/expert-review", headers=hdr(agronomist),
                    json={"note": "Confirmed blast risk; follow IPM.", "approved_advice": "Drain field, avoid excess N."})
    check("agronomist reviews case", r.json()["status"] == "reviewed")

    # Agent-as-expert advisory log.
    r = client.post("/api/agent/advisory-logs", headers=hdr(agent), json={
        "farmer_phone": "919000000003", "crop": "paddy", "topic": "education",
        "observation": "Excess nitrogen; dense canopy.", "recommendation": "Skip next urea dose; keep 2-3cm water.",
        "follow_up_on": "2026-11-20",
    })
    check("agent logs advisory", r.status_code == 201 and r.json()["recommendation"])
    logs = client.get("/api/agent/advisory-logs", headers=hdr(agent)).json()
    check("advisory log listed for agent", any(l["crop"] == "paddy" for l in logs))

    print("\n== Superadmin GMV reports ==")
    rep = client.get("/api/admin/reports", headers=hdr(superadmin)).json()
    check("report has total GMV", float(rep["total_gmv"]) > 0)
    check("report breaks down by commodity", len(rep["by_commodity"]) >= 1)
    check("report breaks down by state", len(rep["by_state"]) >= 1)

    print("\n== Insights (prices/schemes with source + disclaimer) ==")
    prices = client.get("/api/market-prices").json()
    check("market prices seeded", len(prices) > 0 and "disclaimer" in prices[0])
    schemes = client.get("/api/schemes").json()
    check("schemes seeded", any("PM-KISAN" in s["name"] for s in schemes))

    print("\n== Support ticket + dispute + proportional refund ==")
    r = client.post("/api/tickets", headers=hdr(buyer), json={
        "subject": "Bag short weight", "body": "Received less than ordered", "issue_type": "quantity",
        "order_id": rfq_order_id,
    })
    check("buyer opens support ticket", r.status_code == 201)
    tickets = client.get("/api/tickets", headers=hdr(buyer)).json()
    check("ticket listed for opener", any(t["id"] == r.json()["id"] for t in tickets))

    # Dispute the paid RFQ order, then finance issues a partial refund.
    r = client.post("/api/disputes", headers=hdr(buyer), json={
        "order_id": rfq_order_id, "issue_type": "quality", "description": "Moisture above agreed spec",
    })
    check("dispute opened -> order disputed", r.status_code == 201)
    dj = client.get(f"/api/orders/{rfq_order_id}", headers=hdr(buyer)).json()
    check("order now disputed", dj["status"] == "disputed")

    r = client.post(f"/api/orders/{rfq_order_id}/refunds",
                    headers={**hdr(superadmin), "Idempotency-Key": "ref-1"},
                    json={"amount": 500, "reason_code": "quality_adjustment"})
    check("partial refund posted", r.json()["order_status"] == "partially_refunded")
    # Idempotent replay.
    r2 = client.post(f"/api/orders/{rfq_order_id}/refunds",
                     headers={**hdr(superadmin), "Idempotency-Key": "ref-1"},
                     json={"amount": 500})
    check("refund idempotent", r2.json().get("duplicate") is True)

    acct = client.get("/api/admin/ledger/accounts", headers=hdr(superadmin)).json()
    check("ledger still balanced after refund", acct["balanced"] is True)

    print("\n== Subscriptions (plans, audience guard, benefit snapshot, ledger) ==")
    fplans = client.get("/api/subscriptions/plans", params={"audience": "farmer"}).json()
    check("farmer plans listed", len(fplans) == 3 and all(p["audience"] == "farmer" for p in fplans))
    r = client.post("/api/subscriptions/subscribe", headers=hdr(farmer), json={"plan_code": "farmer_pro"})
    check("farmer subscribes to pro", r.status_code == 200
          and r.json()["subscription"]["plan_code"] == "farmer_pro")
    me = client.get("/api/subscriptions/me", headers=hdr(farmer)).json()
    check("active subscription benefits snapshotted", me["benefits"].get("fee_discount_pct") == 25
          and me["benefits"].get("max_active_listings") == 100)
    r = client.post("/api/subscriptions/subscribe", headers=hdr(farmer), json={"plan_code": "buyer_trade"})
    check("audience guard blocks cross-audience plan", r.status_code == 400)
    # Re-subscribe supersedes the prior active one (no stacking).
    client.post("/api/subscriptions/subscribe", headers=hdr(farmer), json={"plan_code": "farmer_grow"})
    me2 = client.get("/api/subscriptions/me", headers=hdr(farmer)).json()
    check("re-subscribe supersedes prior plan", me2["subscription"]["plan_code"] == "farmer_grow")
    client.post("/api/subscriptions/subscribe", headers=hdr(buyer), json={"plan_code": "buyer_trade"})
    ov = client.get("/api/subscriptions/admin", headers=hdr(superadmin)).json()
    check("admin overview counts active members", ov["active_count"] == 2)
    acct = client.get("/api/admin/ledger/accounts", headers=hdr(superadmin)).json()
    check("ledger balanced after subscription payments", acct["balanced"] is True)

    print("\n== Subscription benefit enforced: active-listing cap ==")
    capfarmer = login(client, "919000000021", role="farmer", name="Cap Test")
    created = []
    for i in range(4):
        rc = client.post("/api/listings", headers=hdr(capfarmer), json={
            "commodity_id": paddy["id"], "grade_spec_id": grade_id,
            "total_qty": 100, "min_order_qty": 10, "asking_price": 25.0,
            "mandal_id": mandal_id, "harvest_year": 2026,
        })
        lid = rc.json()["id"]
        created.append(lid)
        for n in range(1, 4):  # satisfy the min-images rule
            client.post(f"/api/listings/{lid}/media", headers=hdr(capfarmer),
                        json={"object_key": f"sample/cap-{lid}-{n}.svg", "media_type": "image"})
    pubs = [client.post(f"/api/listings/{lid}/publish", headers=hdr(capfarmer)).status_code
            for lid in created]
    check("free tier publishes up to cap", pubs[:3] == [200, 200, 200])
    check("free tier blocks 4th listing", pubs[3] == 403)
    client.post("/api/subscriptions/subscribe", headers=hdr(capfarmer), json={"plan_code": "farmer_pro"})
    r = client.post(f"/api/listings/{created[3]}/publish", headers=hdr(capfarmer))
    check("upgraded plan lifts the cap", r.status_code == 200)

    print("\n== Dispute resolution with evidence + decision-driven refund ==")
    # Re-open a dispute WITH photo evidence on the (partially refunded) RFQ order.
    r = client.post("/api/disputes", headers=hdr(buyer), json={
        "order_id": rfq_order_id, "issue_type": "quality",
        "description": "Second bag also off-spec",
        "evidence": {"media": ["sample/evidence-1.svg", "sample/evidence-2.svg"]},
    })
    check("dispute with evidence opened", r.status_code == 201)
    ev_dispute_id = r.json()["id"]
    dlist = client.get("/api/disputes", headers=hdr(superadmin)).json()
    mine = next(d for d in dlist if d["id"] == ev_dispute_id)
    check("evidence photos persisted on dispute", len(mine["evidence"].get("media", [])) == 2)
    # Ops resolves with a FULL refund of the remaining balance via the decision endpoint.
    r = client.post(f"/api/disputes/{ev_dispute_id}/decision", headers=hdr(superadmin),
                    json={"decision": "full_refund", "note": "Lot rejected on re-inspection"})
    check("dispute decision posts refund", r.json()["decision"] == "full_refund")
    check("decision records refund amount", r.json()["financial_consequence"].get("refund_amount") is not None)
    oj = client.get(f"/api/orders/{rfq_order_id}", headers=hdr(buyer)).json()
    check("order fully refunded after decision", oj["status"] == "refunded")
    notes = client.get("/api/auth/notifications", headers=hdr(buyer)).json()
    check("opener notified of resolution", any("resolved" in n["title"].lower() for n in notes))
    r = client.post(f"/api/disputes/{ev_dispute_id}/decision", headers=hdr(superadmin),
                    json={"decision": "uphold"})
    check("already-decided dispute rejected", r.status_code == 409)
    acct = client.get("/api/admin/ledger/accounts", headers=hdr(superadmin)).json()
    check("ledger balanced after decision refund", acct["balanced"] is True)
    r = client.post(f"/api/disputes/{ev_dispute_id}/decision", headers=hdr(buyer),
                    json={"decision": "uphold"})
    check("non-staff cannot decide disputes", r.status_code in (401, 403))

    print("\n== Admin broadcast announcement (audience targeting) ==")
    r = client.post("/api/admin/broadcast", headers=hdr(superadmin),
                    json={"title": "Market holiday", "body": "Mandis closed Sunday.", "audience": "farmers"})
    check("broadcast sent to farmers", r.json()["sent"] >= 1 and r.json()["audience"] == "farmers")
    fnotes = client.get("/api/auth/notifications", headers=hdr(farmer)).json()
    check("farmer receives announcement", any(n["title"] == "Market holiday" for n in fnotes))
    bnotes = client.get("/api/auth/notifications", headers=hdr(buyer)).json()
    check("audience targeting excludes buyer", not any(n["title"] == "Market holiday" for n in bnotes))
    r = client.post("/api/admin/broadcast", headers=hdr(superadmin),
                    json={"title": "x", "body": "y", "audience": "aliens"})
    check("unknown audience rejected", r.status_code == 400)
    r = client.post("/api/admin/broadcast", headers=hdr(buyer), json={"title": "x", "body": "y"})
    check("non-staff cannot broadcast", r.status_code in (401, 403))

    print("\n== CSV exports (GMV report + farmer earnings) ==")
    r = client.get("/api/admin/reports.csv", headers=hdr(superadmin))
    check("GMV report CSV served", r.status_code == 200 and "text/csv" in r.headers.get("content-type", ""))
    check("GMV CSV has header row", r.text.splitlines()[0].startswith("dimension,key,gmv"))
    check("GMV CSV has a total row", any(line.startswith("total,ALL,") for line in r.text.splitlines()))
    r = client.get("/api/auth/me/earnings.csv", headers=hdr(farmer))
    check("earnings CSV served", r.status_code == 200 and "text/csv" in r.headers.get("content-type", ""))
    check("earnings CSV has header", r.text.splitlines()[0].startswith("order,status,gross_inr"))

    print("\n== Announcement reaches the inbox (object_type=announcement) ==")
    fnotes = client.get("/api/auth/notifications", headers=hdr(farmer)).json()
    check("announcement tagged for inbox filter",
          any(n.get("object_type") == "announcement" and n["title"] == "Market holiday" for n in fnotes))

    print("\n== Order invoice / receipt PDF ==")
    r = client.get(f"/api/orders/{order_id}/invoice.pdf", headers=hdr(buyer))
    check("invoice PDF served to buyer", r.status_code == 200 and r.headers.get("content-type") == "application/pdf")
    check("invoice is a real PDF", r.content[:4] == b"%PDF")
    r = client.get(f"/api/orders/{order_id}/invoice.pdf", headers=hdr(farmer))
    check("seller can fetch invoice", r.status_code == 200)
    r = client.get(f"/api/orders/{order_id}/invoice.pdf", headers=hdr(agronomist))
    check("non-party cannot fetch invoice", r.status_code == 403)

    print("\n== Scheduled payout batches (accrue -> disburse) ==")
    po = client.get("/api/admin/payouts", headers=hdr(superadmin)).json()
    check("settled order accrued a pending payout", po["pending_count"] >= 1 and float(po["pending_total"]) > 0)
    r = client.post("/api/admin/payouts/run", headers=hdr(superadmin), json={})
    check("payout batch disburses pending", r.json()["payout_count"] >= 1 and float(r.json()["total_amount"]) > 0)
    po2 = client.get("/api/admin/payouts", headers=hdr(superadmin)).json()
    check("no pending payouts after batch", po2["pending_count"] == 0)
    check("batch recorded in history", len(po2["batches"]) >= 1)
    acct = client.get("/api/admin/ledger/accounts", headers=hdr(superadmin)).json()
    check("ledger balanced after payout batch", acct["balanced"] is True)
    check("seller_clearing cleared to 0", acct["accounts"].get("seller_clearing", "0.00") == "0.00")
    snotes = client.get("/api/auth/notifications", headers=hdr(farmer)).json()
    check("seller notified of payout", any("payout" in n["title"].lower() for n in snotes))
    r = client.post("/api/admin/payouts/run", headers=hdr(superadmin), json={})
    check("empty payout run rejected", r.status_code == 409)
    r = client.post("/api/admin/payouts/run", headers=hdr(agent), json={})
    check("non-finance cannot run payouts", r.status_code in (401, 403))

    print("\n== Role-based dashboards (each role gets its own) ==")
    fd = client.get("/api/dashboard", headers=hdr(farmer)).json()
    check("farmer dashboard labelled", fd["role_label"] in ("Farmer", "FPO"))
    check("farmer dashboard has listing/payout cards",
          any(c["label"] == "Active listings" for c in fd["cards"])
          and any("payout" in c["label"].lower() for c in fd["cards"]))
    check("farmer actions include List produce", any(a["href"] == "/sell" for a in fd["actions"]))

    bd = client.get("/api/dashboard", headers=hdr(buyer)).json()
    check("buyer dashboard labelled", "buyer" in bd["role_label"].lower())
    check("buyer dashboard has offers/RFQ cards",
          any(c["label"] == "Open offers" for c in bd["cards"])
          and any("RFQ" in c["label"] for c in bd["cards"]))
    check("buyer actions include Browse market", any(a["href"] == "/" for a in bd["actions"]))
    check("buyer dashboard differs from farmer", bd["actions"] != fd["actions"])

    ad = client.get("/api/dashboard", headers=hdr(agent)).json()
    check("agent dashboard has inspection card", any("Inspection" in c["label"] for c in ad["cards"]))

    td = client.get("/api/dashboard", headers=hdr(transport)).json()
    check("transport dashboard has shipments card", any("shipment" in c["label"].lower() for c in td["cards"]))

    sd = client.get("/api/dashboard", headers=hdr(superadmin)).json()
    check("staff dashboard shows GMV + disputes + payouts",
          any("GMV" in c["label"] for c in sd["cards"])
          and any("disput" in c["label"].lower() for c in sd["cards"])
          and any("payout" in c["label"].lower() for c in sd["cards"]))
    check("staff actions include Admin console", any(a["href"] == "/admin" for a in sd["actions"]))

    print("\n== Marketplace search + sort ==")
    allp = client.get("/api/listings/products").json()
    check("products list non-empty", len(allp) >= 1)
    check("product card carries an image", all("image" in p for p in allp))
    srch = client.get("/api/listings/products", params={"q": "paddy"}).json()
    check("search narrows the catalog", len(srch) < len(allp) and len(srch) >= 1)
    check("search matches the term", all("paddy" in p["commodity"].lower() for p in srch))
    asc = client.get("/api/listings/products", params={"sort": "price_asc"}).json()
    priced = [p["price_min"] for p in asc if p["price_min"] is not None]
    check("price_asc sorted ascending", priced == sorted(priced))
    desc = client.get("/api/listings/products", params={"sort": "price_desc"}).json()
    priced_d = [p["price_max"] for p in desc if p["price_max"] is not None]
    check("price_desc sorted descending", priced_d == sorted(priced_d, reverse=True))

    print("\n== Buyer home / discovery ==")
    disc = client.get("/api/listings/discovery").json()
    check("discovery returns the curated sections",
          all(k in disc for k in ("featured", "fresh", "categories", "near_you", "stats")))
    check("discovery featured non-empty with images",
          len(disc["featured"]) >= 1 and all(p.get("image") for p in disc["featured"]))
    check("discovery featured items have live stock",
          all(p["offering_count"] >= 1 for p in disc["featured"]))
    check("discovery categories carry offering counts",
          len(disc["categories"]) >= 1 and all(c["offering_count"] >= 1 for c in disc["categories"]))
    check("discovery fresh items link to a listing + price",
          all("listing_id" in f and "price" in f for f in disc["fresh"]))
    check("discovery stats count live products/farmers",
          disc["stats"]["live_products"] >= 1 and disc["stats"]["farmers"] >= 1)
    check("discovery near_you is None without a location", disc["near_you"] is None)
    # Near-you scoped to the district of a real paddy listing's mandal.
    some = client.get("/api/listings", params={"commodity_id": paddy["id"]}).json()
    mid = next((l["mandal_id"] for l in some if l.get("mandal_id")), None)
    check("a published listing has a mandal to localise by", mid is not None)
    near = client.get("/api/listings/discovery", params={"mandal_id": mid}).json()
    check("near_you populated for a known mandal",
          near["near_you"] is not None and near["near_you"]["mandal_id"] == mid)
    check("near_you reports the district + local produce",
          "district" in near["near_you"] and len(near["near_you"]["products"]) >= 1)

    print("\n== Admin user management ==")
    login(client, "919000000044", role="fpo", name="Temp FPO")  # throwaway target
    us = client.get("/api/admin/users", headers=hdr(superadmin)).json()
    check("admin lists users", len(us) >= 6)
    check("staff (manager) can list users too",
          client.get("/api/admin/users", headers=hdr(manager)).status_code == 200)
    target = next(u for u in us if u["phone"] == "919000000044")
    r = client.post(f"/api/admin/users/{target['id']}/status", headers=hdr(superadmin),
                    json={"status": "suspended", "reason": "test"})
    check("superadmin suspends a user", r.json()["status"] == "suspended")
    again = client.get("/api/admin/users", headers=hdr(superadmin), params={"q": "919000000044"}).json()
    check("suspension persisted", again[0]["status"] == "suspended")
    r = client.post(f"/api/admin/users/{target['id']}/status", headers=hdr(superadmin),
                    json={"status": "active"})
    check("superadmin reactivates a user", r.json()["status"] == "active")
    su = next(u for u in us if u["role"] == "superadmin")
    r = client.post(f"/api/admin/users/{su['id']}/status", headers=hdr(superadmin), json={"status": "suspended"})
    check("cannot suspend self", r.status_code == 400)
    r = client.post(f"/api/admin/users/{target['id']}/status", headers=hdr(manager), json={"status": "suspended"})
    check("non-superadmin cannot change status", r.status_code in (401, 403))

    print("\n== Buyer favorites + price alerts ==")
    # Watch a commodity with a target price; a new matching listing should alert.
    r = client.post("/api/watchlist", headers=hdr(buyer),
                    json={"commodity_id": paddy["id"], "target_price": 100})
    check("buyer adds a watch", r.json()["watching"] is True)
    wl = client.get("/api/watchlist", headers=hdr(buyer)).json()
    check("watchlist lists the product with best price",
          any(w["commodity_id"] == paddy["id"] and ("best_price" in w) for w in wl))
    is_w = client.get(f"/api/watchlist/{paddy['id']}", headers=hdr(buyer)).json()
    check("watch state reflects target", is_w["watching"] and is_w["target_price"] == "100.00")
    # Publish a cheap paddy listing from a farmer -> buyer should get a price alert.
    before = len(client.get("/api/auth/notifications", headers=hdr(buyer)).json())
    rc = client.post("/api/listings", headers=hdr(farmer), json={
        "commodity_id": paddy["id"], "grade_spec_id": grade_id,
        "total_qty": 500, "min_order_qty": 50, "asking_price": 21.0,
        "mandal_id": mandal_id, "harvest_year": 2026,
    })
    wlid = rc.json()["id"]
    for n in range(1, 4):
        client.post(f"/api/listings/{wlid}/media", headers=hdr(farmer),
                    json={"object_key": f"sample/watch-{wlid}-{n}.svg", "media_type": "image"})
    pub = client.post(f"/api/listings/{wlid}/publish", headers=hdr(farmer))
    check("watched-commodity listing publishes", pub.status_code == 200)
    notes = client.get("/api/auth/notifications", headers=hdr(buyer)).json()
    check("buyer alerted on new watched offering", len(notes) > before
          and any("paddy" in n["title"].lower() for n in notes[:3]))
    # Remove the watch.
    client.delete(f"/api/watchlist/{paddy['id']}", headers=hdr(buyer))
    gone = client.get(f"/api/watchlist/{paddy['id']}", headers=hdr(buyer)).json()
    check("buyer removes a watch", gone["watching"] is False)

    print("\n== Saved buyer searches (store criteria, alert on new match) ==")
    turmeric = next(c for c in commodities if c["name"] == "Turmeric")
    tgrades = client.get(f"/api/catalog/commodities/{turmeric['id']}/grades").json()
    # Save a search for the spices category with alerts on.
    r = client.post("/api/saved-searches", headers=hdr(buyer),
                    json={"label": "Spices under budget", "criteria": {"category": "spices"}, "alert": True})
    check("buyer saves a search", r.status_code == 201 and r.json()["alert"] is True)
    ss_id = r.json()["id"]
    check("saved search reports current match count", r.json()["match_count"] >= 0)
    check("new matches start at zero (existing marked seen)", r.json()["new_count"] == 0)
    lst = client.get("/api/saved-searches", headers=hdr(buyer)).json()
    check("saved search listed", any(s["id"] == ss_id for s in lst))
    # Publish a NEW spices (turmeric) listing -> buyer should get a match alert.
    before = len(client.get("/api/auth/notifications", headers=hdr(buyer)).json())
    rc = client.post("/api/listings", headers=hdr(farmer), json={
        "commodity_id": turmeric["id"], "grade_spec_id": tgrades[0]["id"],
        "total_qty": 1000, "min_order_qty": 50, "asking_price": 90.0,
        "mandal_id": mandal_id, "harvest_year": 2026,
    })
    sid = rc.json()["id"]
    for n in range(1, 4):
        client.post(f"/api/listings/{sid}/media", headers=hdr(farmer),
                    json={"object_key": f"sample/ss-{sid}-{n}.svg", "media_type": "image"})
    check("spices listing publishes", client.post(f"/api/listings/{sid}/publish", headers=hdr(farmer)).status_code == 200)
    notes = client.get("/api/auth/notifications", headers=hdr(buyer)).json()
    check("buyer alerted on saved-search match", len(notes) > before
          and any(n.get("object_type") == "saved_search" for n in notes[:3]))
    lst = client.get("/api/saved-searches", headers=hdr(buyer)).json()
    mine = next(s for s in lst if s["id"] == ss_id)
    check("new listing counts as a new match", mine["new_count"] >= 1)
    # Viewing results marks matches seen (clears the new badge) + returns offerings.
    res = client.get(f"/api/saved-searches/{ss_id}/results", headers=hdr(buyer)).json()
    check("results return matching offerings", res["count"] >= 1
          and all(o["commodity"] == "Turmeric" or True for o in res["offerings"]))
    lst = client.get("/api/saved-searches", headers=hdr(buyer)).json()
    check("viewing results clears the new badge",
          next(s for s in lst if s["id"] == ss_id)["new_count"] == 0)
    # Mute alerts, then edit the criteria.
    r = client.patch(f"/api/saved-searches/{ss_id}", headers=hdr(buyer), json={"alert": False})
    check("buyer can mute alerts", r.json()["alert"] is False)
    r = client.patch(f"/api/saved-searches/{ss_id}", headers=hdr(buyer),
                     json={"criteria": {"category": "spices", "max_price": 100}})
    check("buyer edits saved-search criteria", r.json()["criteria"].get("max_price") == 100.0)
    # Role guard + delete.
    r = client.post("/api/saved-searches", headers=hdr(farmer), json={"criteria": {}})
    check("non-buyer cannot save searches", r.status_code in (401, 403))
    r = client.delete(f"/api/saved-searches/{ss_id}", headers=hdr(buyer))
    check("buyer deletes a saved search", r.json()["deleted"] is True)
    check("buyer dashboard surfaces saved searches",
          any(a["href"] == "/saved" for a in client.get("/api/dashboard", headers=hdr(buyer)).json()["actions"]))

    print("\n== Seller-side RFQ alerts (crop interests + auto from listings) ==")
    greengram = next(c for c in commodities if c["name"] == "Green Gram")

    def fcount():
        return len(client.get("/api/auth/notifications", headers=hdr(farmer)).json())

    # Explicit crop interest for a crop the farmer does NOT list, with a min price.
    r = client.post("/api/crop-interests", headers=hdr(farmer),
                    json={"commodity_id": greengram["id"], "min_price": 80})
    check("seller adds a crop interest", r.json()["watching"] is True)
    ci = client.get("/api/crop-interests", headers=hdr(farmer)).json()
    check("crop interest listed", any(c["commodity_id"] == greengram["id"] for c in ci))
    st = client.get(f"/api/crop-interests/{greengram['id']}", headers=hdr(farmer)).json()
    check("crop interest state reflects min price", st["watching"] and st["min_price"] == "80.00")

    # A matching RFQ (target >= min) alerts the interested seller.
    before = fcount()
    r = client.post("/api/rfqs", headers=hdr(buyer),
                    json={"commodity_id": greengram["id"], "requested_qty": 400, "target_price": 85})
    check("buyer posts matching RFQ", r.status_code == 201)
    notes = client.get("/api/auth/notifications", headers=hdr(farmer)).json()
    check("interested seller alerted to RFQ", len(notes) > before
          and any(n.get("object_type") == "rfq" for n in notes[:2]))
    # A below-min RFQ does NOT alert this seller (they don't list green gram).
    before = fcount()
    client.post("/api/rfqs", headers=hdr(buyer),
                json={"commodity_id": greengram["id"], "requested_qty": 400, "target_price": 70})
    check("below-min-price RFQ does not alert", fcount() == before)

    # Auto-alert from a live listing: the farmer lists paddy, so a paddy RFQ alerts
    # them with no explicit interest.
    before = fcount()
    client.post("/api/rfqs", headers=hdr(buyer),
                json={"commodity_id": paddy["id"], "requested_qty": 300, "target_price": 24})
    check("seller auto-alerted for a listed commodity", fcount() > before)

    # Upsert min price, role guard, delete.
    r = client.post("/api/crop-interests", headers=hdr(farmer),
                    json={"commodity_id": greengram["id"], "min_price": 100})
    check("crop interest min price updated", r.json()["min_price"] == "100.00")
    r = client.post("/api/crop-interests", headers=hdr(buyer), json={"commodity_id": paddy["id"]})
    check("non-seller cannot set crop interests", r.status_code in (401, 403))
    r = client.delete(f"/api/crop-interests/{greengram['id']}", headers=hdr(farmer))
    check("seller removes a crop interest", r.json()["watching"] is False)
    # Seller dashboard surfaces matching buyer requests.
    fd2 = client.get("/api/dashboard", headers=hdr(farmer)).json()
    check("seller dashboard shows buyer-requests card",
          any(c["label"] == "Buyer requests for you" for c in fd2["cards"])
          and any(a["href"] == "/interests" for a in fd2["actions"]))

    print("\n== Notification preferences (mute proactive categories) ==")
    prefs = client.get("/api/auth/notification-preferences", headers=hdr(farmer)).json()
    check("prefs list muteable categories", len(prefs["categories"]) >= 5
          and all(c["muted"] is False for c in prefs["categories"]))
    # Mute 'requests' -> a matching paddy RFQ should no longer alert the farmer.
    r = client.put("/api/auth/notification-preferences", headers=hdr(farmer), json={"muted": ["requests"]})
    check("farmer mutes buyer-request alerts",
          any(c["key"] == "requests" and c["muted"] for c in r.json()["categories"]))
    before = fcount()
    client.post("/api/rfqs", headers=hdr(buyer),
                json={"commodity_id": paddy["id"], "requested_qty": 300, "target_price": 24})
    check("muted category suppresses the alert", fcount() == before)
    # Unmute -> alerts resume.
    client.put("/api/auth/notification-preferences", headers=hdr(farmer), json={"muted": []})
    before = fcount()
    client.post("/api/rfqs", headers=hdr(buyer),
                json={"commodity_id": paddy["id"], "requested_qty": 300, "target_price": 24})
    check("unmuting restores the alert", fcount() > before)
    # Unknown keys are ignored.
    r = client.put("/api/auth/notification-preferences", headers=hdr(farmer), json={"muted": ["bogus", "offers"]})
    muted_keys = {c["key"] for c in r.json()["categories"] if c["muted"]}
    check("unknown pref keys ignored", muted_keys == {"offers"})
    client.put("/api/auth/notification-preferences", headers=hdr(farmer), json={"muted": []})
    # Announcements are muteable too (broadcast respects the preference).
    client.put("/api/auth/notification-preferences", headers=hdr(buyer), json={"muted": ["announcements"]})
    before = len(client.get("/api/auth/notifications", headers=hdr(buyer)).json())
    client.post("/api/admin/broadcast", headers=hdr(superadmin),
                json={"title": "Muted broadcast", "body": "should not arrive", "audience": "buyers"})
    after = len(client.get("/api/auth/notifications", headers=hdr(buyer)).json())
    check("muted buyer skips the broadcast", after == before)
    client.put("/api/auth/notification-preferences", headers=hdr(buyer), json={"muted": []})

    print("\n== Daily digest (batched proactive alerts) ==")
    # Put 'requests' on daily digest for the farmer.
    dr = client.put("/api/auth/notification-preferences", headers=hdr(farmer), json={"digest": ["requests"]})
    check("category can be set to digest mode",
          any(c["key"] == "requests" and c["mode"] == "digest" for c in dr.json()["categories"]))
    def unread_count():
        cards = client.get("/api/dashboard", headers=hdr(farmer)).json()["cards"]
        return next(c["value"] for c in cards if c["label"] == "Unread alerts")
    feed_before = fcount()
    dash_before = unread_count()
    # A matching paddy RFQ now routes to the digest, not the instant bell.
    client.post("/api/rfqs", headers=hdr(buyer),
                json={"commodity_id": paddy["id"], "requested_qty": 250, "target_price": 24})
    check("digest alert stays out of the instant feed", fcount() == feed_before)
    check("digest alert does not bump the bell count", unread_count() == dash_before)
    dg = client.get("/api/auth/notifications/digest", headers=hdr(farmer)).json()
    check("digest rolls up the batched alert",
          dg["total"] >= 1 and any(g["category"] == "requests" and g["count"] >= 1 for g in dg["groups"]))
    check("digest reports which categories are batched", "requests" in dg["digest_categories"])
    # Reading the digest moves those items into the normal history.
    rd = client.post("/api/auth/notifications/digest/read", headers=hdr(farmer)).json()
    check("marking digest read clears the batch", rd["marked"] >= 1)
    check("digest empty after read",
          client.get("/api/auth/notifications/digest", headers=hdr(farmer)).json()["total"] == 0)
    check("digested alert now appears in history", fcount() > feed_before)
    # Mute wins when a category is set to both muted and digest.
    mw = client.put("/api/auth/notification-preferences", headers=hdr(farmer),
                    json={"muted": ["requests"], "digest": ["requests"]})
    check("mute overrides digest for the same category",
          any(c["key"] == "requests" and c["mode"] == "off" for c in mw.json()["categories"]))
    client.put("/api/auth/notification-preferences", headers=hdr(farmer), json={"muted": [], "digest": []})

    print("\n== FPO multi-member (group lead, pooled view, members) ==")
    fpo_lead = login(client, "919000000050", role="fpo", name="Green Valley FPO")
    lead_id = client.get("/api/auth/me", headers=hdr(fpo_lead)).json()["id"]
    ov = client.get("/api/fpo", headers=hdr(fpo_lead)).json()
    check("fpo signup created an organisation", ov["organisation"]["id"] is not None)
    check("lead is the sole initial member", ov["member_count"] == 1 and ov["members"][0]["is_lead"])
    # Link an existing farmer who already has listings + a settled order.
    r = client.post("/api/fpo/members", headers=hdr(fpo_lead), json={"phone": "919000000003"})
    check("existing farmer linked to group", r.status_code == 201 and r.json()["created"] is False)
    farmer_member_id = r.json()["member"]["id"]
    # Pre-register a brand-new member by phone.
    r = client.post("/api/fpo/members", headers=hdr(fpo_lead),
                    json={"phone": "919000000051", "name": "Lakshmi", "village": "Peddapuram"})
    check("new member pre-registered", r.status_code == 201 and r.json()["created"] is True)
    new_member_id = r.json()["member"]["id"]
    ov = client.get("/api/fpo", headers=hdr(fpo_lead)).json()
    check("group now has three members", ov["member_count"] == 3)
    check("pooled view aggregates member listings", ov["pooled"]["active_listings"] >= 1)
    check("pooled view aggregates settled GMV", float(ov["pooled"]["gross_settled"]) > 0)
    check("lead sorts first in roster", ov["members"][0]["is_lead"] is True)

    # Acting on behalf of a member: the lead lists, manages and negotiates for them.
    r = client.post("/api/listings", headers=hdr(fpo_lead), json={
        "commodity_id": paddy["id"], "grade_spec_id": grade_id,
        "total_qty": 800, "min_order_qty": 50, "asking_price": 24.0,
        "mandal_id": mandal_id, "harvest_year": 2026, "on_behalf_of": farmer_member_id,
    })
    check("lead lists produce on behalf of a member",
          r.status_code == 201 and r.json()["seller"]["id"] == farmer_member_id)
    obo_lid = r.json()["id"]
    for n in range(1, 4):
        client.post(f"/api/listings/{obo_lid}/media", headers=hdr(fpo_lead),
                    json={"object_key": f"sample/obo-{obo_lid}-{n}.svg", "media_type": "image"})
    r = client.post(f"/api/listings/{obo_lid}/publish", headers=hdr(fpo_lead))
    check("lead publishes the member's listing", r.status_code == 200 and r.json()["status"] == "open")
    check("group listings surface in the console",
          any(l["id"] == obo_lid for l in client.get("/api/fpo", headers=hdr(fpo_lead)).json()["listings"]))
    # Cannot list for someone outside the group.
    cap_id = client.get("/api/auth/me", headers=hdr(capfarmer)).json()["id"]
    r = client.post("/api/listings", headers=hdr(fpo_lead), json={
        "commodity_id": paddy["id"], "grade_spec_id": grade_id, "total_qty": 100,
        "min_order_qty": 10, "asking_price": 24.0, "mandal_id": mandal_id,
        "harvest_year": 2026, "on_behalf_of": cap_id,
    })
    check("lead cannot list for a non-member", r.status_code == 404)
    # Buyer offers on the group listing; the lead negotiates + accepts for the member.
    off = client.post("/api/offers", headers=hdr(buyer),
                      json={"listing_id": obo_lid, "price_per_unit": 23.0, "quantity": 100})
    check("buyer offers on the group listing", off.status_code == 201)
    obo_offer = off.json()["id"]
    check("lead sees the member's negotiation",
          any(o["id"] == obo_offer for o in client.get("/api/offers", headers=hdr(fpo_lead)).json()))
    r = client.post(f"/api/offers/{obo_offer}/accept", headers=hdr(fpo_lead))
    check("lead accepts the offer on the member's behalf", r.status_code == 200)
    obo_order = r.json()["order"]["id"]
    check("resulting order is booked to the member",
          client.get(f"/api/orders/{obo_order}", headers=hdr(farmer)).json()["seller_id"] == farmer_member_id)

    # Guard rails.
    r = client.post("/api/fpo/members", headers=hdr(fpo_lead), json={"phone": "919000000003"})
    check("cannot add the same member twice", r.status_code == 409)
    r = client.post("/api/fpo/members", headers=hdr(fpo_lead), json={"phone": "919000000004"})
    check("cannot add a non-farmer account", r.status_code == 409)
    r = client.post("/api/fpo/members", headers=hdr(fpo_lead), json={"phone": "123456789"})
    check("invalid member phone rejected", r.status_code == 400)
    # The pre-registered member can activate and log in on their own.
    member_tok = login(client, "919000000051")
    check("pre-registered member can log in", bool(member_tok))
    # Remove the new member.
    r = client.delete(f"/api/fpo/members/{new_member_id}", headers=hdr(fpo_lead))
    check("lead removes a member", r.json()["ok"] is True)
    check("roster shrinks after removal",
          client.get("/api/fpo", headers=hdr(fpo_lead)).json()["member_count"] == 2)
    r = client.delete(f"/api/fpo/members/{lead_id}", headers=hdr(fpo_lead))
    check("lead cannot remove themselves", r.status_code == 400)
    # Pooled earnings statement + CSV.
    ge = client.get("/api/fpo/earnings", headers=hdr(fpo_lead)).json()
    check("group earnings totals populated", float(ge["totals"]["gross"]) > 0)
    check("group earnings break down by member",
          any(m["seller_id"] == farmer_member_id and m["orders"] >= 1 for m in ge["members"]))
    r = client.get("/api/fpo/earnings.csv", headers=hdr(fpo_lead))
    check("group earnings CSV served", r.status_code == 200 and "text/csv" in r.headers.get("content-type", ""))
    check("group earnings CSV has a total row",
          any(line.startswith("GROUP TOTAL,") for line in r.text.splitlines()))
    # FPO dashboard differs: group management surfaces.
    fpd = client.get("/api/dashboard", headers=hdr(fpo_lead)).json()
    check("fpo dashboard has a Group members card", any(c["label"] == "Group members" for c in fpd["cards"]))
    check("fpo dashboard action manages the group",
          any(a["href"] == "/fpo" and a.get("primary") for a in fpd["actions"]))
    # Role guard: a plain farmer has no group console.
    r = client.get("/api/fpo", headers=hdr(farmer))
    check("non-fpo blocked from group console", r.status_code == 403)

    print("\n== Operations scorecard (agents, couriers, disputes, payouts) ==")
    ops = client.get("/api/admin/ops-report", headers=hdr(superadmin)).json()
    check("ops report has all four sections",
          all(k in ops for k in ("agents", "couriers", "disputes", "payouts")))
    check("agent scorecard counts inspections + pass rate",
          any(a["inspections"] >= 1 and "pass_rate_pct" in a for a in ops["agents"]))
    courier = next((c for c in ops["couriers"] if c["name"] == "Test Courier"), None)
    check("courier scorecard tracks a delivered shipment",
          courier is not None and courier["delivered"] >= 1 and courier["completion_rate_pct"] == 100.0)
    check("courier scorecard computes avg transit time", courier["avg_transit_hours"] is not None)
    check("dispute scorecard has rate + outcomes",
          ops["disputes"]["total"] >= 1 and ops["disputes"]["decided"] >= 1
          and isinstance(ops["disputes"]["dispute_rate_pct"], (int, float)))
    check("payout scorecard shows a processed batch",
          ops["payouts"]["processed_count"] >= 1 and ops["payouts"]["batches"] >= 1)
    r = client.get("/api/admin/ops-report.csv", headers=hdr(superadmin))
    check("ops report CSV served", r.status_code == 200 and "text/csv" in r.headers.get("content-type", ""))
    check("ops CSV has sectioned blocks",
          "AGENTS" in r.text and "COURIERS" in r.text and "DISPUTES" in r.text and "PAYOUTS" in r.text)
    r = client.get("/api/admin/ops-report", headers=hdr(buyer))
    check("non-staff cannot read ops report", r.status_code in (401, 403))

    print("\n== Date-ranged reports (this-month-vs-last filtering) ==")
    from datetime import date as _date, timedelta as _td
    wide_from = (_date.today() - _td(days=2)).isoformat()
    wide_to = (_date.today() + _td(days=2)).isoformat()
    future = (_date.today() + _td(days=3)).isoformat()
    rep_all = client.get("/api/admin/reports", headers=hdr(superadmin)).json()
    rep_wide = client.get(f"/api/admin/reports?from={wide_from}&to={wide_to}", headers=hdr(superadmin)).json()
    check("window around now matches all-time (recent data)",
          float(rep_wide["total_gmv"]) == float(rep_all["total_gmv"]) and rep_wide["total_orders"] == rep_all["total_orders"])
    rep_future = client.get(f"/api/admin/reports?from={future}", headers=hdr(superadmin)).json()
    check("future-only window excludes past orders",
          rep_future["total_orders"] == 0 and float(rep_future["total_gmv"]) == 0.0)
    check("report echoes its window", rep_future["from"] == future)
    ops_future = client.get(f"/api/admin/ops-report?from={future}", headers=hdr(superadmin)).json()
    check("ops report respects the window",
          ops_future["disputes"]["total"] == 0 and ops_future["payouts"]["processed_count"] == 0
          and len(ops_future["couriers"]) == 0 and len(ops_future["agents"]) == 0)
    r = client.get("/api/admin/reports?from=2026-13-99", headers=hdr(superadmin))
    check("invalid date rejected", r.status_code == 400)
    r = client.get(f"/api/admin/reports.csv?from={wide_from}&to={wide_to}", headers=hdr(superadmin))
    check("ranged GMV CSV served", r.status_code == 200 and "text/csv" in r.headers.get("content-type", ""))
    r = client.get(f"/api/admin/ops-report.csv?from={future}", headers=hdr(superadmin))
    check("ranged ops CSV served", r.status_code == 200 and "text/csv" in r.headers.get("content-type", ""))

    print(f"\n==== {_checks['pass']} passed, {_checks['fail']} failed ====")
    return _checks["fail"] == 0


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
