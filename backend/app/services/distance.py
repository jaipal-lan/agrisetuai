"""Transport distance between mandals (PRD section 8 / Phase D).

`route_km` feeds the pricing engine's transport charge. It used to be passed in by
hand; this service computes it from mandal coordinates so quotes are reproducible
and not caller-controlled.

The default provider is `haversine`: great-circle distance between two mandal
centroids, scaled by `road_distance_factor` to approximate road distance. A real
maps/routing provider (OSRM, Google, Mapbox) can be swapped in behind
`route_km_between` without touching the pricing or order code — same signature,
same return shape.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.money import D
from app.models.location import Mandal


@dataclass
class RouteResult:
    route_km: Decimal
    source: str  # "haversine" | "default" | "override"
    serviceable: bool
    from_mandal_id: int | None = None
    to_mandal_id: int | None = None

    def to_json(self) -> dict:
        return {
            "route_km": str(self.route_km),
            "source": self.source,
            "serviceable": self.serviceable,
            "from_mandal_id": self.from_mandal_id,
            "to_mandal_id": self.to_mandal_id,
        }


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two WGS84 points."""
    r = 6371.0088  # mean Earth radius (km)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _has_coords(m: Mandal | None) -> bool:
    return m is not None and m.latitude is not None and m.longitude is not None


def is_serviceable(db: Session, mandal_id: int | None) -> bool:
    if mandal_id is None:
        return False
    m = db.get(Mandal, mandal_id)
    return bool(m and m.serviceable)


def route_km_between(
    db: Session,
    from_mandal_id: int | None,
    to_mandal_id: int | None,
    *,
    override: Decimal | float | None = None,
) -> RouteResult:
    """Resolve the billable road distance between two mandals.

    Precedence: an explicit non-negative ``override`` wins (manual correction /
    backward compatibility); otherwise compute from coordinates; otherwise fall
    back to the configured default so a quote can still be produced.
    """
    serviceable = is_serviceable(db, to_mandal_id) and (
        from_mandal_id is None or is_serviceable(db, from_mandal_id)
    )

    if override is not None and D(override) >= 0:
        return RouteResult(
            route_km=D(override), source="override", serviceable=serviceable,
            from_mandal_id=from_mandal_id, to_mandal_id=to_mandal_id,
        )

    a = db.get(Mandal, from_mandal_id) if from_mandal_id else None
    b = db.get(Mandal, to_mandal_id) if to_mandal_id else None

    if settings.distance_provider == "haversine" and _has_coords(a) and _has_coords(b):
        straight = haversine_km(
            float(a.latitude), float(a.longitude), float(b.latitude), float(b.longitude)
        )
        km = straight * settings.road_distance_factor
        # Same-mandal or co-located centroids still incur a minimum local haul.
        km = max(km, 1.0)
        return RouteResult(
            route_km=D(round(km, 1)), source="haversine", serviceable=serviceable,
            from_mandal_id=from_mandal_id, to_mandal_id=to_mandal_id,
        )

    return RouteResult(
        route_km=D(settings.default_route_km), source="default", serviceable=serviceable,
        from_mandal_id=from_mandal_id, to_mandal_id=to_mandal_id,
    )
