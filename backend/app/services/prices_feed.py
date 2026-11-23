"""Live market-price feed from data.gov.in (AGMARKNET daily mandi prices).

Gated on config: with ``prices_provider="data_gov_in"`` and a ``data_gov_in_api_key``
set, ``refresh_prices(db)`` pulls today's government-declared prices and upserts
them into ``market_prices`` (rows no longer reported are flagged ``stale``). Left
unconfigured (the default), the app keeps serving the seeded sample rows and
``refresh_prices`` raises a clear "not configured" error.

The HTTP layer is kept separate from the parse/upsert layer so the latter can be
exercised in tests by passing synthetic ``records`` — no network needed.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.prices import MarketPrice

log = logging.getLogger("agrisetu.prices_feed")

# "Current Daily Price of Various Commodities from Various Markets (Mandi)".
DATA_GOV_RESOURCE = "9ef84268-d588-465a-a308-a864a43d0070"
DATA_GOV_URL = f"https://api.data.gov.in/resource/{DATA_GOV_RESOURCE}"
SOURCE_NAME = "data.gov.in / AGMARKNET"


def provider_configured() -> bool:
    """True when the live feed is switched on and a key is present."""
    return settings.prices_provider == "data_gov_in" and bool(settings.data_gov_in_api_key)


def last_refresh_at(db: Session):
    """When the live feed last wrote a row, or None if it never has."""
    from sqlalchemy import func
    return db.scalar(
        select(func.max(MarketPrice.updated_at)).where(MarketPrice.source_name == SOURCE_NAME)
    )


def is_refresh_due(db: Session) -> bool:
    """True when the live feed is configured and hasn't refreshed within the
    throttle window (prices_refresh_hours)."""
    if not provider_configured():
        return False
    last = last_refresh_at(db)
    if last is None:
        return True
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return now - last >= timedelta(hours=settings.prices_refresh_hours)


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _get(rec: dict, *keys: str):
    """Case-insensitive field read (the API has shifted field casing over time)."""
    low = {str(k).lower(): v for k, v in rec.items()}
    for k in keys:
        if k.lower() in low and low[k.lower()] not in (None, ""):
            return low[k.lower()]
    return None


def normalize(rec: dict) -> dict | None:
    """Map one raw AGMARKNET record to our MarketPrice fields, or None if unusable."""
    market = (_get(rec, "market") or "")
    commodity = (_get(rec, "commodity") or "")
    market = str(market).strip()
    commodity = str(commodity).strip()
    modal = _num(_get(rec, "modal_price", "modal_x0020_price"))
    if not market or not commodity or modal is None:
        return None
    lo = _num(_get(rec, "min_price", "min_x0020_price"))
    hi = _num(_get(rec, "max_price", "max_x0020_price"))
    state = _get(rec, "state")
    variety = _get(rec, "variety")
    as_of = _get(rec, "arrival_date", "arrival_x0020_date") or ""
    return {
        "state": (str(state).strip() or None) if state else None,
        "market": market,
        "commodity": commodity,
        "variety": (str(variety).strip() or None) if variety else None,
        "min_price": lo if lo is not None else modal,
        "max_price": hi if hi is not None else modal,
        "modal_price": modal,
        "as_of": str(as_of).strip(),
    }


def _csv_list(raw: str) -> list[str]:
    return [s.strip() for s in (raw or "").split(",") if s.strip()]


def _http_fetch_once(limit: int, commodity: str | None, state: str | None) -> list[dict]:
    params = {"api-key": settings.data_gov_in_api_key, "format": "json", "limit": str(limit)}
    if commodity:
        params["filters[commodity]"] = commodity
    if state:
        params["filters[state]"] = state
    url = f"{DATA_GOV_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "agrisetuai/price-feed"})
    with urllib.request.urlopen(req, timeout=25) as resp:  # noqa: S310 (fixed gov URL)
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("records", []) or []


def _http_fetch(limit: int, commodity: str | None, state: str | None, *, retries: int = 3) -> list[dict]:
    """Fetch with simple exponential backoff, and honour the commodity/state
    whitelists when no explicit filter is passed."""
    import time as _time

    commodities = [commodity] if commodity else (_csv_list(settings.prices_feed_commodities) or [None])
    states = [state] if state else (_csv_list(settings.prices_feed_states) or [None])

    records: list[dict] = []
    for c in commodities:
        for st in states:
            last_err = None
            for attempt in range(retries):
                try:
                    records.extend(_http_fetch_once(limit, c, st))
                    last_err = None
                    break
                except Exception as exc:  # noqa: BLE001 - retry any transient failure
                    last_err = exc
                    if attempt < retries - 1:
                        _time.sleep(2 ** attempt)
            if last_err is not None:
                log.warning("price feed fetch failed for commodity=%s state=%s: %s", c, st, last_err)
    return records


def _key(state, market, commodity, variety) -> tuple:
    return ((state or "").lower(), (market or "").lower(),
            (commodity or "").lower(), (variety or "").lower())


def refresh_prices(db: Session, *, records: list[dict] | None = None,
                   limit: int | None = None, commodity: str | None = None,
                   state: str | None = None) -> dict:
    """Upsert the latest mandi prices. Rows within the pulled scope that are no
    longer reported get flagged ``stale``. Pass ``records`` to skip the network
    (tests / an external importer). Flushes; the caller commits. Raises
    RuntimeError when the live feed is requested but not configured."""
    if records is None:
        if not provider_configured():
            raise RuntimeError(
                "Live price feed not configured. Set PRICES_PROVIDER=data_gov_in "
                "and DATA_GOV_IN_API_KEY to enable it."
            )
        records = _http_fetch(limit or settings.prices_feed_limit, commodity, state)

    normalized = [n for n in (normalize(r) for r in records) if n]

    # Existing rows, keyed; scope the stale-sweep to the filter we pulled so a
    # commodity/state-filtered refresh never flags unrelated rows.
    stmt = select(MarketPrice)
    if commodity:
        stmt = stmt.where(MarketPrice.commodity == commodity)
    if state:
        stmt = stmt.where(MarketPrice.state == state)
    existing = {_key(p.state, p.market, p.commodity, p.variety): p
                for p in db.scalars(stmt)}
    for p in existing.values():
        p.stale = True

    url = f"{DATA_GOV_URL}" if provider_configured() else "https://agmarknet.gov.in/"
    added = 0
    for n in normalized:
        k = _key(n["state"], n["market"], n["commodity"], n["variety"])
        row = existing.get(k)
        if row is None:
            row = MarketPrice(market=n["market"], commodity=n["commodity"],
                              variety=n["variety"], state=n["state"])
            db.add(row)
            existing[k] = row  # so a repeat of this key in the same batch updates it
            added += 1
        row.state = n["state"]
        row.min_price = n["min_price"]
        row.max_price = n["max_price"]
        row.modal_price = n["modal_price"]
        row.unit = "₹/qtl"
        row.arrivals = "reported"
        row.as_of = n["as_of"] or row.as_of or ""
        row.source_name = SOURCE_NAME
        row.source_url = url
        row.stale = False
    db.flush()

    as_of_vals = [n["as_of"] for n in normalized if n["as_of"]]
    return {
        "fetched": len(records),
        "parsed": len(normalized),
        "upserted": len(normalized),
        "new": added,
        "source": SOURCE_NAME,
        "as_of": max(as_of_vals) if as_of_vals else None,
    }


import threading
import time as _time

# Single-flight guard + attempt-cooldown for the opportunistic page-load refresh.
_refresh_lock = threading.Lock()
_last_attempt_monotonic = 0.0
# Don't re-attempt more than once per this window, success OR failure. is_refresh_due
# is based on the last *successful* write, so without this a persistently failing
# feed (e.g. data.gov.in geo-blocking the server) would spawn a slow fetch on every
# single page load. 15 min is well under the default 12h success throttle.
_ATTEMPT_COOLDOWN_SECONDS = 15 * 60


def maybe_refresh_in_background() -> None:
    """Fire-and-forget, throttled refresh — safe to call on every prices request.

    No-ops unless the live feed is configured, a refresh is due (prices_refresh_hours),
    no refresh is already in flight, and we haven't attempted one within the
    attempt-cooldown. Opens its own session; never raises. Intended to be handed to
    FastAPI BackgroundTasks so it runs after the response is sent — the user never
    waits on the upstream fetch."""
    global _last_attempt_monotonic
    if not provider_configured():
        return
    if _time.monotonic() - _last_attempt_monotonic < _ATTEMPT_COOLDOWN_SECONDS:
        return
    if not _refresh_lock.acquire(blocking=False):
        return  # a refresh is already running
    try:
        # Re-check under the lock (another thread may have just attempted).
        if _time.monotonic() - _last_attempt_monotonic < _ATTEMPT_COOLDOWN_SECONDS:
            return
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            if not is_refresh_due(db):
                return
            _last_attempt_monotonic = _time.monotonic()  # count the attempt before the slow fetch
            refresh_prices(db)
            db.commit()
            log.info("opportunistic price refresh: prices updated on page load")
        except Exception:  # noqa: BLE001 - a transient/upstream failure must not surface
            db.rollback()
            log.exception("opportunistic price refresh failed")
        finally:
            db.close()
    finally:
        _refresh_lock.release()


def status(db: Session) -> dict:
    """Feed health for the Admin console: configuration, row counts, freshness."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func

    total = db.scalar(select(func.count(MarketPrice.id))) or 0
    stale = db.scalar(select(func.count(MarketPrice.id)).where(MarketPrice.stale.is_(True))) or 0
    last = last_refresh_at(db)
    is_stale = True
    if last is not None:
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        is_stale = (datetime.now(timezone.utc) - last) >= timedelta(hours=settings.prices_stale_hours)
    return {
        "configured": provider_configured(),
        "provider": settings.prices_provider,
        "commodities_whitelist": _csv_list(settings.prices_feed_commodities),
        "states_whitelist": _csv_list(settings.prices_feed_states),
        "last_refresh_at": last.isoformat() if last else None,
        "row_count": total,
        "stale_rows": stale,
        "fresh_rows": total - stale,
        "stale_after_hours": settings.prices_stale_hours,
        "feed_is_stale": is_stale if provider_configured() else False,
    }
