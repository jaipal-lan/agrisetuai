# AgriSetuAI

Telugu-first, door-to-door **farm-to-market marketplace**: farmers list produce, buyers order, field agents verify, transport delivers — with **barcode/QR bag tracking** end to end. FastAPI + SQLAlchemy backend, Next.js (PWA) frontend. Payments/SMS are mocked behind a clean service layer and swap in later without UI changes.

See [AUDIT_REPORT.md](AUDIT_REPORT.md) for a feature-by-feature status map and [DEPLOYMENT.md](DEPLOYMENT.md) for staging/production. Initial geography: Andhra Pradesh & Telangana.

## Stack
- **Backend**: FastAPI, SQLAlchemy 2.0, Alembic (SQLite dev / Postgres prod), Python 3.13.
- **Frontend**: Next.js 14 (pages router, plain JS), i18n te/en/hi, PWA.
- Money is double-entry **ledger**-backed (the ledger, not order status, is the source of truth). Schema is Alembic migrations, auto-applied on startup via `AUTO_MIGRATE`.

## Run locally

### Backend
```bash
cd backend
py -3.13 -m venv .venv                               # 3.13 (3.15 has no pydantic wheel yet)
./.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux
./.venv/Scripts/python.exe -m app.seed               # create + seed the dev DB
DEV_MODE=true ./.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Health: http://127.0.0.1:8000/api/health · OpenAPI: http://127.0.0.1:8000/docs

### Frontend
```bash
cd web
npm install
# point the web app at the API (use your LAN IP to test on a phone on the same Wi-Fi):
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000/api npx next build
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000/api npx next start -H 0.0.0.0 -p 3000
```
Open http://localhost:3000

> **Camera features** (profile photo capture, barcode scanning) need **HTTPS or `localhost`** — browsers block the camera on a plain-HTTP LAN IP. Over the LAN link use the **manual-entry** fallback on the scan screen; the camera works on the HTTPS staging deploy and on phones.

### Tests
```bash
cd backend && ./.venv/Scripts/python.exe smoke_test.py   # end-to-end regression (hermetic temp DB)
```

## Demo logins
All seeded users share the password **`demo1234`**. In `DEV_MODE` the OTP is shown on screen (master OTP `123456`).

| Role | Phone |
|---|---|
| SuperAdmin | `919999999998` |
| Field Manager | `919000000006` |
| Field Leader (Agent Lead) | `919000000001` |
| Field Agent | `919000000002` |
| Farmer (Ravi) | `919000000003` |
| Business buyer (Lakshmi Traders) | `919000000004` |
| Household buyer | `919000000009` |
| Transport partner | `919000000005` |

Register new accounts at **/register** (phone OTP → password → role → details).

## Demo data (fresh seed)
15 commodities, demo listings, 3 couriers, live/sample mandi prices, demo offers/RFQs/reviews, and **3 demo orders with 25 barcoded bags** across statuses — including a **collection-centre mismatch** (an order with bags still missing) to showcase the alert.

## Key features
- **Marketplace**: listings (per-listing unit kg/quintal/piece/dozen/litre, draggable farm geo-pin, 3-photo requirement), offers/counter-offers, RFQs (price range, live market-price preview, multi-area sourcing, comment thread, 1-day agent escalation, needed-by date), inspection-first order lifecycle, PDF invoices/receipts.
- **Barcode/QR bag tracking**: generate bags per order, printable labels, stage scanning (pickup → collection → loading → delivery) with validation (invalid/duplicate/out-of-sequence/wrong-role) + offline queue, public track-by-barcode, collection-centre mismatch alert, superadmin audit + manual correction.
- **Money**: double-entry ledger, commission/fees, seller payouts (admin batch + **farmer-initiated withdrawals**), refunds, mandi price feed with ₹/kg toggle + best-price sorting + area filter.
- **People**: phone+password auth (OTP fallback + reset), RBAC enforced on every endpoint, KYC verification, profile photo, business-buyer KYC docs, address + farm profile fields.
- **Ops**: role dashboards, admin reports with charts, disputes, broadcasts, team targets/meetings, live courier map, security headers + CSP.

## Test each flow
- **Sell → order**: farmer → Sell → create listing (unit, 3 photos, optional map pin) → publish. Buyer → Marketplace → product → make offer → negotiate → accept → inspection → pay → pack → ship → deliver.
- **Barcode**: order → **Bags & labels** → generate + print. Agent → **Scan** (Pickup); leader (Collection); transporter (Loading, Delivery). **/track** shows the public journey; leader → **Team → Collection centre** shows mismatches; Admin → **Barcode / live tracking** audits + corrects.
- **Withdrawal**: farmer sets a payout account (Profile) → superadmin verifies it (Admin → Payout accounts) → after an order settles, farmer → **Earnings → Request withdrawal** → superadmin **Approve & pay** (Admin → Withdrawal requests).

## Pending for real deployment (integrate later)
- Real **SMS** provider (Twilio/MSG91/Gupshup) for OTP — config `SMS_PROVIDER`/`SMS_API_KEY`.
- Real **payment/payout** provider + signed webhooks + reconciliation (escrow/legal review).
- Object-storage media + signed URLs (local disk in the pilot).
- Transport fare for per-piece/dozen listings assumes a weight basis — refine when real logistics pricing lands.
- Temporary demo produce photos (`web/public/produce/`) are royalty-free placeholders; real seller uploads override them.
