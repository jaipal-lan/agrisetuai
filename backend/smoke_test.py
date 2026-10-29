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

    r = client.post(f"/api/listings/{listing['id']}/publish", headers=hdr(farmer))
    check("listing published", r.json()["status"] == "open")

    found = client.get("/api/listings", params={"commodity_id": paddy["id"]}).json()
    check("listing appears in search", any(x["id"] == listing["id"] for x in found))
    check("seller phone NOT leaked in search", "phone" not in found[0]["seller"])

    print("\n== Negotiation (offer -> counter -> accept) ==")
    r = client.post("/api/offers", headers=hdr(buyer), json={
        "listing_id": listing["id"], "price_per_unit": 22.0, "quantity": 500,
    })
    check("buyer opens offer", r.status_code == 201)
    offer = r.json()
    check("offer has version 1", offer["versions"][0]["version_no"] == 1)

    # Buyer cannot accept own proposal.
    r = client.post(f"/api/offers/{offer['id']}/accept", headers=hdr(buyer))
    check("buyer cannot accept own proposal", r.status_code == 409)

    # Seller counters at 24.
    r = client.post(f"/api/offers/{offer['id']}/counter", headers=hdr(farmer), json={
        "price_per_unit": 24.0, "quantity": 500,
    })
    check("seller counters (v2)", len(r.json()["versions"]) == 2)

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
    check("service fee 2% = 240.00", q["service_fee"] == "240.00")
    # buyer_total = 12000 + 500 + 300 + 1030 + 240 (+0 tax) = 14070
    check("buyer total 14070.00", q["buyer_total"] == "14070.00")
    check("seller payable 12000.00", q["seller_payable"] == "12000.00")

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
    check("seller_payable credited 12000", acct["accounts"].get("seller_payable") == "12000.00")

    print("\n== Packing, shipment, delivery, settlement ==")
    r = client.post(f"/api/orders/{order_id}/packing-complete", headers=hdr(agent))
    check("packing complete -> ready_for_pickup", r.json()["order"]["status"] == "ready_for_pickup")
    check("lot id issued", r.json()["lot_id"].startswith("LOT-"))

    for ev, expect in [("picked_up", "picked_up"), ("in_transit", "in_transit"),
                       ("out_for_delivery", "out_for_delivery"),
                       ("delivered", "delivered_pending_acceptance")]:
        r = client.post(f"/api/orders/{order_id}/shipment/event", headers=hdr(transport),
                        json={"event": ev})
        check(f"shipment {ev}", r.json()["order"]["status"] == expect)

    r = client.post(f"/api/orders/{order_id}/acceptance", headers=hdr(buyer))
    check("buyer accepts delivery -> settled", r.json()["status"] == "settled")

    relisting = client.get(f"/api/listings/{listing['id']}").json()
    check("reserved released, 500 kg sold", relisting["sold_qty"] == "500.000"
          and relisting["reserved_qty"] == "0.000")

    acct = client.get("/api/admin/ledger/accounts", headers=hdr(superadmin)).json()
    check("ledger still balanced after settlement", acct["balanced"] is True)
    check("seller_payable cleared to 0", acct["accounts"].get("seller_payable") == "0.00")

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
    r = client.post(f"/api/orders/{rfq_order_id}/confirm-quote", headers=hdr(buyer), json={"route_km": 30})
    check("RFQ order prices without a listing", r.json()["status"] == "payment_pending"
          and r.json()["quote"]["product_value"] == "4800.00")  # 24 * 200
    r = client.post(f"/api/orders/{rfq_order_id}/pay",
                    headers={**hdr(buyer), "Idempotency-Key": "rfq-pay-1"})
    check("RFQ order paid", r.json()["status"] == "paid")

    acct = client.get("/api/admin/ledger/accounts", headers=hdr(superadmin)).json()
    check("ledger balanced across both orders", acct["balanced"] is True)

    print(f"\n==== {_checks['pass']} passed, {_checks['fail']} failed ====")
    return _checks["fail"] == 0


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
