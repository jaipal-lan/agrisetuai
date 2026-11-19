"""End-to-end regression for the AgriSetuAI marketplace core.

Runs against a throwaway SQLite DB using FastAPI's TestClient. No server needed.

    cd backend
    python smoke_test.py            # fresh temp DB
"""
import json
import os
import sys
import tempfile

# Point the app at a throwaway DB *before* importing it, and force dev mode.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["DEV_MODE"] = "true"
os.environ["AUTH_SECRET"] = "smoke-test-secret"
# Keep the test hermetic: ignore any local backend/.env secrets (a configured
# live price feed, scheduler, etc.) so the feed tests see the known sample state.
os.environ["PRICES_PROVIDER"] = "sample"
os.environ["DATA_GOV_IN_API_KEY"] = ""
os.environ["PRICES_FEED_STATES"] = ""
os.environ["PRICES_FEED_COMMODITIES"] = ""
os.environ["SCHEDULER_INTERVAL_SECONDS"] = "0"
# Keep uploaded registration evidence out of the real media dir.
os.environ["MEDIA_DIR"] = tempfile.mkdtemp(prefix="agri-smoke-media-")

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


DEMO_PW = "demo1234"


def login(client, phone, role=None, name=None):
    """Return an auth token for `phone`. With `role`, first self-registers a new
    public account (verify phone -> register -> password login); without it,
    logs an existing account in with its demo password."""
    r = client.post("/api/auth/otp/request", json={"phone": phone})
    code = r.json().get("dev_code", "123456")
    if role:
        vp = client.post("/api/auth/otp/verify-phone",
                         json={"phone": phone, "code": code}).json()
        first, _, last = (name or "Test User").partition(" ")
        data = {"phone_token": vp["phone_token"], "password": DEMO_PW, "role": role,
                "first_name": first, "last_name": last}
        files = None
        if role == "buyer_business":
            data["biz_legal_name"] = name or "Demo Business"
            files = [("evidence", ("pan.pdf", b"%PDF-1.4 demo evidence", "application/pdf"))]
        reg = client.post("/api/auth/register", data=data, files=files)
        assert reg.status_code == 201, f"register failed: {reg.status_code} {reg.text}"
    r = client.post("/api/auth/login", json={"phone": phone, "password": DEMO_PW})
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
    manager = login(client, "919000000001")   # seeded field leader (mandal)
    superadmin = login(client, "919999999998")
    transport = login(client, "919000000005")
    check("farmer token issued", bool(farmer))
    check("buyer token issued", bool(buyer))

    # --- Registration + password auth ---
    # Full public sign-up: verify phone -> register (household buyer) -> login.
    ph = "919000000071"
    code = client.post("/api/auth/otp/request", json={"phone": ph}).json().get("dev_code", "123456")
    vp = client.post("/api/auth/otp/verify-phone", json={"phone": ph, "code": code}).json()
    check("verify-phone returns a phone_token for a new number",
          bool(vp.get("phone_token")) and vp.get("exists") is False)
    reg = client.post("/api/auth/register", data={
        "phone_token": vp["phone_token"], "password": "s3cret!", "role": "buyer_household",
        "first_name": "Sita", "last_name": "Devi", "email": "sita@example.com",
    })
    check("register creates a household buyer (no token returned)",
          reg.status_code == 201 and reg.json().get("created") is True and "token" not in reg.json())
    check("short password is rejected",
          client.post("/api/auth/register", data={
              "phone_token": client.post("/api/auth/otp/verify-phone",
                  json={"phone": "919000000072",
                        "code": client.post("/api/auth/otp/request", json={"phone": "919000000072"}).json()["dev_code"]}
                  ).json()["phone_token"],
              "password": "123", "role": "farmer", "first_name": "Short"}).status_code == 400)
    login_ok = client.post("/api/auth/login", json={"phone": ph, "password": "s3cret!"})
    check("new account logs in with phone + password", login_ok.status_code == 200 and "token" in login_ok.json())
    new_tok = login_ok.json()["token"]
    me_new = client.get("/api/auth/me", headers=hdr(new_tok)).json()
    check("me exposes structured name + email", me_new.get("first_name") == "Sita" and me_new.get("email") == "sita@example.com")
    check("wrong password is rejected",
          client.post("/api/auth/login", json={"phone": ph, "password": "nope"}).status_code == 401)
    # OTP verify no longer creates accounts.
    code2 = client.post("/api/auth/otp/request", json={"phone": "919000000079"}).json()["dev_code"]
    check("otp login for an unknown phone 404s (no silent create)",
          client.post("/api/auth/otp/verify", json={"phone": "919000000079", "code": code2}).status_code == 404)
    # OTP login still works for an existing (seeded, no self-signup) account.
    code3 = client.post("/api/auth/otp/request", json={"phone": "919999999998"}).json()["dev_code"]
    check("otp login still works for an existing account",
          "token" in client.post("/api/auth/otp/verify", json={"phone": "919999999998", "code": code3}).json())
    # Duplicate registration is blocked.
    code4 = client.post("/api/auth/otp/request", json={"phone": ph}).json()["dev_code"]
    dup_tok = client.post("/api/auth/otp/verify-phone", json={"phone": ph, "code": code4}).json()
    check("verify-phone flags an existing account", dup_tok.get("exists") is True)
    check("register is blocked for an existing phone",
          client.post("/api/auth/register", data={
              "phone_token": dup_tok["phone_token"], "password": "s3cret!",
              "role": "buyer_household", "first_name": "Dup"}).status_code == 409)
    # Business buyer must attach evidence.
    bz = "919000000073"
    bcode = client.post("/api/auth/otp/request", json={"phone": bz}).json()["dev_code"]
    btok = client.post("/api/auth/otp/verify-phone", json={"phone": bz, "code": bcode}).json()["phone_token"]
    check("business register without evidence is rejected",
          client.post("/api/auth/register", data={
              "phone_token": btok, "password": "s3cret!", "role": "buyer_business",
              "first_name": "Raju", "biz_legal_name": "Raju Traders"}).status_code == 400)
    bcode2 = client.post("/api/auth/otp/request", json={"phone": bz}).json()["dev_code"]
    btok2 = client.post("/api/auth/otp/verify-phone", json={"phone": bz, "code": bcode2}).json()["phone_token"]
    bz_reg = client.post("/api/auth/register",
        data={"phone_token": btok2, "password": "s3cret!", "role": "buyer_business",
              "first_name": "Raju", "biz_legal_name": "Raju Traders", "biz_gst": "36ABCDE1234F1Z5"},
        files=[("evidence", ("regdoc.pdf", b"%PDF-1.4 reg", "application/pdf"))])
    check("business register with evidence succeeds", bz_reg.status_code == 201)
    bz_tok = client.post("/api/auth/login", json={"phone": bz, "password": "s3cret!"}).json()["token"]
    bz_me = client.get("/api/auth/me", headers=hdr(bz_tok)).json()
    check("business account carries its organisation + GST",
          bz_me.get("organisation", {}).get("legal_name") == "Raju Traders"
          and bz_me["organisation"].get("gst") == "36ABCDE1234F1Z5")
    # Registration evidence is PRIVATE: exposed to the owner only as a signed link,
    # refused by the public media route, and shown to staff in the KYC queue.
    ev = (bz_me.get("organisation", {}).get("evidence") or [])
    check("owner sees their registration evidence as a signed link",
          len(ev) == 1 and "/media/secure/" in (ev[0].get("url") or ""))
    ekey = ev[0]["object_key"]
    if ekey.startswith("priv/"):
        check("registration evidence refused by the public media route",
              client.get(f"/api/media/file/{ekey}").status_code == 403)
    bz_kyc = [x for x in client.get("/api/admin/kyc", headers=hdr(superadmin)).json()
              if x["user_id"] == bz_me["id"]]
    check("business buyer appears in KYC queue with signed evidence for staff",
          len(bz_kyc) == 1 and bz_kyc[0].get("business")
          and len(bz_kyc[0]["business"]["evidence"]) == 1
          and "/media/secure/" in (bz_kyc[0]["business"]["evidence"][0].get("url") or ""))
    # Password reset via OTP.
    rcode = client.post("/api/auth/otp/request", json={"phone": ph}).json()["dev_code"]
    rtok = client.post("/api/auth/otp/verify-phone", json={"phone": ph, "code": rcode}).json()["phone_token"]
    check("password reset succeeds",
          client.post("/api/auth/password/reset", json={"phone_token": rtok, "new_password": "newpass9"}).status_code == 200)
    check("login works with the new password after reset",
          client.post("/api/auth/login", json={"phone": ph, "password": "newpass9"}).status_code == 200)
    check("old password no longer works after reset",
          client.post("/api/auth/login", json={"phone": ph, "password": "s3cret!"}).status_code == 401)
    # GPS -> nearest mandal (powers "use my location" at sign-up/checkout).
    near = client.get("/api/locations/nearest", params={"lat": 16.24, "lng": 80.64})
    check("nearest-mandal resolves a GPS point to a mandal",
          near.status_code == 200 and near.json().get("mandal_id"))
    nj = near.json()
    check("nearest flags in-service-area for a nearby point",
          nj.get("within_service_area") is True and "service_radius_km" in nj)
    # A far-away point (Delhi-ish) is outside the AP/TG footprint.
    far = client.get("/api/locations/nearest", params={"lat": 28.61, "lng": 77.21}).json()
    check("nearest flags out-of-service-area for a far point",
          far.get("within_service_area") is False)

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
        "quality_grade": "A", "defect_pct": 2.5, "defect_notes": "Minor broken grains",
    })
    check("farmer creates listing", r.status_code == 201)
    listing = r.json()
    check("listing starts as draft", listing["status"] == "draft")
    check("listing records quality grade + defects",
          listing["quality_grade"] == "A" and listing["defect_pct"] == "2.50"
          and listing["defect_notes"] == "Minor broken grains")
    # Per-listing selling unit + farm geo pin.
    pl = client.post("/api/listings", headers=hdr(farmer), json={
        "commodity_id": paddy["id"], "grade_spec_id": grade_id, "total_qty": 100,
        "min_order_qty": 2, "asking_price": 30, "mandal_id": mandal_id, "harvest_year": 2026,
        "unit": "piece", "latitude": 16.24, "longitude": 80.64})
    check("listing honours a per-listing unit + geo pin",
          pl.status_code == 201 and pl.json()["unit"] == "piece" and pl.json()["latitude"] == 16.24)
    from app.services.pricing_engine import billable_kg_for as _bkg
    check("transport billable-kg converts quintal to 100kg",
          str(_bkg("quintal", 2)) == "200.000" and str(_bkg("kg", 5)) == "5.000")
    # Seller "Other": add a product that isn't in the catalog yet.
    nc = client.post("/api/catalog/commodities", headers=hdr(farmer),
                     json={"name": "Dragon Fruit"})
    check("farmer can add a new product", nc.status_code == 201 and nc.json()["name"] == "Dragon Fruit")
    check("new product appears in the catalog",
          any(c["name"] == "Dragon Fruit" for c in client.get("/api/catalog/commodities").json()))
    check("adding the same product reuses it (no duplicate)",
          client.post("/api/catalog/commodities", headers=hdr(farmer),
                      json={"name": "dragon fruit"}).json()["id"] == nc.json()["id"])

    # --- Catalog management: staff add + removal request/approve workflow ---
    ag = client.post("/api/catalog/commodities", headers=hdr(agent),
                     json={"name": "Jackfruit", "category": "fruit"})
    check("field agent can add a product", ag.status_code == 201 and ag.json()["name"] == "Jackfruit")
    jid = ag.json()["id"]
    check("buyer cannot add a product",
          client.post("/api/catalog/commodities", headers=hdr(buyer), json={"name": "Zucchini"}).status_code == 403)
    rq = client.post(f"/api/catalog/commodities/{jid}/request-deletion", headers=hdr(manager),
                     json={"reason": "duplicate entry"})
    check("field leader can request product removal", rq.status_code == 200 and rq.json()["pending_deletion"] is True)
    check("farmer cannot request product removal",
          client.post(f"/api/catalog/commodities/{jid}/request-deletion", headers=hdr(farmer),
                      json={"reason": "x"}).status_code == 403)
    check("duplicate removal request is blocked",
          client.post(f"/api/catalog/commodities/{jid}/request-deletion", headers=hdr(manager),
                      json={"reason": "again"}).status_code == 409)
    check("non-superadmin cannot approve removal",
          client.post(f"/api/catalog/commodities/{jid}/deletion-decision", headers=hdr(manager),
                      json={"approve": True}).status_code == 403)
    mgmt = client.get("/api/catalog/commodities/manage", headers=hdr(manager)).json()
    mrow = next(c for c in mgmt if c["id"] == jid)
    check("manage list flags the pending removal + requester",
          mrow["pending_deletion"] and mrow.get("deletion_requested_by_name"))
    check("pending product is still in the active catalog",
          any(c["id"] == jid for c in client.get("/api/catalog/commodities").json()))
    ap = client.post(f"/api/catalog/commodities/{jid}/deletion-decision", headers=hdr(superadmin),
                     json={"approve": True})
    check("superadmin approves removal", ap.status_code == 200 and ap.json()["active"] is False)
    check("removed product disappears from the active catalog",
          not any(c["id"] == jid for c in client.get("/api/catalog/commodities").json()))
    check("approving with no pending request 400s",
          client.post(f"/api/catalog/commodities/{jid}/deletion-decision", headers=hdr(superadmin),
                      json={"approve": True}).status_code == 400)
    check("superadmin can restore a removed product",
          client.post(f"/api/catalog/commodities/{jid}/restore", headers=hdr(superadmin)).json()["active"] is True)
    check("restored product reappears in the catalog",
          any(c["id"] == jid for c in client.get("/api/catalog/commodities").json()))
    client.post(f"/api/catalog/commodities/{jid}/request-deletion", headers=hdr(manager),
                json={"reason": "reconsider"})
    rej = client.post(f"/api/catalog/commodities/{jid}/deletion-decision", headers=hdr(superadmin),
                      json={"approve": False})
    check("superadmin can reject a removal (product stays active)",
          rej.status_code == 200 and rej.json()["active"] is True and rej.json()["pending_deletion"] is False)
    # A sample video attaches as video media (separate from the 3 image requirement).
    client.post(f"/api/listings/{listing['id']}/media", headers=hdr(farmer),
                json={"object_key": "sample/paddy-clip.mp4", "media_type": "video"})
    check("listing exposes a sample video",
          client.get(f"/api/listings/{listing['id']}").json()["video"] == "sample/paddy-clip.mp4")

    # Publishing requires at least 3 sample images.
    r = client.post(f"/api/listings/{listing['id']}/publish", headers=hdr(farmer))
    check("publish blocked without 3 images", r.status_code == 400)
    for n in range(1, 4):
        client.post(f"/api/listings/{listing['id']}/media", headers=hdr(farmer),
                    json={"object_key": f"sample/paddy-test-{n}.svg", "media_type": "image"})
    r = client.post(f"/api/listings/{listing['id']}/publish", headers=hdr(farmer))
    check("listing published after images", r.json()["status"] == "open")

    # Remove one photo (seller can delete/replace individual media).
    lj = client.get(f"/api/listings/{listing['id']}").json()
    mid = lj["media"][0]["id"]
    check("listing media exposes an id", isinstance(mid, int))
    dr = client.delete(f"/api/listings/{listing['id']}/media/{mid}", headers=hdr(farmer))
    check("seller removes one listing photo",
          dr.status_code == 200 and len(dr.json()["media"]) == len(lj["media"]) - 1)
    check("a non-owner cannot delete someone's listing media",
          client.delete(f"/api/listings/{listing['id']}/media/{lj['media'][1]['id']}",
                        headers=hdr(buyer)).status_code in (403, 404))
    # Re-add so the listing still has its 3 images for later steps.
    client.post(f"/api/listings/{listing['id']}/media", headers=hdr(farmer),
                json={"object_key": "sample/paddy-test-readd.svg", "media_type": "image"})

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
    # Offline photo-evidence sync path: the agent uploads an inspection photo and
    # gets an object_key to attach as evidence (what the field app flushes on sync).
    import base64 as _b64
    _png = _b64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
    up = client.post("/api/media/upload", headers=hdr(agent),
                     files={"file": ("inspection.png", _png, "image/png")})
    check("agent uploads an inspection photo", up.status_code == 200 and bool(up.json().get("object_key")))

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
    r = client.post(f"/api/orders/{order_id}/packing-complete", headers=hdr(agent),
                    json={"packing_video": "sample/packing-clip.mp4"})
    check("packing complete -> ready_for_pickup", r.json()["order"]["status"] == "ready_for_pickup")
    check("lot id issued", r.json()["lot_id"].startswith("LOT-"))
    check("packing video attached to the order",
          r.json()["order"]["packing_video"] == "sample/packing-clip.mp4")
    check("buyer sees the packing video on the order",
          client.get(f"/api/orders/{order_id}", headers=hdr(buyer)).json()["packing_video"]
          == "sample/packing-clip.mp4")

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
    check("tracking exposes navigation (route + maps link)",
          "nav_url" in trk and "from_coord" in trk and "to_place" in trk)
    check("tracking estimates an ETA", trk["eta"] is not None)
    check("buyer sees the delivery code out-for-delivery", bool(trk.get("delivery_code")))
    trk_s = client.get(f"/api/orders/{order_id}/tracking", headers=hdr(farmer)).json()
    check("seller does not see the delivery code", "delivery_code" not in trk_s)

    # Live courier tracking: the courier app shares GPS; the buyer watches it live.
    r = client.post(f"/api/transport/orders/{order_id}/location", headers=hdr(transport),
                    json={"lat": 16.3, "lng": 80.45})
    check("courier posts live location", r.json().get("ok") is True)
    check("bad coordinates rejected",
          client.post(f"/api/transport/orders/{order_id}/location", headers=hdr(transport),
                      json={"lat": 999, "lng": 0}).status_code == 400)
    check("buyer cannot post courier location",
          client.post(f"/api/transport/orders/{order_id}/location", headers=hdr(buyer),
                      json={"lat": 16.3, "lng": 80.4}).status_code == 403)
    trk_live = client.get(f"/api/orders/{order_id}/tracking", headers=hdr(buyer)).json()
    check("tracking shows the live courier position",
          bool(trk_live.get("courier_location")) and trk_live["courier_location"]["lat"] == 16.3)
    check("tracking computes courier distance to destination",
          trk_live["courier_location"].get("distance_km") is not None)
    check("tracking gives a live ETA in minutes",
          trk_live["courier_location"].get("eta_minutes") is not None)
    # The transport partner can open the order + its tracking (shared delivery
    # pool) — they are neither buyer, seller, nor office staff.
    check("transport partner can view the order detail",
          client.get(f"/api/orders/{order_id}", headers=hdr(transport)).status_code == 200)
    trk_t = client.get(f"/api/orders/{order_id}/tracking", headers=hdr(transport))
    check("transport partner can view live tracking", trk_t.status_code == 200)
    # Drive the courier onto the delivery address -> buyer gets a 'nearby' ping.
    to_coord = trk_live.get("to_coord")
    if to_coord:
        rn = client.post(f"/api/transport/orders/{order_id}/location", headers=hdr(transport),
                         json={"lat": to_coord["lat"], "lng": to_coord["lng"]}).json()
        check("courier-nearby distance computed at the door",
              rn.get("distance_km") is not None and rn["distance_km"] <= 2)
        bnotes = client.get("/api/auth/notifications", headers=hdr(buyer)).json()
        check("buyer pinged that the courier is nearby",
              any("nearby" in (str(n.get("title", "")) + str(n.get("body", ""))).lower() for n in bnotes))

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

    print("\n== Transport earnings + payout (delivery partner) ==")
    te = client.get("/api/transport/earnings", headers=hdr(transport)).json()
    check("settlement accrued a transport payout",
          te["trip_count"] >= 1 and float(te["pending_total"]) > 0)
    check("transport earnings lists the settled trip",
          any(t["public_id"] for t in te["trips"]))
    check("transport earnings CSV served",
          client.get("/api/transport/earnings.csv", headers=hdr(transport)).status_code == 200)

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
    # Buyer-trust: rating surfaces where a buyer browses/decides, not just on the raw listing.
    pcards = client.get("/api/listings/products").json()
    pcard = next((p for p in pcards if p["commodity_id"] == paddy["id"]), None)
    check("product card carries seller rating", pcard is not None
          and pcard.get("seller_rating") is not None and pcard["seller_rating_count"] >= 1)
    # Buyers can rank + filter the marketplace grid by seller rating.
    rated_sorted = client.get("/api/listings/products", params={"sort": "rating"}).json()
    rvals = [p["seller_rating"] for p in rated_sorted if p["seller_rating"] is not None]
    check("rating sort returns highest-rated first", rvals == sorted(rvals, reverse=True))
    check("rating sort puts unrated products last",
          all(p["seller_rating"] is not None for p in rated_sorted[:len(rvals)]))
    hi = client.get("/api/listings/products", params={"min_rating": 4}).json()
    check("min_rating filter keeps only 4-star-plus products",
          all((p["seller_rating"] or 0) >= 4 for p in hi) and any(p["commodity_id"] == paddy["id"] for p in hi))
    prod2 = client.get(f"/api/listings/products/{paddy['id']}").json()
    check("product detail exposes aggregate seller rating",
          prod2.get("seller_rating") is not None and prod2["seller_rating_count"] >= 1)
    check("product detail offerings carry per-seller rating",
          any(o.get("seller_rating") == 5.0 for o in prod2["offerings"]))
    # Review depth: actual comments surface at the decision point, sellers sortable by rating.
    check("product detail offering carries latest review comment",
          any((o.get("top_review") or {}).get("comment") for o in prod2["offerings"]))
    rev = client.get("/api/reviews", params={
        "subject_type": "farmer", "subject_id": lst["seller"]["id"]}).json()
    check("public reviews list returns written comments",
          any(r.get("comment") for r in rev["reviews"]))
    disc = client.get("/api/listings/discovery").json()
    check("discovery featured cards expose rating field",
          all("seller_rating" in p for p in disc["featured"]))
    check("discovery fresh cards expose rating field",
          all("seller_rating" in f for f in disc["fresh"]))
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

    # Government photo-ID proof for identity verification (add -> list -> remove).
    ip = client.post("/api/auth/me/id-proof", headers=hdr(newf),
                     json={"object_key": "sample/aadhaar-front.jpg", "doc_type": "aadhaar"})
    check("id-proof upload recorded", ip.status_code == 200 and len(ip.json()["id_documents"]) == 1)
    check("id-proof exposes a viewable url + type",
          ip.json()["id_documents"][0]["doc_type"] == "aadhaar"
          and ip.json()["id_documents"][0]["url"])
    rp = client.request("DELETE", "/api/auth/me/id-proof", headers=hdr(newf),
                        json={"object_key": "sample/aadhaar-front.jpg"})
    check("id-proof removal clears the document",
          rp.status_code == 200 and len(rp.json()["id_documents"]) == 0)

    # PRIVATE KYC media: an ID doc must not be reachable at a public URL — only
    # through a signed, expiring /media/secure link bound to that exact file.
    pm = client.post("/api/media/upload", headers=hdr(newf),
                     files={"file": ("id.png", b"\x89PNG\r\n\x1a\n" + b"0" * 48, "image/png")},
                     data={"private": "true"})
    check("private upload accepted", pm.status_code == 200)
    pkey = pm.json()["object_key"]
    if pkey.startswith("priv/"):  # local-disk pilot path (Cloudinary returns an https url)
        check("private file refused by the public media route",
              client.get(f"/api/media/file/{pkey}").status_code == 403)
        ipp = client.post("/api/auth/me/id-proof", headers=hdr(newf),
                          json={"object_key": pkey, "doc_type": "pan"})
        doc = next(d for d in ipp.json()["id_documents"] if d["object_key"] == pkey)
        check("ID doc exposes a signed /media/secure link", "/media/secure/" in (doc["url"] or ""))
        from urllib.parse import parse_qs, urlparse
        tok = parse_qs(urlparse(doc["url"]).query).get("token", [""])[0]
        check("signed link serves the private file",
              client.get(f"/api/media/secure/{pkey}", params={"token": tok}).status_code == 200)
        check("secure route rejects a bad token",
              client.get(f"/api/media/secure/{pkey}", params={"token": "nope"}).status_code == 403)
        check("secure route rejects a missing token",
              client.get(f"/api/media/secure/{pkey}").status_code == 403)
        # Clean up so it doesn't affect later id_documents assertions.
        client.request("DELETE", "/api/auth/me/id-proof", headers=hdr(newf),
                       json={"object_key": pkey})

    # Profile photo can be cleared by sending an empty avatar key.
    client.patch("/api/auth/me", headers=hdr(newf), json={"avatar_object_key": "sample/x.jpg"})
    cleared = client.patch("/api/auth/me", headers=hdr(newf), json={"avatar_object_key": ""}).json()
    check("avatar can be removed", cleared.get("avatar_url") is None)

    # SMS OTP via 2Factor.in: delivers our code through 2Factor's pre-approved OTP
    # template (no DLT on our side). Stub httpx so no real SMS is sent.
    from app.services import sms as _sms
    from app.core.config import settings as _st
    _save = (_st.sms_provider, _st.sms_api_key, _st.twofactor_template_name, _sms.httpx.get)
    try:
        _st.sms_provider, _st.sms_api_key, _st.twofactor_template_name = "2factor", "KEYXYZ", ""
        cap = {}

        class _R:
            status_code = 200; text = '{"Status":"Success"}'
            def json(self):  # noqa: D401
                return {"Status": "Success", "Details": "sid"}
        _sms.httpx.get = lambda url, **kw: (cap.__setitem__("url", url), _R())[1]
        ok = _sms.send_otp("+919876543210", "4321")
        check("2factor OTP send returns ok", ok is True)
        check("2factor OTP builds the correct URL (10-digit, code in path)",
              cap.get("url") == "https://2factor.in/API/V1/KEYXYZ/SMS/9876543210/4321")

        class _E:
            status_code = 200; text = '{"Status":"Error"}'
            def json(self):
                return {"Status": "Error", "Details": "Invalid Key"}
        _sms.httpx.get = lambda url, **kw: _E()
        check("2factor failure fails safe (returns False, no raise)",
              _sms.send_otp("919876543210", "1") is False)
    finally:
        _st.sms_provider, _st.sms_api_key, _st.twofactor_template_name, _sms.httpx.get = _save

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
    # Razorpay-shaped webhook: X-Razorpay-Signature + {event, payload.payment.entity}.
    rz = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
        "order_id": "order_test", "notes": {"order_public_id": "NOPE"}}}}}).encode()
    rzr = client.post("/api/payments/webhook", content=rz,
                      headers={"x-razorpay-signature": _pay.sign(rz)})
    check("razorpay-shaped webhook is parsed + verified (unknown order -> 404)",
          rzr.status_code == 404)
    check("razorpay webhook with a bad signature is rejected",
          client.post("/api/payments/webhook", content=rz,
                      headers={"x-razorpay-signature": "nope"}).status_code == 401)

    print("\n== Reorder + admin KYC queue ==")
    r = client.post(f"/api/orders/{order_id}/reorder", headers=hdr(buyer))
    check("buyer reorders -> new offer", r.json().get("reorderable") is True and r.json().get("offer_id"))
    myoffers = client.get("/api/offers", headers=hdr(buyer)).json()
    check("reorder offer appears in buyer's offers", any(o["id"] == r.json()["offer_id"] for o in myoffers))

    # Re-submit an ID proof so the reviewer queue can surface it for review.
    client.post("/api/auth/me/id-proof", headers=hdr(newf),
                json={"object_key": "sample/aadhaar-front.jpg", "doc_type": "aadhaar"})
    q = client.get("/api/admin/kyc", headers=hdr(superadmin)).json()
    check("new farmer appears in KYC queue", any(x["phone"] == "919000000031" for x in q))
    target = next(x for x in q if x["phone"] == "919000000031")
    check("KYC queue surfaces the submitted ID documents for review",
          isinstance(target.get("id_documents"), list)
          and len(target["id_documents"]) == 1
          and target["id_documents"][0].get("url")
          and target["id_documents"][0].get("doc_type") == "aadhaar")
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
    # Single login: a farmer shops too — they can post a buyer RFQ with the same account.
    rf = client.post("/api/rfqs", headers=hdr(farmer), json={
        "commodity_id": paddy["id"], "grade_spec_id": grade_id,
        "requested_qty": 50, "target_price": 24, "destination_mandal_id": mandal_id,
    })
    check("farmer can post a buyer RFQ (one login, sells + buys)", rf.status_code == 201)
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

    # --- Enhanced RFQ: price range, source areas, comment thread, escalation ---
    er = client.post("/api/rfqs", headers=hdr(buyer), json={
        "commodity_id": paddy["id"], "requested_qty": 100,
        "price_min": 20, "price_max": 26, "source_mandal_ids": [mandal_id],
        "needed_by": "2027-01-15", "note": "Need clean, dry paddy."})
    check("RFQ accepts a price range + source areas + needed-by date",
          er.status_code == 201 and er.json()["price_min"] == "20.00"
          and er.json()["price_max"] == "26.00" and er.json()["source_mandal_ids"] == [mandal_id]
          and er.json()["needed_by"] == "2027-01-15")
    erid = er.json()["id"]
    thread = client.get(f"/api/rfqs/{erid}/comments", headers=hdr(buyer)).json()
    check("request thread has a system entry + the buyer's note",
          any(c["is_system"] for c in thread) and any(c["body"] == "Need clean, dry paddy." for c in thread))
    check("farmer can comment on a request",
          client.post(f"/api/rfqs/{erid}/comments", headers=hdr(farmer),
                      json={"body": "I can supply 100 kg."}).status_code == 201)
    client.post(f"/api/rfqs/{erid}/offers", headers=hdr(farmer),
                json={"price_per_unit": 24, "quantity": 100})
    thread2 = client.get(f"/api/rfqs/{erid}/comments", headers=hdr(farmer)).json()
    check("an offer is recorded on the request thread",
          any(c["is_system"] and "offered" in c["body"] for c in thread2))
    other = login(client, "919000000091", role="buyer_business", name="Other Biz")
    check("a non-participant buyer cannot read another's request thread",
          client.get(f"/api/rfqs/{erid}/comments", headers=hdr(other)).status_code == 403)
    # Escalation: backdate an untouched request, then run the scheduler job.
    esc = client.post("/api/rfqs", headers=hdr(buyer), json={
        "commodity_id": paddy["id"], "requested_qty": 30, "source_mandal_ids": [mandal_id]}).json()
    from datetime import datetime as _dt
    from datetime import timedelta as _td
    from datetime import timezone as _tz

    from app.core.database import SessionLocal
    from app.models.marketplace import RFQ as _RFQ
    from app.services.scheduler import escalate_stale_rfqs
    _db = SessionLocal()
    try:
        _db.get(_RFQ, esc["id"]).created_at = _dt.now(_tz.utc) - _td(hours=48)
        _db.commit()
        n_esc = escalate_stale_rfqs(_db)
    finally:
        _db.close()
    check("a stale request escalates to agents", n_esc >= 1)
    check("the escalated request is flagged",
          client.get(f"/api/rfqs/{esc['id']}").json()["escalated"] is True)

    # --- Barcode bag tracking: generate, scan through stages, validate, track ---
    bags = client.post(f"/api/orders/{rfq_order_id}/bags", headers=hdr(agent),
                       json={"count": 3, "weights": [50, 50, 100]})
    check("agent generates bags for an order", bags.status_code == 201 and len(bags.json()) == 3)
    blist = bags.json()
    bc0 = blist[0]["bag_code"]
    check("bag code is AGRI-{order}-BAG-NN", bc0 == f"AGRI-{rfq_order_id}-BAG-01")
    check("bag generation is idempotent",
          len(client.post(f"/api/orders/{rfq_order_id}/bags", headers=hdr(agent),
                          json={"count": 9}).json()) == 3)
    check("out-of-sequence scan is blocked (deliver before pickup)",
          client.post("/api/bags/scan", headers=hdr(transport),
                      json={"bag_code": bc0, "stage": "delivery"}).status_code == 409)
    check("invalid barcode rejected",
          client.post("/api/bags/scan", headers=hdr(agent),
                      json={"bag_code": "AGRI-999999-BAG-99", "stage": "pickup"}).status_code == 404)
    check("wrong role for a stage is blocked (transporter can't do pickup)",
          client.post("/api/bags/scan", headers=hdr(transport),
                      json={"bag_code": bc0, "stage": "pickup"}).status_code == 403)
    sp = client.post("/api/bags/scan", headers=hdr(agent),
                     json={"bag_code": bc0, "stage": "pickup", "lat": 16.2, "lng": 80.6})
    check("agent scans pickup -> picked_up", sp.status_code == 200 and sp.json()["bag"]["status"] == "picked_up")
    check("duplicate scan is blocked",
          client.post("/api/bags/scan", headers=hdr(agent),
                      json={"bag_code": bc0, "stage": "pickup"}).status_code == 409)
    check("leader scans collection -> at_collection",
          client.post("/api/bags/scan", headers=hdr(manager),
                      json={"bag_code": bc0, "stage": "collection"}).json()["bag"]["status"] == "at_collection")
    check("transporter scans loading -> in_transit",
          client.post("/api/bags/scan", headers=hdr(transport),
                      json={"bag_code": bc0, "stage": "loading"}).json()["bag"]["status"] == "in_transit")
    check("transporter scans delivery -> delivered",
          client.post("/api/bags/scan", headers=hdr(transport),
                      json={"bag_code": bc0, "stage": "delivery"}).json()["bag"]["status"] == "delivered")
    det = client.get(f"/api/bags/{bc0}", headers=hdr(agent)).json()
    check("bag detail shows the full scan history", len(det["scans"]) >= 4)
    pub = client.get(f"/api/track/{bc0}")
    check("public track works without auth and hides farmer PII",
          pub.status_code == 200 and len(pub.json()["ladder"]) == 5
          and "farmer_name" not in pub.json() and pub.json()["status"] == "delivered")
    check("superadmin can audit bags",
          any(b["bag_code"] == bc0 for b in client.get("/api/bags", headers=hdr(superadmin)).json()))
    check("bag stats expose a delivered count",
          client.get("/api/bags/stats", headers=hdr(superadmin)).json()["delivered"] >= 1)
    corr = client.post(f"/api/bags/{blist[1]['bag_code']}/correct", headers=hdr(superadmin),
                       json={"to_status": "delivered", "reason": "scan failed at gate"})
    check("superadmin can manually correct a bag status",
          corr.status_code == 200 and corr.json()["status"] == "delivered")
    check("non-superadmin cannot correct a bag",
          client.post(f"/api/bags/{blist[2]['bag_code']}/correct", headers=hdr(manager),
                      json={"to_status": "delivered", "reason": "x"}).status_code == 403)
    cs = client.get("/api/bags/collection-summary", headers=hdr(manager)).json()
    check("collection summary flags a mismatch (expected vs arrived)",
          isinstance(cs, list) and any(r["mismatch"] for r in cs))
    # Profile: address + farm fields + masked KYC.
    pm = client.patch("/api/auth/me", headers=hdr(farmer), json={
        "district": "Guntur", "pincode": "522201", "farm_size": 5, "crops_grown": ["Paddy"],
        "soil_type": "Black", "irrigation_type": "Canal", "experience_years": 10,
        "aadhaar": "999988887777"})
    check("patch_me saves address + farm fields", pm.status_code == 200)
    me2 = client.get("/api/auth/me", headers=hdr(farmer)).json()
    check("me exposes farm fields + masked aadhaar + district",
          me2["farmer"]["farm_size"] == "5.00" and (me2.get("aadhaar_masked") or "").endswith("7777")
          and me2["district"] == "Guntur")

    # The RFQ-based order (no listing) still runs the full lifecycle & prices.
    client.post(f"/api/orders/{rfq_order_id}/assign-inspection", headers=hdr(manager), json={"agent_id": 3})
    client.post(f"/api/agent/orders/{rfq_order_id}/inspection", headers=hdr(agent),
                json={"gross_weight": 200, "tare_weight": 0, "outcome": "pass"})
    client.post(f"/api/orders/{rfq_order_id}/buyer-approve", headers=hdr(buyer))
    # Checkout with a saved delivery address: the server resolves the destination
    # mandal from it and persists the street line for the courier. No route_km ->
    # the server computes distance from mandal coordinates.
    chk_addr = client.post("/api/auth/addresses", headers=hdr(buyer),
                           json={"label": "Shop", "mandal_id": mandal_id,
                                 "address_line": "12-3-45 Market Rd"}).json()
    r = client.post(f"/api/orders/{rfq_order_id}/confirm-quote", headers=hdr(buyer),
                    json={"address_id": chk_addr["id"]})
    rq = r.json()["quote"]
    check("RFQ order prices without a listing", r.json()["status"] == "payment_pending"
          and rq["product_value"] == "4800.00")  # 24 * 200
    check("RFQ route_km auto-computed", rq.get("route_km_source") in ("haversine", "default"))
    terms_after = r.json()["accepted_terms"]
    check("checkout persists delivery destination from saved address",
          terms_after.get("destination_mandal_id") == mandal_id
          and terms_after.get("delivery_address_line") == "12-3-45 Market Rd")
    trk = client.get(f"/api/orders/{rfq_order_id}/tracking", headers=hdr(buyer)).json()
    check("tracking surfaces the delivery address line + label",
          trk.get("to_address_line") == "12-3-45 Market Rd" and trk.get("to_label") == "Shop")
    r = client.post(f"/api/orders/{rfq_order_id}/pay",
                    headers={**hdr(buyer), "Idempotency-Key": "rfq-pay-1"})
    check("RFQ order paid", r.json()["status"] == "paid")

    acct = client.get("/api/admin/ledger/accounts", headers=hdr(superadmin)).json()
    check("ledger balanced across both orders", acct["balanced"] is True)

    print("\n== Superadmin GMV reports ==")
    rep = client.get("/api/admin/reports", headers=hdr(superadmin)).json()
    check("report has total GMV", float(rep["total_gmv"]) > 0)
    check("report breaks down by commodity", len(rep["by_commodity"]) >= 1)
    check("report breaks down by state", len(rep["by_state"]) >= 1)

    print("\n== Market prices (today's govt prices, all-India, product-wise) ==")
    mp = client.get("/api/market-prices").json()
    check("market prices seeded", len(mp) > 0 and "disclaimer" in mp[0] and "state" in mp[0])
    pc = client.get("/api/market-prices/commodities").json()
    check("priced commodities list has market/state counts",
          any(c["commodity"] == "Paddy" and c["market_count"] >= 2 and c["state_count"] >= 2 for c in pc))
    check("priced commodities carry a category (for filtering)",
          all("category" in c for c in pc)
          and any(c["commodity"] == "Paddy" and c["category"] == "cereal" for c in pc))
    ai = client.get("/api/market-prices/all-india", params={"commodity": "Paddy"}).json()
    check("all-India price view groups a commodity by state",
          ai["commodity"] == "Paddy" and len(ai["states"]) >= 2 and ai["modal_avg"] is not None)
    filtered = client.get("/api/market-prices", params={"commodity": "Paddy", "state": "Punjab"}).json()
    check("prices filter by commodity + state",
          len(filtered) >= 1 and all(p["state"] == "Punjab" and p["commodity"] == "Paddy" for p in filtered))

    print("\n== Market price feed (data.gov.in / AGMARKNET) ==")
    # Unconfigured by default: the admin refresh reports "not configured" cleanly.
    rf = client.post("/api/admin/prices/refresh", headers=hdr(superadmin)).json()
    check("refresh reports not-configured when no feed key", rf.get("configured") is False)
    check("refresh is superadmin-only",
          client.post("/api/admin/prices/refresh", headers=hdr(farmer)).status_code == 403)
    # Exercise the parse/upsert path directly with a synthetic AGMARKNET payload.
    from app.core.database import SessionLocal  # noqa: E402
    from app.services import prices_feed  # noqa: E402
    _db = SessionLocal()
    try:
        res = prices_feed.refresh_prices(_db, records=[
            {"state": "Kerala", "market": "Kochi", "commodity": "Black Pepper",
             "variety": "Garbled", "min_price": "60000", "max_price": "66000",
             "modal_price": "63000", "arrival_date": "2026-11-11"},
            {"state": "Kerala", "market": "Kochi", "commodity": "Black Pepper",
             "variety": "Garbled", "min_price": "61000", "max_price": "67000",
             "modal_price": "64000", "arrival_date": "2026-11-12"},  # same key -> update
            {"commodity": "", "market": "", "modal_price": None},  # unusable -> skipped
        ])
        _db.commit()
    finally:
        _db.close()
    check("feed parses + upserts valid rows, skips junk", res["parsed"] == 2 and res["new"] == 1)
    check("feed is idempotent on a repeated key (1 new row, not 2)", res["upserted"] == 2)
    pepper = client.get("/api/market-prices", params={"commodity": "Black Pepper"}).json()
    check("upserted feed row is served + latest price wins",
          len(pepper) == 1 and pepper[0]["modal_price"] == "64000.00"
          and pepper[0]["source_name"] == prices_feed.SOURCE_NAME)
    _db2 = SessionLocal()
    try:
        check("live refresh not due when provider unconfigured", prices_feed.is_refresh_due(_db2) is False)
    finally:
        _db2.close()
    sr = client.post("/api/admin/scheduler/run", headers=hdr(superadmin)).json()
    check("scheduler run reports prices + meeting-reminder keys",
          all(k in sr for k in ("digests_sent", "prices_refreshed", "meeting_reminders")))
    st = client.get("/api/admin/prices/status", headers=hdr(superadmin)).json()
    check("price-feed status reports config + counts",
          "configured" in st and st["row_count"] >= 1 and "feed_is_stale" in st
          and "stale_rows" in st)

    print("\n== Team console (field leader / manager) ==")
    ov = client.get("/api/team/overview", headers=hdr(manager)).json()
    check("team overview lists field agents + pipeline",
          isinstance(ov["agents"], list) and any(a["name"] for a in ov["agents"])
          and isinstance(ov["pipeline"], list))
    check("team overview reports counts",
          "unassigned" in ov and "active_orders" in ov)
    check("non-lead cannot read the team console",
          client.get("/api/team/overview", headers=hdr(farmer)).status_code == 403)

    print("\n== Field-leader targets ==")
    from datetime import date as _date, timedelta as _td  # noqa: E402
    agent_id = client.get("/api/auth/me", headers=hdr(agent)).json()["id"]
    start = (_date.today() - _td(days=1)).isoformat()
    end = (_date.today() + _td(days=1)).isoformat()
    r = client.post("/api/team/targets", headers=hdr(manager), json={
        "agent_id": agent_id, "metric": "inspections", "target_value": 3,
        "period_start": start, "period_end": end, "note": "Weekly goal"})
    check("leader sets a target for an agent", r.status_code == 200)
    tgt = r.json()
    # The agent already completed an inspection earlier today -> progress counts it.
    check("target shows live progress from the agent's inspections",
          tgt["progress"] >= 1 and tgt["target_value"] == 3 and 0 < tgt["pct"] <= 100)
    check("target lists for the leader",
          any(t["id"] == tgt["id"] for t in client.get("/api/team/targets", headers=hdr(manager)).json()))
    check("agent sees their own target",
          any(t["id"] == tgt["id"] for t in client.get("/api/team/my-targets", headers=hdr(agent)).json()))
    check("bad metric rejected",
          client.post("/api/team/targets", headers=hdr(manager), json={
              "agent_id": agent_id, "metric": "bogus", "target_value": 1,
              "period_start": start, "period_end": end}).status_code == 400)
    check("non-lead cannot set targets",
          client.post("/api/team/targets", headers=hdr(farmer), json={
              "agent_id": agent_id, "metric": "inspections", "target_value": 1,
              "period_start": start, "period_end": end}).status_code == 403)
    up = client.patch(f"/api/team/targets/{tgt['id']}", headers=hdr(manager),
                      json={"target_value": 10}).json()
    check("target value updated + pct recomputed", up["target_value"] == 10 and up["pct"] <= 30)

    print("\n== Field-leader meetings ==")
    r = client.post("/api/team/meetings", headers=hdr(manager), json={
        "title": "Mandal weekly sync", "scheduled_at": "2026-11-15T10:00",
        "location": "Guntur office", "agenda": "Targets + pending verifications",
        "attendee_ids": [agent_id]})
    check("leader schedules a meeting", r.status_code == 200)
    mtg = r.json()
    check("meeting records attendees", mtg["attendee_count"] == 1 and mtg["status"] == "scheduled")
    check("meeting lists for the leader",
          any(m["id"] == mtg["id"] for m in client.get("/api/team/meetings", headers=hdr(manager)).json()))
    check("invited agent sees the meeting",
          any(m["id"] == mtg["id"] for m in client.get("/api/team/my-meetings", headers=hdr(agent)).json()))
    check("agent notified of the meeting",
          any(n["object_type"] == "meeting"
              for n in client.get("/api/auth/notifications", headers=hdr(agent)).json()))
    done = client.patch(f"/api/team/meetings/{mtg['id']}", headers=hdr(manager),
                        json={"status": "done", "notes": "All targets reviewed",
                              "attended_ids": [agent_id]}).json()
    check("meeting marked done with minutes",
          done["status"] == "done" and done["notes"] == "All targets reviewed")
    check("non-lead cannot schedule a meeting",
          client.post("/api/team/meetings", headers=hdr(farmer), json={
              "title": "x", "scheduled_at": "2026-11-15T10:00"}).status_code == 403)

    print("\n== Team leaderboard + meeting reminders ==")
    lb = client.get("/api/team/leaderboard", headers=hdr(manager), params={"period": "month"}).json()
    check("leaderboard ranks agents with attainment",
          lb["period"] == "month" and len(lb["rows"]) >= 1 and lb["rows"][0]["rank"] == 1
          and "attainment_pct" in lb["rows"][0])
    row = next((r for r in lb["rows"] if r["agent_id"] == agent_id), None)
    check("leaderboard reflects the agent's inspections + meeting attendance",
          row is not None and row["inspections"] >= 1
          and row["meetings_invited"] >= 1 and row["meetings_attended"] >= 1)
    check("non-lead cannot read the leaderboard",
          client.get("/api/team/leaderboard", headers=hdr(farmer)).status_code == 403)
    check("leaderboard CSV served",
          client.get("/api/team/leaderboard.csv", headers=hdr(manager), params={"period": "month"}).status_code == 200)
    tr = client.get("/api/team/trends", headers=hdr(manager), params={"weeks": 4}).json()
    check("trends returns a weekly activity series",
          len(tr["series"]) == 4 and "inspections" in tr["series"][0] and "orders" in tr["series"][0])

    # Pre-meeting reminders: an imminent meeting reminds its attendees once.
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td3  # noqa: E402
    soon = (_dt.now(_tz.utc) + _td3(hours=2)).isoformat()
    client.post("/api/team/meetings", headers=hdr(manager),
                json={"title": "Imminent sync", "scheduled_at": soon, "attendee_ids": [agent_id]})
    from app.services.scheduler import raise_meeting_reminders  # noqa: E402
    _db3 = SessionLocal()
    try:
        n1 = raise_meeting_reminders(_db3)
        n2 = raise_meeting_reminders(_db3)
    finally:
        _db3.close()
    check("reminder raised for an imminent meeting", n1 >= 1)
    check("reminder is idempotent (reminded once)", n2 == 0)

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
    r = client.get(f"/api/orders/{order_id}/invoice.pdf", headers=hdr(transport))
    check("non-party cannot fetch invoice", r.status_code == 403)

    print("\n== Scheduled payout batches (accrue -> disburse) ==")
    po = client.get("/api/admin/payouts", headers=hdr(superadmin)).json()
    check("settled order accrued a pending payout", po["pending_count"] >= 1 and float(po["pending_total"]) > 0)

    # Payouts disburse ONLY to verified payout accounts.
    r = client.post("/api/admin/payouts/run", headers=hdr(superadmin), json={})
    check("payout run blocked while no payee account is verified", r.status_code == 409)
    client.put("/api/auth/payout-account", headers=hdr(farmer),
               json={"method": "upi", "upi_id": "ravi@okaxis"})
    client.put("/api/auth/payout-account", headers=hdr(transport),
               json={"method": "bank", "account_name": "Kisan Logistics",
                     "account_number": "123456789012", "ifsc": "HDFC0001234"})
    queue = client.get("/api/admin/payout-accounts", headers=hdr(superadmin)).json()
    check("unverified accounts show in the verify queue", len(queue) >= 2)
    check("verify queue masks bank account numbers",
          all(a["method"] != "bank" or (a["account_number_masked"] or "").startswith("****") for a in queue))
    po_blocked = client.get("/api/admin/payouts", headers=hdr(superadmin)).json()
    check("overview flags payouts blocked on unverified accounts", po_blocked.get("blocked_unverified", 0) >= 1)
    r = client.post("/api/admin/payouts/run", headers=hdr(superadmin), json={})
    check("payout run still blocked while accounts unverified", r.status_code == 409)
    check("non-finance cannot verify payout accounts",
          client.post(f"/api/admin/payout-accounts/{queue[0]['user_id']}/verify",
                      headers=hdr(agent), json={"approve": True}).status_code in (401, 403))
    for a in queue:
        vr = client.post(f"/api/admin/payout-accounts/{a['user_id']}/verify",
                         headers=hdr(superadmin), json={"approve": True})
        check("admin verifies a payout account", vr.json()["verified"] is True)
    check("nothing blocked after verification",
          client.get("/api/admin/payouts", headers=hdr(superadmin)).json().get("blocked_unverified", 0) == 0)

    r = client.post("/api/admin/payouts/run", headers=hdr(superadmin), json={})
    check("payout batch disburses pending", r.json()["payout_count"] >= 1 and float(r.json()["total_amount"]) > 0)
    po2 = client.get("/api/admin/payouts", headers=hdr(superadmin)).json()
    check("no pending payouts after batch", po2["pending_count"] == 0)
    check("batch recorded in history", len(po2["batches"]) >= 1)
    acct = client.get("/api/admin/ledger/accounts", headers=hdr(superadmin)).json()
    check("ledger balanced after payout batch", acct["balanced"] is True)
    check("seller_clearing cleared to 0", acct["accounts"].get("seller_clearing", "0.00") == "0.00")
    check("transport_clearing cleared to 0 too", acct["accounts"].get("transport_clearing", "0.00") == "0.00")
    snotes = client.get("/api/auth/notifications", headers=hdr(farmer)).json()
    check("seller notified of payout", any("payout" in n["title"].lower() for n in snotes))
    te2 = client.get("/api/transport/earnings", headers=hdr(transport)).json()
    check("transport payout marked paid after the batch", float(te2["paid_total"]) > 0)
    r = client.post("/api/admin/payouts/run", headers=hdr(superadmin), json={})
    check("empty payout run rejected", r.status_code == 409)
    r = client.post("/api/admin/payouts/run", headers=hdr(agent), json={})
    check("non-finance cannot run payouts", r.status_code in (401, 403))

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
    login(client, "919000000044", role="buyer_household", name="Temp Buyer")  # throwaway target
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

    print("\n== Notification preferences (mute proactive categories) ==")
    def fcount():
        return len(client.get("/api/auth/notifications", headers=hdr(farmer)).json())

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

    print("\n== Partner payout accounts (UPI / bank) ==")
    r = client.put("/api/auth/payout-account", headers=hdr(farmer),
                   json={"method": "upi", "upi_id": "ravi@okaxis"})
    check("farmer saves a UPI payout account", r.json()["account"]["upi_id"] == "ravi@okaxis")
    acc = client.get("/api/auth/payout-account", headers=hdr(farmer)).json()["account"]
    check("payout account read back", acc and acc["method"] == "upi")
    check("UPI without @ rejected",
          client.put("/api/auth/payout-account", headers=hdr(farmer),
                     json={"method": "upi", "upi_id": "notaupi"}).status_code == 400)
    r = client.put("/api/auth/payout-account", headers=hdr(transport),
                   json={"method": "bank", "account_name": "Fast Logistics",
                         "account_number": "123456789012", "ifsc": "HDFC0001234"})
    check("transport saves a bank payout account", r.json()["account"]["method"] == "bank")
    check("bank account number is masked",
          r.json()["account"]["account_number_masked"].endswith("9012")
          and r.json()["account"]["account_number_masked"].startswith("****"))
    check("bank without IFSC rejected",
          client.put("/api/auth/payout-account", headers=hdr(transport),
                     json={"method": "bank", "account_name": "X", "account_number": "1"}).status_code == 400)
    po = client.get("/api/admin/payouts", headers=hdr(superadmin)).json()
    check("payouts overview flags missing payout accounts", "missing_payout_accounts" in po)

    print("\n== Buyer saved addresses ==")
    a1 = client.post("/api/auth/addresses", headers=hdr(buyer),
                     json={"label": "Shop", "mandal_id": mandal_id, "address_line": "Main Rd",
                           "latitude": 16.24, "longitude": 80.64, "is_default": True})
    check("buyer adds a default address (with map pin)",
          a1.status_code == 201 and a1.json()["is_default"] and a1.json()["latitude"] == 16.24)
    check("admin live-bags map endpoint is accessible",
          isinstance(client.get("/api/bags/live", headers=hdr(superadmin)).json(), list))
    a2 = client.post("/api/auth/addresses", headers=hdr(buyer),
                     json={"label": "Home", "mandal_id": mandal_id, "is_default": True})
    check("second default demotes the first",
          a2.json()["is_default"] and sum(1 for a in client.get("/api/auth/addresses", headers=hdr(buyer)).json() if a["is_default"]) == 1)
    addrs = client.get("/api/auth/addresses", headers=hdr(buyer)).json()
    check("addresses list resolves mandal name", any(a["mandal"] for a in addrs))
    check("address deleted",
          client.delete(f"/api/auth/addresses/{a1.json()['id']}", headers=hdr(buyer)).status_code == 200)

    print("\n== One-tap reorder ==")
    r = client.post(f"/api/orders/{order_id}/reorder", headers=hdr(buyer)).json()
    check("buyer reorders -> fresh offer on an active listing",
          r.get("reorderable") is True and r.get("offer_id"))
    check("reorder targets the same commodity", r.get("commodity_id") is not None)
    check("non-party cannot reorder someone else's order",
          client.post(f"/api/orders/{order_id}/reorder", headers=hdr(farmer)).status_code in (403, 404))

    print("\n== Farmer withdrawals ==")
    wf = login(client, "919000000061", role="farmer", name="Withdraw Farmer")
    bal = client.get("/api/auth/me/balance", headers=hdr(wf)).json()
    check("balance endpoint returns available + can_request",
          "available" in bal and bal["can_request"] is False)
    check("withdrawal blocked without a verified payout account",
          client.post("/api/auth/me/withdrawals", headers=hdr(wf)).status_code == 400)
    client.put("/api/auth/payout-account", headers=hdr(wf), json={"method": "upi", "upi_id": "wf@okaxis"})
    wf_id = client.get("/api/auth/me", headers=hdr(wf)).json()["id"]
    client.post(f"/api/admin/payout-accounts/{wf_id}/verify", headers=hdr(superadmin), json={"approve": True})
    check("withdrawal blocked with a verified account but zero balance",
          client.post("/api/auth/me/withdrawals", headers=hdr(wf)).status_code == 400)
    check("finance withdrawals queue is accessible",
          client.get("/api/admin/withdrawals", headers=hdr(superadmin)).status_code == 200)

    # Identity-KYC gate: even with a verified payout account, a withdrawal is held
    # until the farmer's identity is verified by staff.
    bal2 = client.get("/api/auth/me/balance", headers=hdr(wf)).json()
    check("balance exposes identity_verified flag (unverified farmer)",
          bal2.get("identity_verified") is False)
    wd = client.post("/api/auth/me/withdrawals", headers=hdr(wf))
    check("withdrawal blocked while identity unverified",
          wd.status_code == 400 and "identity" in str(wd.json().get("detail", "")).lower())
    client.post(f"/api/admin/kyc/{wf_id}/decision", headers=hdr(superadmin), json={"approve": True})
    bal3 = client.get("/api/auth/me/balance", headers=hdr(wf)).json()
    check("identity flag flips to verified after staff approval",
          bal3.get("identity_verified") is True)
    wd2 = client.post("/api/auth/me/withdrawals", headers=hdr(wf))
    check("after identity approval only the zero-balance block remains",
          wd2.status_code == 400 and "identity" not in str(wd2.json().get("detail", "")).lower())
    ov = client.get("/api/admin/payouts", headers=hdr(superadmin)).json()
    check("payouts overview exposes identity-gate fields",
          "blocked_unverified_identity" in ov
          and all("identity_verified" in p for p in ov["pending"]))

    print("\n== Ledger edge cases ==")
    acct = client.get("/api/admin/ledger/accounts", headers=hdr(superadmin)).json()
    check("ledger globally balanced", acct["balanced"] is True)
    check("no clearing balances left stranded",
          acct["accounts"].get("seller_clearing", "0.00") == "0.00"
          and acct["accounts"].get("transport_clearing", "0.00") == "0.00")
    # Re-settling an already-settled order must not double-accrue a payout.
    before = client.get("/api/admin/payouts", headers=hdr(superadmin)).json()["pending_count"]
    client.post(f"/api/orders/{order_id}/acceptance", headers=hdr(buyer))  # already settled -> no-op/err
    after = client.get("/api/admin/payouts", headers=hdr(superadmin)).json()["pending_count"]
    check("re-accepting a settled order does not double-accrue payouts", after == before)
    check("ledger still balanced after the edge-case probe",
          client.get("/api/admin/ledger/accounts", headers=hdr(superadmin)).json()["balanced"] is True)

    print(f"\n==== {_checks['pass']} passed, {_checks['fail']} failed ====")
    return _checks["fail"] == 0


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
