from decimal import Decimal

from sqlalchemy import JSON, Boolean, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import TimestampMixin


class Commodity(Base, TimestampMixin):
    __tablename__ = "commodities"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(40), index=True)  # rice, pulses, spices...
    name: Mapped[str] = mapped_column(String(80))
    product_form: Mapped[str] = mapped_column(String(40))  # e.g. paddy vs milled rice
    name_te: Mapped[str | None] = mapped_column(String(80))  # Telugu label
    unit: Mapped[str] = mapped_column(String(8), default="kg")
    # Handling class drives per-kg transport rate selection.
    handling_class: Mapped[str] = mapped_column(String(24), default="dry_grain")
    # Minimum order quantity for this product (superadmin-configurable). Justifies
    # inspection/packing/transport cost: e.g. rice 25 kg, dal 10 kg, chilli 5 kg.
    min_order_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    # Soft-delete: inactive commodities drop out of the catalogue (farmers/buyers
    # can't list/request them) but the row stays so existing listings/orders/
    # prices that reference it keep resolving. Removal is a request→approve flow:
    # a field leader/manager requests, the superadmin approves (sets active=False).
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    deletion_requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    deletion_requested_at: Mapped[str | None] = mapped_column(String(40))
    deletion_reason: Mapped[str | None] = mapped_column(String(300))

    varieties: Mapped[list["Variety"]] = relationship(back_populates="commodity")
    grade_specs: Mapped[list["GradeSpec"]] = relationship(back_populates="commodity")


class Variety(Base, TimestampMixin):
    __tablename__ = "varieties"

    id: Mapped[int] = mapped_column(primary_key=True)
    commodity_id: Mapped[int] = mapped_column(ForeignKey("commodities.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    name_te: Mapped[str | None] = mapped_column(String(80))

    commodity: Mapped[Commodity] = relationship(back_populates="varieties")


class GradeSpec(Base, TimestampMixin):
    __tablename__ = "grade_specs"

    id: Mapped[int] = mapped_column(primary_key=True)
    commodity_id: Mapped[int] = mapped_column(ForeignKey("commodities.id"), index=True)
    code: Mapped[str] = mapped_column(String(24))  # e.g. "A", "FAQ"
    label: Mapped[str] = mapped_column(String(120))
    # Measurable attributes for inspection, e.g. {"max_moisture_pct": 14, ...}
    attributes: Mapped[dict | None] = mapped_column(JSON)
    spec_version: Mapped[int] = mapped_column(default=1)

    commodity: Mapped[Commodity] = relationship(back_populates="grade_specs")
