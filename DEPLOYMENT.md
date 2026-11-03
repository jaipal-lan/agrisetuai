# AgriSetuAI — Deployment & Go-Live Guide

Audience: whoever deploys and operates this (devops / the project owner). It
covers moving from the local SQLite pilot to a production Postgres deployment,
the real third-party keys to plug in (everything is mocked in the pilot), and
the compliance gates that must clear before taking real money or produce.

---

## 1. Architecture recap

- **Backend**: FastAPI (`backend/`), SQLAlchemy 2.0, Alembic migrations.
  SQLite in dev, Postgres in prod. Money is `Decimal` + a double-entry ledger
  (the ledger, not order status, is the financial source of truth).
- **Frontend**: Next.js 14 (`web/`), plain-JS PWA. The API base URL is baked
  in at build time via `NEXT_PUBLIC_API_BASE`.
- **Auth**: phone + OTP, bearer token with a per-user `token_version` for
  revocation.

## 2. Prerequisites

- Python 3.13 (3.15 has no prebuilt pydantic-core wheel — do not use it).
- Node 20+ / npm.
- PostgreSQL 15+ (managed is fine: RDS, Cloud SQL, Neon, Supabase).
- A reverse proxy with TLS (nginx/Caddy) in front of both services.

## 3. Backend configuration (environment variables)

All settings live in `backend/app/core/config.py` and read from env / `.env`.
Set these in production:

| Variable | Pilot default | Production |
| --- | --- | --- |
| `DEV_MODE` | `true` | **`false`** (disables the dev OTP echo + master OTP) |
| `AUTH_SECRET` | dev-only fallback | **a long random secret** (required when `DEV_MODE=false`) |
| `DATABASE_URL` | `sqlite:///./agrisetu.db` | `postgresql+psycopg://user:pass@host:5432/agrisetu` |
| `AUTO_MIGRATE` | `true` | **`false`** — run migrations from the deploy pipeline instead |
| `SUPERADMIN_PHONE` | `919999999998` | the real superadmin phone |
| `MASTER_OTP` | `123456` | ignored when `DEV_MODE=false`; remove anyway |
| `PAYMENT_PROVIDER` | `mock` | `sandbox` then your live provider (see §7) |
| `PAYMENT_WEBHOOK_SECRET` | dev value | the provider's signing secret |
| `SMS_PROVIDER` | `console` | `twilio` / `msg91` / `gupshup` (see §7) |
| `SMS_API_KEY`, `SMS_SENDER_ID` | empty | real credentials + DLT-approved sender id |
| `DISTANCE_PROVIDER` | `haversine` | keep, or swap for a maps/routing API |

Generate a secret: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

## 4. Database & migrations

```bash
# one-time, and on every deploy that ships schema changes:
cd backend
DATABASE_URL=postgresql+psycopg://... python -m alembic upgrade head
```

Do **not** rely on `AUTO_MIGRATE` in production — run the line above from CI/CD
so a bad migration fails the deploy rather than a booting web process. The
pilot's demo data comes from `python -m app.seed`; in production seed only the
reference data you actually need (locations, catalog, pricing rule, plans) and
**skip `seed_demo_activity` / demo users**.

## 5. Running the services

Backend (behind your TLS proxy, multiple workers):

```bash
cd backend
DEV_MODE=false AUTH_SECRET=... DATABASE_URL=... \
  python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Frontend (the API base is compiled in — rebuild if it changes):

```bash
cd web
npm ci
NEXT_PUBLIC_API_BASE=https://api.yourdomain.com/api npm run build
NEXT_PUBLIC_API_BASE=https://api.yourdomain.com/api npx next start -p 3000
```

CORS: `app/main.py` currently allows localhost + private-LAN IPs on ports
3000–3002. For production, replace `_origin_regex` with your exact web origin
(e.g. `https://app.yourdomain.com`).

## 6. LAN / iPad demo (pilot only)

Backend on `--host 0.0.0.0:8000`; build the web app with
`NEXT_PUBLIC_API_BASE=http://<LAN-IP>:8000/api` and serve on
`-H 0.0.0.0 -p 3000`. Open the Windows firewall once (Admin PowerShell):

```powershell
New-NetFirewallRule -DisplayName "AgriSetuAI" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 3000,8000 -Profile Private
```

The iPad must be on the same Wi-Fi. If port 3000 is stuck in use after a
restart, kill the stale `next start` child:
`Get-NetTCPConnection -LocalPort 3000 -State Listen | % { Stop-Process -Id $_.OwningProcess -Force }`.

## 7. Real third-party keys to plug in (all mocked today)

Each integration is isolated behind a service module so swapping in real keys
is a localized change:

- **Payments** — `app/services/payments.py` (intent + HMAC-signed webhook).
  Point `PAYMENT_PROVIDER`/`PAYMENT_WEBHOOK_SECRET` at a real marketplace
  provider (Razorpay Route / Cashfree Easy Split / PhonePe). Keep the webhook
  signature check; capture already routes through `orders.capture_order_payment`.
- **Seller payouts** — `app/api/admin.py` `run_payout_batch` currently writes a
  mock disbursement to the ledger. Replace the per-payout step with a real
  bank/UPI payout API (RazorpayX / Cashfree Payouts), store the provider ref,
  and only mark `processed` on the provider's success callback.
- **SMS/OTP** — `app/services/sms.py` (console provider). Add a real gateway
  (MSG91 / Gupshup / Twilio) with a **DLT-registered** template + sender id.
- **AI crop triage** — `app/services/advisory_engine.py` `_visual_prescreen`
  is a non-diagnosing stub. Wire a real vision model only with agronomist
  sign-off; never auto-prescribe pesticide doses.
- **Distance/maps** — `app/services/distance.py` is haversine×road-factor;
  swap for a routing API behind the same interface if needed.

## 8. Compliance gates before go-live (not code — owner/legal)

These must clear before real trades/payments:

- **Payments & escrow**: PA/escrow arrangement, KYC/AML on sellers, settlement
  terms, refund policy — align with the payment provider's marketplace rules.
- **FSSAI**: licensing/registration for food commodities as applicable.
- **APMC / e-NAM**: mandi licensing / market-fee position for the states you
  operate in (AP & Telangana).
- **Weights & measures**: certified-scale basis for the "verified lot" weights.
- **Data protection (DPDP Act)**: consent records exist (`ConsentRecord`);
  confirm retention, deletion and grievance-officer process.
- **Invoices**: the PDF is a commercial document, not a statutory tax invoice —
  add GST/tax-invoice fields if/when registered.

## 9. Operations

- **Backups**: automated Postgres backups + point-in-time recovery. The ledger
  is append-only; never edit it by hand.
- **Health**: `GET /api/health`. Put it behind your load balancer's health check.
- **Secrets**: store in your platform's secret manager, not in `.env` on disk.
- **Monitoring**: watch `GET /api/admin/ledger/accounts` → `balanced: true`
  as a financial canary.

## 10. Smoke test

`cd backend && python smoke_test.py` runs ~188 end-to-end checks against a
throwaway SQLite DB. Run it in CI on every change; it must stay green.
