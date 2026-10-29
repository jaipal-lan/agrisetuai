# AgriSetuAI

AI-assisted regional-language farming advisory **+** a verified farm-to-marketplace
with two-way price negotiation, physical field-agent inspection, packing/dispatch
tracking, and superadmin control of fees, logistics and operations.

> Working product name only — run trademark/domain checks before adoption.
> Initial geography: Andhra Pradesh & Telangana, India.

This repository implements the PRD "managed marketplace" — every trade is auditable
from farmer listing → negotiation → inspection → payment → packing → dispatch →
delivery → settlement → dispute closure.

## Layout

```
backend/   FastAPI + SQLAlchemy. The auditable core: auth/RBAC, catalog, listings,
           RFQs, offer/counteroffer negotiation, order state machine, server-side
           pricing engine, double-entry ledger, append-only audit log.
web/       Next.js PWA (Telugu-first / English) — farmer + buyer + admin surfaces.
docs/      Build roadmap and architecture notes.
```

## Quick start (backend)

```bash
cd backend
python -m venv .venv          # use Python 3.13; 3.15 has no pydantic wheel yet
.venv/Scripts/activate        # Windows:  .venv\Scripts\activate
pip install -r requirements.txt
python -m app.seed            # runs migrations + seeds locations/catalog/users/pricing
python -m uvicorn app.main:app --port 8000 --reload
# OpenAPI docs: http://127.0.0.1:8000/docs
```

### Schema & migrations

The schema is managed by **Alembic**, not `create_all`. On startup the app runs
`alembic upgrade head` when `AUTO_MIGRATE=true` (default); in production set it to
`false` and run migrations from the deploy pipeline. The same URL drives SQLite
(dev) and PostgreSQL (prod — `postgresql+psycopg://…`).

```bash
cd backend
python -m alembic upgrade head                       # apply migrations
python -m alembic revision --autogenerate -m "msg"   # after changing models
python -m alembic current                            # show current revision
```

Run the end-to-end regression:

```bash
cd backend
python smoke_test.py
```

## Design principles (from the PRD)

- **Server is the source of truth for money.** Clients never decide fees, payouts or
  order status. Prices/quantities use `Decimal`. The order status field is *not* the
  financial source of truth — the append-only ledger is.
- **Every offer version is immutable.** A counteroffer creates a new version;
  acceptance references the exact price/quantity/grade/terms accepted.
- **Idempotency** on order creation, payment, refunds, shipment creation and webhooks.
- **Fee rules are versioned.** Publishing a new rule never reprices a confirmed order.
- **AI is decision-support, not diagnosis.** No model-invented pesticide doses;
  reviewed knowledge base + expert escalation. (Advisory module is a later phase.)

See [docs/ROADMAP.md](docs/ROADMAP.md) for phase status.
