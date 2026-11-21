"""High-volume regression + load test for the AgriSetuAI marketplace.

Opens the ENTIRE Telangana + Andhra Pradesh coverage menu as serviceable, then
seeds a large, region-spread dataset and drives the real API end to end:

  * registers farmers across every opened mandal,
  * publishes a large listing corpus (create -> 3 images -> publish),
  * registers buyers and runs full order lifecycles across regions
    (buy-now -> inspect -> approve -> quote -> pay -> pack -> ship -> settle),
  * exercises discovery queries under the data volume.

It measures latency (p50 / p95 / max) per operation class, asserts correctness
across regions, and confirms the ledger is balanced at the end. Runs in-process
against a throwaway SQLite DB (no server needed), same harness as smoke_test.

    cd backend
    python volume_test.py
"""
import os
import sys
import tempfile
import time

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["DEV_MODE"] = "true"
os.environ["AUTH_SECRET"] = "volume-test-secret"
os.environ["PRICES_PROVIDER"] = "sample"
os.environ["DATA_GOV_IN_API_KEY"] = ""
os.environ["SCHEDULER_INTERVAL_SECONDS"] = "0"
os.environ["MEDIA_DIR"] = tempfile.mkdtemp(prefix="agri-vol-media-")

sys.path.insert(0, os.path.dirname(__file__))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seed import main as seed_main  # noqa: E402

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
_checks = {"pass": 0, "fail": 0}
_timings = {}  # label -> [durations in ms]


def check(label, cond):
    tag = PASS if cond else FAIL
    print(f"  [{tag}] {label}")
    _checks["pass" if cond else "fail"] += 1
    return cond


def timed(label, fn):
    """Run fn(), record its latency under `label`, return its result."""
    t0 = time.perf_counter()
    out = fn()
    _timings.setdefault(label, []).append((time.perf_counter() - t0) * 1000.0)
    return out


def pct(vals, p):
    if not vals:
        return 0.0
    s = sorted(vals)
    k = min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1))))
    return s[k]


DEMO_PW = "demo1234"


def hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


def register(client, phone, role, name):
    r = client.post("/api/auth/otp/request", json={"phone": phone})
    code = r.json().get("dev_code", "123456")
    vp = client.post("/api/auth/otp/verify-phone", json={"phone": phone, "code": code}).json()
    first, _, last = name.partition(" ")
    data = {"phone_token": vp["phone_token"], "password": DEMO_PW, "role": role,
            "first_name": first, "last_name": last or "."}
    files = None
    if role == "buyer_business":
        data["biz_legal_name"] = name
        files = [("evidence", ("pan.pdf", b"%PDF-1.4 demo", "application/pdf"))]
    reg = client.post("/api/auth/register", data=data, files=files)
    assert reg.status_code == 201, f"register {phone}: {reg.status_code} {reg.text}"
    r = client.post("/api/auth/login", json={"phone": phone, "password": DEMO_PW})
    return r.json()["token"]


def login_seeded(client, phone):
    client.post("/api/auth/otp/request", json={"phone": phone})
    r = client.post("/api/auth/login", json={"phone": phone, "password": DEMO_PW})
    return r.json()["token"]


