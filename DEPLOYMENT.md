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
| `PRICES_PROVIDER` | `sample` | `data_gov_in` to pull live AGMARKNET mandi prices |
| `DATA_GOV_IN_API_KEY` | empty | a free key from https://data.gov.in (required for the live feed) |
| `PRICES_FEED_COMMODITIES` / `PRICES_FEED_STATES` | empty (all) | optional comma-separated whitelists |
| `PRICES_REFRESH_HOURS` | `12` | throttle for the scheduler's price refresh |
| `PRICES_STALE_HOURS` | `48` | prices older than this are flagged stale in Admin |
| `SCHEDULER_INTERVAL_SECONDS` | `0` (off) | e.g. `3600` to run digests, meeting reminders + price refresh on a timer |
| `MEETING_REMINDER_HOURS` | `24` | how far ahead to remind team-meeting attendees |
| `COURIER_SPEED_KMPH` / `COURIER_NEARBY_KM` | `25` / `2` | live-ETA speed + buyer "courier nearby" radius |

Generate a secret: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

### Live market-price feed (data.gov.in / AGMARKNET)

Left at `PRICES_PROVIDER=sample`, the app serves seeded sample prices (no network,
no key). To go live: register a free key at https://data.gov.in, set
`PRICES_PROVIDER=data_gov_in` + `DATA_GOV_IN_API_KEY=<key>`, then either refresh on
demand (Admin → "Refresh prices now") or set `SCHEDULER_INTERVAL_SECONDS>0` so the
in-process timer refreshes them (throttled by `PRICES_REFRESH_HOURS`). Admin →
Market price feed shows the live status + a "feed stale" warning.

## 4. Database & migrations

```bash
# one-time, and on every deploy that ships schema changes:
cd backend
DATABASE_URL=postgresql+psycopg://... python -m alembic upgrade head
```

Do **not** rely on `AUTO_MIGRATE` in production — run the line above from CI/CD
so a bad migration fails the deploy rather than a booting web process. The
pilot's demo data comes from `python -m app.seed`; in production seed only the
reference data you actually need (locations, catalog, pricing rule, market
prices) and **skip `seed_demo_activity` / demo users / demo reviews**.

### Staging (Postgres) quickstart

A staging run mirrors production but with the sandbox providers. Checklist:

1. Provision a Postgres 15+ DB; set `DATABASE_URL=postgresql+psycopg://…`.
2. `DEV_MODE=false`, a real `AUTH_SECRET`, `AUTO_MIGRATE=false`.
3. Run migrations from CI: `python -m alembic upgrade head`.
4. Seed reference data only (no demo users/activity).
5. `PAYMENT_PROVIDER=sandbox`, `SMS_PROVIDER` on a test sender, `PRICES_PROVIDER=data_gov_in`
   with a key, `SCHEDULER_INTERVAL_SECONDS=3600`.
6. Restrict CORS `_origin_regex` (app/main.py) to the staging web origin.
7. Smoke the deploy: `GET /api/health` and `GET /api/admin/ledger/accounts` → `balanced: true`.
8. Run `python smoke_test.py` in CI (it uses its own throwaway SQLite DB, so it
   validates the code, not the Postgres instance).

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
- **Seller & transport payouts** — `app/api/admin.py` `run_payout_batch` writes a
  mock disbursement to the ledger for both seller and transport-partner payouts
  (`Payout.payee_type`). Replace the per-payout step with a real bank/UPI payout
  API (RazorpayX / Cashfree Payouts), store the provider ref, and only mark
  `processed` on the provider's success callback. Payees capture their UPI/bank
  details via `PUT /api/auth/payout-account`; Admin → Payouts flags any pending
  payee with no account on file (`missing_payout_accounts`).
- **SMS/OTP** — `app/services/sms.py` (console provider). Add a real gateway
  (MSG91 / Gupshup / Twilio) with a **DLT-registered** template + sender id.
- **Market prices** — `app/services/prices_feed.py` pulls live AGMARKNET prices
  from data.gov.in once `PRICES_PROVIDER=data_gov_in` + `DATA_GOV_IN_API_KEY` are
  set (retry/backoff + optional commodity/state whitelists built in).
- **Distance/maps** — `app/services/distance.py` is haversine×road-factor;
  live courier GPS tracking is real, but turn-by-turn is a maps deep link
  (`nav_url`). Swap for a routing/maps API behind the same interface if needed.

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

`cd backend && python smoke_test.py` runs 300+ end-to-end checks against a
throwaway SQLite DB (covering the ledger, payouts, orders, tracking, team tools
and the price feed). Run it in CI on every change; it must stay green.
