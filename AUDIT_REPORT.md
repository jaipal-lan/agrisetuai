# AgriSetuAI — Audit Report

_Audit of the existing codebase against the "complete the app" spec. Written for the project owner/developer. Date: 2026-11-14._

## 0. Important: what this app actually is (vs the spec's assumptions)

The spec appears to be a generic completion prompt. Several of its assumptions **do not match this codebase** — reconciling these matters before any work:

| Spec assumes | Reality in this repo |
|---|---|
| Data in **localStorage / mock**, build a `services/api.js` mock layer | There is a **real backend**: FastAPI + SQLAlchemy 2.0 + Alembic (SQLite dev / Postgres prod), 21 API routers, 34 migrations. The frontend already talks to it through a single service layer (`web/lib/api.js`) — no `fetch`/`localStorage` for domain data in components. **We should NOT rip this out for a mock layer.** |
| **Flutter** mobile app | Frontend is **Next.js 14** (pages router, plain JS), a mobile-friendly PWA. No Flutter. |
| Roles: Farmer, Agent, Agent Lead, Manager, Transporter, SuperAdmin (an **aggregation / collection-centre** model where the agent collects bags and creates orders) | Roles exist (see mapping) but the app is a **negotiation marketplace**: buyers (household + business) order from farmers; agents **inspect**; transport delivers. There are **buyers** the spec omits. The "agent collects bags → collection centre → transporter" flow is a **new logistics layer** on top. |
| Order id `AGRI-XXXX` | Order id is `ORD-xxxxxxxx` (helper `public_id()` in `core/ids.py`). Prefix is a 1-line change if desired. |

**Recommendation:** keep the real architecture; treat the spec as a feature checklist, not a rewrite order. Most of sections 2/3/6/7/8/9/10 already exist. The genuinely new, high-value work is the **multi-stage barcode/QR scan tracking** (spec §5) — see §A below.

## 1. Role mapping (spec → actual `core/rbac.py`)

| Spec role | Actual role | Status |
|---|---|---|
| Farmer | `farmer` (sells **and** buys) | ✅ |
| Agent | `field_agent` | ✅ |
| Agent Lead | `field_leader` | ✅ |
| Manager | `field_manager` | ✅ |
| Transporter | `transport` | ✅ |
| SuperAdmin | `superadmin` | ✅ |
| _(missing in spec)_ | `buyer_household`, `buyer_business` | ✅ exist, central to the marketplace |

RBAC is enforced **server-side** on every endpoint (`require_roles`), with cosmetic client gating (`lib/roles.js`). This is stricter than the spec's "middleware/guard" ask. ✅

## 2. Data models — gap analysis

Existing models: `user, farmer/buyer/agent profiles, organisation, catalog (commodity/variety/grade), marketplace (listing, rfq, offer, offerversion, rfq_comment), order (order, orderline, orderstatusevent, inspection, lot, lotevent, package[qr_code], shipment, shipmentevent), account (payout_account, saved_address), finance (payout, payout_batch, ledger), review, support (ticket, dispute, consent, notification, media, quality_case), team (targets, meetings), prices (market_price), pricing (rules), audit`.

All have `created_at/updated_at` (TimestampMixin). Status + append-only event logs exist for order/lot/shipment.

| Spec model | Status | Missing fields to add |
|---|---|---|
| a) User | ✅ strong | spec extras not present: `email`✅(added), `profile_photo`✅(avatar), `district/state/pincode` (only `village/mandal`), `documents (Aadhaar/PAN)`, `bank_details/UPI` (exist on **PayoutAccount**, not User), `created_by/updated_by` (we have audit log instead) |
| b) Farmer profile | ⚠️ partial | has `village, mandal, pickup_point, verification_status`. Missing: `farm_size, crops_grown[], soil_type, irrigation_type, experience_years, rating, total_sales` |
| c) Product / Listing | ✅ strong | has qty/unit/price/MOQ/grade/photos/status/specs/defects. Missing: `harvest_date`(has `harvest_year`), `expiry_date` |
| d) Order | ✅ strong | has commission split, payouts, payment status, lines, delivery/pickup via terms. Spec's flat `buyerName/buyerPhone` differ (we use buyer user). Prefix `ORD` not `AGRI` |
| e) Agent Assignment | ⚠️ partial | `agent_profile.service_mandals` + team targets exist; no explicit `farmers_assigned[]` link or per-agent `target/performance` object (team targets cover some) |
| f) Transport | ✅ | `carrier` + `shipment` (vehicle, courier, fare via transport_charge, status, milestones) |
| g) Delivery Tracking | ✅ strong | `shipment` + `shipment_event` + live courier GPS (`/orders/{id}/tracking`), OTP + proof_of_delivery. Missing: persisted `location_history[]` table (currently live point only) |
| h) Payment / Payout | ✅ | `payout`, `payout_batch`, double-entry `ledger` |
| i) Inventory | ✅ | on Listing: `total/reserved/sold/available_qty` (no separate `wastage_qty`) |
| j) Notification | ✅ | `notification` (+ digest/mute prefs) |
| k) Dispute / Ticket | ✅ | `support_ticket`, `dispute` (evidence, decision, refund) |
| l) Price / Mandi Rate | ✅ strong | `market_price` (live data.gov.in/AGMARKNET feed, product-wise) |
| m) Config | ⚠️ partial | commission/fees/transport rates in **PricingRule** (versioned draft→publish); service areas = `mandal.serviceable`. No single "Config" table but equivalent exists |

**Net-new models needed for the barcode feature (spec §5):** `Barcode/Bag` (barcodeId, orderId, productId, farmerId, agentId, bagNo, weight, status, scanHistory[]). `Package` already has `qr_code` but not the multi-stage scan history.

