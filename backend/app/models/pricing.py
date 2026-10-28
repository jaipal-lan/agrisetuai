from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import TimestampMixin


class PricingRule(Base, TimestampMixin):
    """Versioned, superadmin-configured fee/transport rule.

    Publishing a new version never mutates an existing one. A confirmed order
    snapshots the exact version it used, so republishing cannot reprice it.
    """

    __tablename__ = "pricing_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(12), default="draft")  # draft|published|retired

    # Scope — null means "applies everywhere / all classes".
    service_mandal_id: Mapped[int | None] = mapped_column(ForeignKey("mandals.id"))
    handling_class: Mapped[str | None] = mapped_column(String(24))

    currency: Mapped[str] = mapped_column(String(4), default="INR")

    # Transport components.
    rate_per_kg: Mapped[float] = mapped_column(Numeric(10, 4), default=0)
    rate_per_km: Mapped[float] = mapped_column(Numeric(10, 4), default=0)
    fixed_pickup_fee: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    min_transport_charge: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    max_transport_charge: Mapped[float | None] = mapped_column(Numeric(10, 2))

    # Platform service fee: percentage of product value OR a flat fee.
    service_fee_pct: Mapped[float] = mapped_column(Numeric(6, 3), default=0)
    service_fee_flat: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    service_fee_payer: Mapped[str] = mapped_column(String(8), default="buyer")  # buyer|seller

    # Inspection + packing.
    inspection_fee: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    packing_fee: Mapped[float] = mapped_column(Numeric(10, 2), default=0)

    # Tax (applied to the taxable base defined by the engine).
    tax_pct: Mapped[float] = mapped_column(Numeric(6, 3), default=0)

    surcharges: Mapped[dict | None] = mapped_column(JSON)

    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(String(300))
    requires_second_approval: Mapped[bool] = mapped_column(Boolean, default=False)
