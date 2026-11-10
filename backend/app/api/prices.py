"""Today's government-declared mandi prices — a reference screen for farmers and
buyers. No advisory, no schemes, no weather: just the official price for a
commodity across markets in India."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.prices import MarketPrice

router = APIRouter(tags=["prices"])

_DISCLAIMER = "Official mandi observation, not a guaranteed sale price on this platform."


def _row(p: MarketPrice) -> dict:
    return {
        "id": p.id,
        "state": p.state,
        "market": p.market,
        "commodity": p.commodity,
        "variety": p.variety,
        "min_price": str(p.min_price),
        "max_price": str(p.max_price),
        "modal_price": str(p.modal_price),
        "unit": p.unit,
        "arrivals": p.arrivals,
        "as_of": p.as_of,
        "source_name": p.source_name,
        "source_url": p.source_url,
        "stale": p.stale,
        "disclaimer": _DISCLAIMER,
    }


@router.get("/market-prices")
def market_prices(commodity: str | None = None, state: str | None = None,
                  db: Session = Depends(get_db)):
    """Flat list of market prices, optionally filtered by commodity and/or state."""
    stmt = select(MarketPrice)
    if commodity:
        stmt = stmt.where(MarketPrice.commodity == commodity)
    if state:
        stmt = stmt.where(MarketPrice.state == state)
    return [_row(p) for p in db.scalars(stmt.order_by(MarketPrice.commodity, MarketPrice.state))]


@router.get("/market-prices/commodities")
def priced_commodities(db: Session = Depends(get_db)):
    """The commodities that have prices, each with how many markets report + the
    modal price range — the product picker for the prices screen."""
    rows = list(db.scalars(select(MarketPrice)))
    by_c: dict[str, list[MarketPrice]] = {}
    for p in rows:
        by_c.setdefault(p.commodity, []).append(p)
    out = []
    for name, ps in sorted(by_c.items()):
        modals = [float(p.modal_price) for p in ps]
        out.append({
            "commodity": name,
            "market_count": len(ps),
            "state_count": len({p.state for p in ps if p.state}),
            "modal_min": min(modals) if modals else None,
            "modal_max": max(modals) if modals else None,
            "unit": ps[0].unit if ps else "₹/qtl",
            "as_of": ps[0].as_of if ps else None,
        })
    return out


@router.get("/market-prices/all-india")
def all_india(commodity: str, db: Session = Depends(get_db)):
    """One commodity's government price across every reporting market in India,
    grouped by state (what a farmer/buyer sees when they tap a product)."""
    rows = list(db.scalars(
        select(MarketPrice).where(MarketPrice.commodity == commodity)
        .order_by(MarketPrice.state, MarketPrice.market)
    ))
    by_state: dict[str, list[dict]] = {}
    for p in rows:
        by_state.setdefault(p.state or "—", []).append(_row(p))
    states = [{"state": s, "markets": ms} for s, ms in sorted(by_state.items())]
    modals = [float(p.modal_price) for p in rows]
    return {
        "commodity": commodity,
        "unit": rows[0].unit if rows else "₹/qtl",
        "as_of": rows[0].as_of if rows else None,
        "source_name": rows[0].source_name if rows else None,
        "modal_min": min(modals) if modals else None,
        "modal_max": max(modals) if modals else None,
        "modal_avg": round(sum(modals) / len(modals), 2) if modals else None,
        "market_count": len(rows),
        "states": states,
        "disclaimer": _DISCLAIMER,
    }