## 3. Flows — status

| Flow | Status |
|---|---|
| Farmer: register→login→dashboard→add/edit product→orders→payments→track→rate | ✅ (register wizard, sell, orders, earnings, order tracking, reviews) |
| Agent: login→dashboard→assigned work→add product for farmer→create order→assign transporter→track→collect payment→commission | ⚠️ agent has inspection jobs, add-product, advisory; "create order on behalf / collect payment / commission view" partial |
| Agent Lead: manage agents, assign villages/farmers, approve listings, team performance | ⚠️ team targets/meetings/leaderboard exist; "approve listings" + explicit village/farmer assignment partial |
| Manager: manage staff, approve/reject products, pricing, disputes, reports | ✅ mostly (admin console: pricing, disputes, reports, KYC, broadcast, catalog mgmt) |
| Transporter: deliveries, accept/reject, pickup, live location, delivered+OTP+photo, earnings | ✅ (transport page, milestones, OTP, earnings) |
| SuperAdmin: create staff, manage all, categories/commission/areas/mandi, analytics, payouts | ✅ mostly (admin + user mgmt + payouts + catalog + prices) |

Every nav item routes to a real page; no known blank pages. Empty/loading/toast states exist.

## 4. Tracking + Maps — status

- ✅ Order tracking timeline (`/orders/{id}/tracking`, `OrderStatusEvent`, order page `TrackingTimeline`).
- ✅ Live map via OpenStreetMap embed; courier live GPS via `watchPosition`; buyer live-ETA; nearby ping.
- ✅ Distance + fare auto-calc (`services/distance.py`, haversine × road factor; pricing engine).
- ✅ Delivery OTP + proof-of-delivery photo.
- ⚠️ "Pick farm location on a map" at Add Product / pick pickup+drop on Create Order — currently mandal-based + GPS "use my location"; no draggable map pin yet.

## 5. Barcode scanning (spec §5) — **the main missing feature** → see §A

Not implemented as specified. `Package.qr_code` exists but there is **no** per-bag barcode generation, multi-stage scan (agent pickup → collection centre → loading → delivery), scan history/validation, public track-by-barcode, or superadmin barcode audit.

## 6. Dashboards + Reports — status
✅ Role-based dashboard with real counts (`/dashboard`), admin reports (GMV by commodity/state/agent, ops scorecard, CSV), date filters, search+pagination on lists. ⚠️ No chart components yet (counts/tables only); "bags scanned/in-transit/delivered" tiles depend on §5.

## 7. Security / permissions — ✅
Server-side RBAC on every route; token-version revocation; OTP rate-limit; password hashing; CSP + security headers; form validation on key inputs. ⚠️ Validation coverage could be tightened on some forms.

## 8. UI/UX — ✅ mostly
Mobile-friendly, te/en/hi toggle, dark mode, toasts, empty/loading states, role-based nav, ₹/kg formatting. ⚠️ dates are ISO in places (not all dd-mm-yyyy).

## 9. API-ready structure — ✅ (already real)
`web/lib/api.js` is the single service layer (`api`, `apiForm`, `uploadMedia`, `mediaUrl`, `productImage`, …). Components don't call `fetch` directly for domain data. The backend IS the API; no mock layer needed.

## 10. Final check — status
✅ Build passes; 361 smoke checks green; servers run; `DEPLOYMENT.md` + CI exist. ⚠️ `README.md` with demo logins + a documented demo-data seed could be added. Demo users exist in `seed.py` (all password `demo1234`).

---

## §A. Recommended plan for the barcode/scan tracking feature (spec §5)

This is the one large, genuinely-new feature. Proposed design that fits the existing architecture:

- **Model `Bag`** (new): `bag_code` (`AGRI-{orderId}-BAG-{nn}`), `qr_payload`, `order_id`, `listing_id/commodity`, `farmer_id`, `agent_id`, `weight`, `status`, timestamps. **Model `BagScan`** (append-only): `bag_id`, `stage` (pickup|collection_centre|loading|delivery), `scanned_by`, `role`, `lat/lng`, `note`, `created_at`, `corrected_by/reason`.
- **Endpoints:** generate bags for an order; `POST /bags/scan` (stage-aware, with validation: wrong bag, duplicate, out-of-sequence, offline-sync); `GET /bags/{code}` history; public `GET /track/{code}` (no PII); superadmin audit list + manual correct.
- **Status ladder:** Created → Picked up from farmer → Reached collection centre → Loaded / In transit → Out for delivery → Delivered (ties into existing shipment states).
- **Frontend:** one shared **Scan** screen (html5-qrcode via CDN, torch, manual entry) reused by agent/lead/transporter; **label print** page; **public track-by-barcode** page; **superadmin barcode audit** page. Notifications on each scan reuse `services/notify.py`.
- **Design fork to confirm:** in this marketplace, an Order is one buyer↔one farmer. Do bags attach to the **existing Order** (simplest), or do we add an **aggregation/consignment** concept (one agent collecting many farmers' bags to a centre, as the spec's model implies)? This changes the data model materially.

### Suggested build order (incremental, each committed + smoke-green)
1. `Bag` + `BagScan` models + migration + generation + scan endpoints + validation (+ smoke).
2. Shared Scan UI + label print + wire into agent/lead/transporter pages.
3. Public track-by-barcode page + notifications on scan.
4. SuperAdmin barcode audit/live view + reports (bags scanned/in-transit/delivered dashboard tiles).
5. Smaller gaps from §2–§8 (extra profile fields, map pin picker, README + demo data, dd-mm-yyyy dates) as a cleanup pass.

**I will not blindly rewrite the working app to match the generic prompt.** The above completes the spec's intent on top of the real architecture, without churn.
