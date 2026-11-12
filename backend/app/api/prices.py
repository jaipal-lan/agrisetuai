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

# Best-effort grouping of AGMARKNET commodity names into shopper-friendly
# categories, so the (large) price list can be filtered. Checked in ORDER; first
# keyword hit wins. Cereals/pulses/oilseeds/spices are checked before
# vegetables/fruits so staple grains and legumes aren't mislabelled by a stray
# substring (e.g. "Pearl Millet" vs "pear", "Urd Beans" vs "beans"). Unmatched
# falls to "other".
_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("cereal", ("rice", "paddy", "wheat", "maize", "jowar", "bajra", "ragi", "barley",
                "millet", "corn")),
    ("pulse", ("gram", "tur", "arhar", "moong", "urad", "masur", "lentil", "dal",
               "rajma", "horse gram", "moth", "kulthi", "black gram", "green gram",
               "red gram", "bengal gram", "pulse", "kabuli", "cowpea", "peas(dry)",
               "field pea", "lobia")),
    # Dairy, meat, fish & livestock (checked after pulse so "cowpea" isn't caught
    # by "cow"). AGMARKNET lists these in some markets.
    ("dairy_meat", ("milk", "ghee", "butter", "curd", "paneer", "khoa", "cream",
                    "cow", "ox", "buffalo", "bullock", "goat", "sheep", "prawn",
                    "fish", "egg", "mutton", "chicken", "meat", "poultry")),
    ("oilseed", ("groundnut", "sunflower", "soyabean", "soybean", "mustard", "sesamum",
                 "sesame", "til ", "castor", "safflower", "niger", "linseed", "copra",
                 "coconut", "cottonseed")),
    ("spice", ("chilli", "chili", "turmeric", "coriander", "cumin", "jeera", "pepper",
               "cardamom", "clove", "cinnamon", "fenugreek", "ajwain", "tamarind",
               "dry ginger", "ginger(dry)", "garlic", "fennel", "saunf", "nutmeg", "mace")),
    ("fruit", ("apple", "banana", "mango", "orange", "mosambi", "sweet lime", "grape",
               "pomegranate", "papaya", "guava", "watermelon", "water melon", "musk melon",
               "karbuja", "pineapple", "sapota", "chikoo", "pear", "plum", "peach",
               "lemon", "lime", "ber(", "custard apple", "jack fruit", "fig", "amla",
               "kinnow", "pomo", "grapes", "litchi", "lichi", "strawberry",
               "seetapal", "sitaphal", "seethaphal")),
    ("vegetable", ("tomato", "onion", "potato", "brinjal", "bhindi", "ladies finger",
                   "cabbage", "cauliflower", "carrot", "beetroot", "beans", "peas",
                   "green chilli", "capsicum", "cucumber", "cucumbar", "kheera",
                   "pumpkin", "gourd", "radish", "spinach", "methi", "drumstick",
                   "knol khol", "tapioca", "sweet potato", "colocasia", "colacasia",
                   "yam", "amaranthus", "cluster beans", "field bean",
                   "tinda", "chow chow", "leafy", "raw banana", "mint", "ginger",
                   "ash gourd", "raddish", "ridge", "snake", "thondekai", "tori",
                   "pea pod", "green and fresh", "knolkhol")),
]


def _category(name: str | None) -> str:
    n = (name or "").lower()
    for cat, keys in _CATEGORY_KEYWORDS:
        if any(k in n for k in keys):
            return cat
    return "other"


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
            "category": _category(name),
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