def publish_listing(client, token, commodity_id, grade_id, mandal_id, qty, price, unit_hint=None):
    body = {"commodity_id": commodity_id, "grade_spec_id": grade_id,
            "total_qty": qty, "min_order_qty": max(1, qty // 20), "asking_price": price,
            "mandal_id": mandal_id, "harvest_year": 2026, "quality_grade": "A", "defect_pct": 1.5}
    r = timed("listing_create", lambda: client.post("/api/listings", headers=hdr(token), json=body))
    if r.status_code != 201:
        return None
    lid = r.json()["id"]
    for i in range(3):
        client.post(f"/api/listings/{lid}/media", headers=hdr(token),
                    json={"object_key": f"sample/vol-{lid}-{i}.svg", "media_type": "image"})
    pr = client.post(f"/api/listings/{lid}/publish", headers=hdr(token))
    return r.json() if pr.status_code == 200 and pr.json().get("status") == "open" else None


def run():
    print("== Bootstrap ==")
    seed_main()
    client = TestClient(app)
    superadmin = login_seeded(client, "919999999998")
    agent = login_seeded(client, "919000000002")
    manager = login_seeded(client, "919000000001")
    transport = login_seeded(client, "919000000005")
    agent_id = client.get("/api/auth/me", headers=hdr(agent)).json()["id"]
    check("seeded staff reachable", all([superadmin, agent, manager, transport]))

    print("\n== Open ALL Telangana + Andhra regions ==")
    r = timed("open_all", lambda: client.post("/api/admin/service-areas/preset/open-all",
                                              headers=hdr(superadmin)))
    check("open-all endpoint succeeds", r.status_code == 200 and r.json().get("ok"))
    opened = r.json()
    print(f"    activated={opened.get('activated')} flipped_on={opened.get('flipped_on')}")

    sa = client.get("/api/admin/service-areas", headers=hdr(superadmin)).json()
    regions = {}   # state_name -> [ (mandal_id, mandal_name) ]
    svc_count = 0
    for st in sa:
        for d in st["districts"]:
            for m in d["mandals"]:
                if m["serviceable"]:
                    svc_count += 1
                    regions.setdefault(st["name"], []).append((m["id"], m["name"]))
    tg = len(regions.get("Telangana", []))
    ap = len(regions.get("Andhra Pradesh", []))
    print(f"    serviceable mandals: Telangana={tg}, Andhra Pradesh={ap}, total={svc_count}")
    check("Telangana opened (>=20 mandals)", tg >= 20)
    check("Andhra Pradesh opened (>=15 mandals)", ap >= 15)
    check("no non-serviceable AP/TG mandal remains",
          all(m["serviceable"] for st in sa if st["name"] in ("Telangana", "Andhra Pradesh")
              for d in st["districts"] for m in d["mandals"]))

    all_mandals = [mid for lst in regions.values() for (mid, _) in lst]

    # Catalog: a spread of commodities, each with a grade spec.
    commodities = client.get("/api/catalog/commodities").json()
    cat = []
    for c in commodities:
        grades = client.get(f"/api/catalog/commodities/{c['id']}/grades").json()
        if grades:
            cat.append((c["id"], grades[0]["id"]))
        if len(cat) >= 8:
            break
    check("catalog has gradeable commodities", len(cat) >= 3)

    print("\n== High-volume seed: farmers + listings across every region ==")
    FARMERS = len(all_mandals)                 # one farmer per opened mandal
    LISTINGS_PER_FARMER = 4
    listings = []                              # (listing_id, mandal_id, state)
    mandal_state = {mid: st for st, lst in regions.items() for (mid, _) in lst}
    for i in range(FARMERS):
        mandal_id = all_mandals[i]
        tok = register(client, f"9180100{i:05d}", "farmer", f"Farmer {i}")
        for j in range(LISTINGS_PER_FARMER):
            cid, gid = cat[(i + j) % len(cat)]
            lst = publish_listing(client, tok, cid, gid, mandal_id,
                                  qty=200 + 10 * j, price=20.0 + j)
            if lst:
                listings.append((lst["id"], mandal_id, mandal_state[mandal_id]))
    print(f"    farmers registered: {FARMERS}")
    print(f"    listings published: {len(listings)} (target {FARMERS * LISTINGS_PER_FARMER})")
    check("bulk listing corpus published", len(listings) >= FARMERS * LISTINGS_PER_FARMER * 0.95)
    check("listings span both states",
          len({s for (_, _, s) in listings}) == 2)

    print("\n== Discovery under load ==")
    grid = timed("discovery_grid", lambda: client.get("/api/listings/products").json())
    check("product grid returns under load", isinstance(grid, list) and len(grid) > 0)
    for _ in range(20):
        timed("discovery_list", lambda: client.get("/api/listings").json())
    # 'near you' from a few region centroids
    for lat, lng in [(17.49, 78.39), (16.31, 80.44), (17.69, 83.22), (14.44, 79.99)]:
        timed("discovery_near", lambda: client.get(
            "/api/listings", params={"lat": lat, "lng": lng}).json())
    check("discovery p95 under 400ms", pct(_timings.get("discovery_list", []), 95) < 400)

    print("\n== Full order lifecycles across regions ==")
    BUYERS = 16
    buyers = [register(client, f"9180200{i:05d}", "buyer_household", f"Buyer {i}")
              for i in range(BUYERS)]
    check("buyers registered", len(buyers) == BUYERS)

    LIFECYCLES = 30
    settled = 0
    step_fail = {}
    # Spread chosen listings across the corpus (and thus across regions).
    stride = max(1, len(listings) // LIFECYCLES)
    chosen = listings[::stride][:LIFECYCLES]
    for n, (lid, mandal_id, state) in enumerate(chosen):
        buyer = buyers[n % BUYERS]

        def stage(name, fn, ok):
            r = fn()
            good = ok(r)
            if not good:
                step_fail[name] = step_fail.get(name, 0) + 1
            return r, good

        t0 = time.perf_counter()
        try:
            r, g = stage("buy_now",
                         lambda: client.post("/api/offers/buy-now", headers=hdr(buyer),
                                             json={"listing_id": lid, "quantity": 50}),
                         lambda r: r.status_code == 200 and r.json().get("order"))
            if not g:
                continue
            oid = r.json()["order"]["id"]
            _, g = stage("assign_inspection",
                         lambda: client.post(f"/api/orders/{oid}/assign-inspection",
                                             headers=hdr(superadmin), json={"agent_id": agent_id}),
                         lambda r: r.status_code == 200)
            if not g:
                continue
            _, g = stage("inspection",
                         lambda: client.post(f"/api/agent/orders/{oid}/inspection",
                                             headers=hdr(agent),
                                             json={"gross_weight": 10.2, "tare_weight": 0.2,
                                                   "outcome": "pass",
                                                   "checklist": {"moisture_pct": 12}}),
                         lambda r: r.status_code == 200)
            if not g:
                continue
            stage("buyer_approve",
                  lambda: client.post(f"/api/orders/{oid}/buyer-approve", headers=hdr(buyer)),
                  lambda r: r.status_code == 200)
            stage("confirm_quote",
                  lambda: client.post(f"/api/orders/{oid}/confirm-quote", headers=hdr(buyer),
                                      json={"route_km": 25}),
                  lambda r: r.status_code == 200)
            stage("pay",
                  lambda: client.post(f"/api/orders/{oid}/pay", headers={**hdr(buyer),
                                      "Idempotency-Key": f"vol-pay-{oid}"}),
                  lambda r: r.status_code == 200 and r.json().get("status") == "paid")
            stage("packing",
                  lambda: client.post(f"/api/orders/{oid}/packing-complete", headers=hdr(agent),
                                      json={"packing_video": "sample/pack.mp4"}),
                  lambda r: r.status_code == 200)
            # courier assigned by the buyer (buyer-paid logistics)
            car = client.post("/api/carriers", headers=hdr(superadmin),
                              json={"name": f"Carrier {n}", "code": f"C{n:03d}",
                                    "vehicle_classes": ["mini_truck"], "service_areas": [state]})
            cid = car.json()["id"]
            client.patch(f"/api/carriers/{cid}", headers=hdr(superadmin),
                         json={"kyc_status": "verified"})
            stage("assign_courier",
                  lambda: client.post(f"/api/orders/{oid}/assign-courier", headers=hdr(buyer),
                                      json={"courier_id": cid, "vehicle_class": "mini_truck"}),
                  lambda r: r.status_code == 200)
            for ev in ["picked_up", "in_transit", "out_for_delivery", "delivered"]:
                stage(f"ship_{ev}",
                      lambda ev=ev: client.post(f"/api/orders/{oid}/shipment/event",
                                                headers=hdr(transport), json={"event": ev}),
                      lambda r: r.status_code == 200)
            r, g = stage("acceptance",
                         lambda: client.post(f"/api/orders/{oid}/acceptance", headers=hdr(buyer)),
                         lambda r: r.status_code == 200 and r.json().get("status") == "settled")
            if g:
                settled += 1
        finally:
            _timings.setdefault("order_lifecycle", []).append(
                (time.perf_counter() - t0) * 1000.0)

    print(f"    lifecycles attempted: {len(chosen)}, settled end-to-end: {settled}")
    if step_fail:
        print(f"    stage failures: {step_fail}")
    check("most lifecycles settle end-to-end", settled >= len(chosen) * 0.9)

    print("\n== Ledger integrity after high volume ==")
    acct = client.get("/api/admin/ledger/accounts", headers=hdr(superadmin)).json()
    check("ledger balanced after all settlements", acct.get("balanced") is True)

    print("\n== KPI / reporting under volume ==")
    kpis = timed("admin_kpis", lambda: client.get("/api/admin/kpis", headers=hdr(superadmin)).json())
    check("admin KPIs computed under volume", "total_orders" in kpis and kpis["total_orders"] >= settled)

    # ---- Latency report ----
    print("\n== Latency (ms) ==")
    print(f"  {'operation':<22}{'n':>6}{'p50':>9}{'p95':>9}{'max':>9}")
    order = ["listing_create", "discovery_grid", "discovery_list", "discovery_near",
             "order_lifecycle", "admin_kpis", "open_all"]
    for label in order:
        v = _timings.get(label, [])
        if v:
            print(f"  {label:<22}{len(v):>6}{pct(v,50):>9.1f}{pct(v,95):>9.1f}{max(v):>9.1f}")

    print("\n" + "=" * 54)
    print(f"  VOLUME SUMMARY: {FARMERS} farmers, {len(listings)} listings, "
          f"{BUYERS} buyers, {settled}/{len(chosen)} orders settled")
    print(f"  across {tg + ap} serviceable mandals (TG {tg} / AP {ap})")
    print(f"==== {_checks['pass']} passed, {_checks['fail']} failed ====")
    return _checks["fail"] == 0


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
