# KissanSetu — Go-Live Verification Checklist

One place to confirm every gated integration and config is actually live before
(and right after) launch. Each item: **what to set**, **where**, and **how to
verify it's working** — not just that the variable exists. Deep-dive setup lives
in the linked per-service docs.

Operated by **Lanciere Technologies**. App: **KissanSetu** (AgriSetuAI).

> Everything below is **gated and inert until configured** — the app runs, builds
> and passes all automated tests (smoke 474 / volume 20 / E2E 8 / i18n 1331×3)
> with none of these set. This checklist is about switching production ON.

---

## 1. Core infrastructure

| Item | Where | Set | Verify |
|---|---|---|---|
| Backend deployed | Render (`render.yaml`) | Blueprint deploy | `GET /api/health` → `{"ok":true}` |
| Frontend deployed | Vercel | auto-deploy from `main` | Home page loads; points at the Render API |
| Database | Neon Postgres | `DATABASE_URL` (Render, `sync:false`) | Health ok; migrations applied on boot (`AUTO_MIGRATE=true`) |
| CORS locked down | Render `CORS_ORIGINS` | set to the exact Vercel URL | Cross-origin call from the site works; a random origin is blocked |
| Auth secret | Render `AUTH_SECRET` | `generateValue` (auto) | Login issues a token; it survives a redeploy only if pinned |

See **DEPLOYMENT.md**.

## 2. Keep-awake & scheduled jobs  *(risk: Render free-tier sleep)*

| Item | Where | Set | Verify |
|---|---|---|---|
| Daily price refresh | GitHub Actions `cron.yml` | secrets `BACKEND_URL`, `CRON_TOKEN` (same `CRON_TOKEN` on Render) | Actions run green; mandi prices show today's date |
| Keep-awake pinger | GitHub Actions `keepalive.yml` | secret `BACKEND_URL` | Actions run green every ~10 min during IST day |
| **Recommended:** external uptime monitor | UptimeRobot / cron-job.org | monitor `GET /api/health` every 5 min | Dashboard shows "up"; first request of the day is fast (no cold start) |
| Move off free tier before scale | Render plan | upgrade to an always-on instance | No spin-down; keep-awake becomes unnecessary |

The keep-awake workflow and UptimeRobot are redundant on purpose — GitHub's
scheduler can be delayed, an external monitor is steadier.

## 3. Market prices (data.gov.in)  *(gated)*

| Item | Where | Set | Verify |
|---|---|---|---|
| Live feed on | Render | `PRICES_PROVIDER=data_gov_in`, `DATA_GOV_IN_API_KEY` (`sync:false`) | `/api/prices` returns rows dated today after a cron run |

See **MARKET_PRICES_SETUP.md**.

## 4. Payments — Razorpay  *(gated; deferred, check later)*

| Item | Where | Set | Verify |
|---|---|---|---|
| Live keys | Render | `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` (live, not test) | Create a ₹1 order → pay in live mode → order goes PAID |
| Webhook | Razorpay dashboard | webhook URL + secret (`RAZORPAY_WEBHOOK_SECRET`) | Payment event hits the backend; signature verifies |
| Idempotency | (code, already live) | — | Pay with same `Idempotency-Key` twice → single capture (smoke: BUY-04) |
| Ledger | (code, already live) | — | After pay + settle, ledger `balanced: true` (smoke + volume) |

Until set, mock/COD payment paths are used and fully tested. See **RAZORPAY_SETUP.md**.

## 5. WhatsApp — Gupshup  *(gated; deferred, check later)*

| Item | Where | Set | Verify |
|---|---|---|---|
| Provider on | Render | `WHATSAPP_PROVIDER=gupshup` | Admin → WhatsApp outbox shows real sends (not mock) |
| Credentials | Render | Gupshup API key + source number | A test order sends a real message |
| Approved templates | Gupshup dashboard | order/invoice templates **approved** by Meta | Template message delivers to a real handset |
| Invoice delivery | (code, already live) | — | On pay, invoice PDF link is sent to the buyer |

Until set, the **mock** provider records messages to the in-memory outbox
(enabled, visible to superadmin) and all alert logic is exercised by tests.
See **WHATSAPP_SETUP.md**.

## 6. Observability & safety  *(gated)*

| Item | Where | Set | Verify |
|---|---|---|---|
| Error tracking | Render / Vercel | `SENTRY_DSN` (backend), `NEXT_PUBLIC_SENTRY_DSN` (web) | Trigger a test error → appears in Sentry |
| Analytics | Vercel | `NEXT_PUBLIC_GA4_ID`, `NEXT_PUBLIC_POSTHOG_KEY` | Signup/call/payment events show in GA4/PostHog |
| Upload scanning | Render | ClamAV config enabled | Upload a known EICAR test file → rejected |
| Map tiles | Vercel build | `NEXT_PUBLIC_MAP_TILE_URL` + `_ATTRIBUTION` (SLA provider) | Live-track map renders tiles without OSM rate-limiting |

## 7. Business activation (in-app, superadmin)

- [ ] Service areas: activate the **Hyderabad launch** area (and TG/AP as you expand).
- [ ] Pricing: confirm the live rule — **3% service fee + 18% GST on services**, transport exempt (⚡ presets in Admin → Pricing); run **Simulate**.
- [ ] KYC queue: verify the first farmers and carriers.
- [ ] Walk one real order end-to-end: list → buy → pay → inspect → deliver → settle; confirm invoice (KS/LAN number, branded PDF) and a balanced ledger.

## 8. Post-deploy smoke (every release)

- [ ] `GET /api/health` ok on prod.
- [ ] CI green on the deployed commit (smoke 474, migrations on Postgres, build, i18n-check).
- [ ] E2E (`e2e.yml`) green.
- [ ] Spot-check all 8 role dashboards render correctly in **te / en / hi**.
- [ ] No Critical/High defects open (see QA Suite → Bug Template severity guide).

---

*Linked docs: DEPLOYMENT.md · MARKET_PRICES_SETUP.md · RAZORPAY_SETUP.md · WHATSAPP_SETUP.md · ROADMAP.md · docs/KissanSetu-Tax-Compliance-Blueprint.docx*
