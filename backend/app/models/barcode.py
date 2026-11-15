"""Barcode/QR bag tracking — the single source of truth for goods movement.

Each confirmed order is split into one or more physical bags, each with a unique
scannable code (AGRI-{orderId}-BAG-{nn}). Every scan appends an immutable
BagScan (who/where/when/stage) and advances the bag's status along:

    created -> picked_up -> at_collection -> in_transit -> delivered
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import TimestampMixin


class Bag(Base, TimestampMixin):
    __tablename__ = "bags"

    id: Mapped[int] = mapped_column(primary_key=True)
    bag_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    commodity_id: Mapped[int | None] = mapped_column(ForeignKey("commodities.id"))
    bag_no: Mapped[int] = mapped_column()
    weight: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    status: Mapped[str] = mapped_column(String(24), default="created", index=True)
    last_scan_at: Mapped[str | None] = mapped_column(String(40))
    last_lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    last_lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))

    scans: Mapped[list["BagScan"]] = relationship(
        back_populates="bag", order_by="BagScan.id"
    )


class BagScan(Base, TimestampMixin):
    """Immutable scan event. author/role captured; corrections are logged, not
    overwritten (a correction is a new scan flagged `corrected`)."""

    __tablename__ = "bag_scans"

    id: Mapped[int] = mapped_column(primary_key=True)
    bag_id: Mapped[int] = mapped_column(ForeignKey("bags.id"), index=True)
    stage: Mapped[str] = mapped_column(String(24))  # pickup|collection|loading|delivery|correction
    to_status: Mapped[str] = mapped_column(String(24))
    scanned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str | None] = mapped_column(String(24))
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    note: Mapped[str | None] = mapped_column(Text)
    corrected: Mapped[bool] = mapped_column(Boolean, default=False)
    correction_reason: Mapped[str | None] = mapped_column(String(300))

    bag: Mapped[Bag] = relationship(back_populates="scans")
