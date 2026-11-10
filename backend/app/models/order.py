from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import OrderStatus, TimestampMixin


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    offer_id: Mapped[int | None] = mapped_column(ForeignKey("offers.id"))
    assigned_agent_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)

    status: Mapped[str] = mapped_column(
        String(32), default=OrderStatus.PROVISIONAL_AGREEMENT, index=True
    )

    # Immutable snapshot of accepted terms (price/qty/grade/delivery/inspection).
    accepted_terms: Mapped[dict] = mapped_column(JSON)
    # Full server-computed price quote snapshot + the fee-rule versions it used.
    quote: Mapped[dict | None] = mapped_column(JSON)
    pricing_rule_version: Mapped[int | None] = mapped_column()
    cancellation_policy_version: Mapped[int] = mapped_column(default=1)

    buyer_total: Mapped[float | None] = mapped_column(Numeric(14, 2))
    seller_payable: Mapped[float | None] = mapped_column(Numeric(14, 2))

    # A short packing video (object key) captured when the lot is sealed, before
    # dispatch — proof of what was packed for the buyer who paid.
    packing_video: Mapped[str | None] = mapped_column(String(200))

    # Idempotency key supplied at confirmation to prevent duplicate orders.
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True)

    lines: Mapped[list["OrderLine"]] = relationship(back_populates="order")
    status_events: Mapped[list["OrderStatusEvent"]] = relationship(
        back_populates="order", order_by="OrderStatusEvent.id"
    )


class OrderLine(Base):
    __tablename__ = "order_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("listings.id"))
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("lots.id"))

    quantity: Mapped[float] = mapped_column(Numeric(14, 3))
    accepted_quantity: Mapped[float | None] = mapped_column(Numeric(14, 3))
    price_per_unit: Mapped[float] = mapped_column(Numeric(12, 2))
    unit: Mapped[str] = mapped_column(String(8), default="kg")
    grade_spec_id: Mapped[int | None] = mapped_column(ForeignKey("grade_specs.id"))
    allocation_status: Mapped[str] = mapped_column(String(16), default="reserved")

    order: Mapped[Order] = relationship(back_populates="lines")


class OrderStatusEvent(Base):
    """Append-only log of every order state transition (who, why, when)."""

    __tablename__ = "order_status_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reason_code: Mapped[str | None] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    order: Mapped[Order] = relationship(back_populates="status_events")


class Inspection(Base, TimestampMixin):
    __tablename__ = "inspections"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("lots.id"))
    agent_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    declared_qty: Mapped[float | None] = mapped_column(Numeric(14, 3))
    gross_weight: Mapped[float | None] = mapped_column(Numeric(14, 3))
    tare_weight: Mapped[float | None] = mapped_column(Numeric(14, 3))
    net_qty: Mapped[float | None] = mapped_column(Numeric(14, 3))
    scale_ref: Mapped[str | None] = mapped_column(String(80))

    checklist: Mapped[dict | None] = mapped_column(JSON)
    measurements: Mapped[dict | None] = mapped_column(JSON)
    evidence: Mapped[dict | None] = mapped_column(JSON)  # list of media refs

    outcome: Mapped[str | None] = mapped_column(String(24))
    reason_codes: Mapped[dict | None] = mapped_column(JSON)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # Local draft id for offline-first sync dedupe.
    client_draft_id: Mapped[str | None] = mapped_column(String(64), unique=True)


class Lot(Base, TimestampMixin):
    __tablename__ = "lots"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    parent_lot_id: Mapped[int | None] = mapped_column(ForeignKey("lots.id"))
    source_listing_id: Mapped[int | None] = mapped_column(ForeignKey("listings.id"))
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    commodity_id: Mapped[int] = mapped_column(ForeignKey("commodities.id"))
    quantity: Mapped[float] = mapped_column(Numeric(14, 3))
    grade_spec_id: Mapped[int | None] = mapped_column(ForeignKey("grade_specs.id"))
    seal_ref: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(24), default="created")


class LotEvent(Base):
    __tablename__ = "lot_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    payload: Mapped[dict | None] = mapped_column(JSON)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Package(Base, TimestampMixin):
    __tablename__ = "packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"), index=True)
    qr_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    net_weight: Mapped[float] = mapped_column(Numeric(14, 3))
    package_count: Mapped[int] = mapped_column(default=1)
    label_data: Mapped[dict | None] = mapped_column(JSON)
    packing_status: Mapped[str] = mapped_column(String(16), default="packed")


class Shipment(Base, TimestampMixin):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    carrier_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # Assigned transport courier (a company we tie up with) + snapshot of its name.
    courier_id: Mapped[int | None] = mapped_column(ForeignKey("carriers.id"))
    courier_name: Mapped[str | None] = mapped_column(String(120))
    route: Mapped[dict | None] = mapped_column(JSON)
    vehicle_class: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24), default="created")
    eta_source: Mapped[str | None] = mapped_column(String(40))
    proof_of_delivery: Mapped[dict | None] = mapped_column(JSON)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True)

    events: Mapped[list["ShipmentEvent"]] = relationship(back_populates="shipment")


class ShipmentEvent(Base):
    __tablename__ = "shipment_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"), index=True)
    event: Mapped[str] = mapped_column(String(40))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    location_precision: Mapped[str | None] = mapped_column(String(24))
    evidence_ref: Mapped[str | None] = mapped_column(String(300))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    shipment: Mapped[Shipment] = relationship(back_populates="events")
