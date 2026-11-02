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

### Phase A — frontend surfaces
- [x] Next.js PWA: Telugu/English toggle, OTP login, buyer browse + offer,
      farmer listing management, RFQ requests, order timeline, admin pricing/KPIs.
- [x] Field-agent PWA view (`web/pages/agent.js`): assigned-job list, inspection
      capture, and an **offline draft queue** (localStorage) that flushes on
      reconnect. The backend dedupes on `client_draft_id`, so re-sync never
      duplicates an inspection. Job list is cached for offline viewing.

### Phase B — harden the core
- [x] Real migrations (Alembic) instead of `create_all`. Baseline revision
      `0be45af65a74` creates all 30 tables; app runs `alembic upgrade head` on
      startup behind `AUTO_MIGRATE`. `psycopg` driver installed for PostgreSQL;
      `render_as_batch` on for SQLite ALTERs. Mandal lat/long geo columns added
      (`73d2bb5c72e5`) as plain decimals — no PostGIS dependency; add PostGIS
      spatial indexes only if proximity queries at scale need them.
- [x] RFQ-initiated negotiation (seller offers into a buyer RFQ). Buyer posts an
      RFQ; sellers browse open RFQs and offer in; accept marks the RFQ matched and
      creates a listing-less order that still prices/packs (commodity + mandal are
      snapshotted into accepted_terms).
- [x] Partial-quantity acceptance (inspection `pass_with_adjustment` proposes a
      new quantity; buyer confirms the accepted qty, reserved stock is adjusted,
      original is preserved) + partial refund. Proportional refund splits the
      original quote legs and absorbs sub-paisa rounding into the largest leg so
      the ledger stays balanced to the paisa.
- [x] Dispute workflow + support tickets; refund ledger paths.
- [ ] Media uploads (object storage, signed URLs, type/size + malware scan).
      (Local media router + optional ClamAV scan exist; object storage + signed
      URLs still to wire for production.)
- [x] Rate limiting on OTP; session revocation (token_version). Fraud checks TBD.

### Phase C — payments for real
- [ ] Marketplace-capable provider (split settlement, seller payouts, webhooks).
      **Launch gate:** legal + provider review before holding any customer funds.
- [ ] Signed webhook verification + reconciliation jobs + exception queue.

### Phase D — logistics & ops
- [x] Configurable distance source + serviceability (`app/services/distance.py`,
      `/logistics/*`). Default `haversine` provider computes `route_km` from mandal
      centroids × `road_distance_factor`; confirm-quote resolves distance
      server-side (origin = produce mandal, destination = buyer mandal) unless an
      explicit override is passed. The quote records `route_km_source`. Swap in an
      external maps/routing provider behind `route_km_between` without touching
      pricing/order code.
- [ ] Carrier assignment, milestone tracking fallback (no false GPS promises).
- [ ] Mandal dashboards, agent performance, logistics control tower.

### Phase E — AI advisory (controlled, parallel)
- [x] Crop triage returning **likelihoods with uncertainty**, not diagnosis
      (`app/services/advisory_engine.py`; keyword-matched for now — image model
      still to add).
- [x] Reviewed knowledge base (crop/region/season/source-date) + agronomist
      escalation. **No model-invented pesticide doses** — label-sourced only.
- [x] Weather/calendar, market prices, scheme cards (with source + last-checked).

### Launch gates (PRD section 18 — require professional review)
Food-business licensing (FSSAI), packaged-goods labelling, pesticide advisory,
organic claims, APMC/e-NAM market-access rules, payment/escrow structure,
consumer-protection terms, privacy/data-protection. None of these are code tasks.

## Known simplifications in the current build
- Payment provider is a mock with the same idempotent, ledger-backed shape as a
  real one, to keep the swap isolated.
- Transport distance (`route_km`) is passed in, not yet computed from a maps API.
- Row locks (`with_for_update`) are no-ops on SQLite; real on Postgres.
