# AgriSetuAI — build roadmap & status

Maps the PRD's phased plan (section 20) to what exists in this repo.

## Done — Phase 1 core + slices of 2/3/4 (backend)

The auditable managed-marketplace spine, with a passing end-to-end smoke test
(`backend/smoke_test.py`, 49 checks):

- **Auth & RBAC** — phone OTP (dev-mode master code), signed stateless tokens,
  11 roles (`app/core/rbac.py`), role-gated endpoints.
- **Reference data** — states/districts/mandals (AP + Telangana), commodity /
  variety / grade-spec catalog, Telugu labels. Seeded by `app/seed.py`.
- **Listings** — farmer create/publish/pause/withdraw, inventory
  (total/reserved/sold/available), organic-claim evidence gate, public search
  with PII-safe serialization.
- **Negotiation** — offer → counter → accept with **immutable offer versions**;
  only the non-proposer can accept/counter; expiry; accept creates a provisional
  order and reserves stock (no overselling).
- **Order state machine** — all PRD section-5 states, validated transitions,
  append-only `OrderStatusEvent` history.
- **Inspection** — mandal-manager assigns an agent; agent submits checklist +
  weighing + evidence + decision (pass/hold/fail); offline-draft idempotency;
  a pass auto-advances to buyer approval.
- **Pricing engine** — versioned rules, admin draft → **simulate** → publish;
  server-computed itemised quote; a confirmed order snapshots its rule version
  so republishing never reprices it.
- **Payments (mock) + ledger** — idempotent capture posts a balanced
  **double-entry ledger**; the ledger (not `Order.status`) is the money source of
  truth; `/admin/ledger/accounts` proves it balances.
- **Packing / shipment / delivery / settlement** — lot + QR package, shipment
  milestones, buyer acceptance → seller payout ledger posting + `Payout` record.
- **Audit log** — sensitive actions recorded append-only.

## Next (not yet built)

Ordered by dependency and PRD risk-gating.

### Phase A — frontend surfaces (in progress)
- [ ] Next.js PWA: Telugu/English toggle, OTP login, buyer browse + offer,
      farmer listing management, order timeline, admin pricing/KPIs.
- [ ] Field-agent PWA view: job list, inspection capture, offline draft queue.

### Phase B — harden the core
- [ ] Real migrations (Alembic) instead of `create_all`; PostgreSQL + PostGIS.
- [ ] RFQ-initiated negotiation (seller offers into a buyer RFQ).
- [ ] Partial-quantity acceptance + partial refund without corrupting history.
- [ ] Dispute workflow + support tickets; refund ledger paths.
- [ ] Media uploads (object storage, signed URLs, type/size + malware scan).
- [ ] Rate limiting on OTP; fraud checks; session revocation.

### Phase C — payments for real
- [ ] Marketplace-capable provider (split settlement, seller payouts, webhooks).
      **Launch gate:** legal + provider review before holding any customer funds.
- [ ] Signed webhook verification + reconciliation jobs + exception queue.

### Phase D — logistics & ops
- [ ] Configurable distance source (maps/routing provider), serviceability.
- [ ] Carrier assignment, milestone tracking fallback (no false GPS promises).
- [ ] Mandal dashboards, agent performance, logistics control tower.

### Phase E — AI advisory (controlled, parallel)
- [ ] Crop-image triage returning **likelihoods with uncertainty**, not diagnosis.
- [ ] Reviewed knowledge base (crop/region/season/source-date) + agronomist
      escalation. **No model-invented pesticide doses** — label-sourced only.
- [ ] Weather/calendar, market prices, scheme cards (with source + last-checked).

### Launch gates (PRD section 18 — require professional review)
Food-business licensing (FSSAI), packaged-goods labelling, pesticide advisory,
organic claims, APMC/e-NAM market-access rules, payment/escrow structure,
consumer-protection terms, privacy/data-protection. None of these are code tasks.

## Known simplifications in the current build
- `create_all` on startup (dev/SQLite); production needs Alembic migrations.
- Payment provider is a mock with the same idempotent, ledger-backed shape as a
  real one, to keep the swap isolated.
- Transport distance (`route_km`) is passed in, not yet computed from a maps API.
- Row locks (`with_for_update`) are no-ops on SQLite; real on Postgres.
