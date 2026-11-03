from datetime import date, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import ListingStatus, OfferStatus, RFQStatus, TimestampMixin


class Listing(Base, TimestampMixin):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    commodity_id: Mapped[int] = mapped_column(ForeignKey("commodities.id"), index=True)
    variety_id: Mapped[int | None] = mapped_column(ForeignKey("varieties.id"))
    grade_spec_id: Mapped[int | None] = mapped_column(ForeignKey("grade_specs.id"))

    harvest_year: Mapped[int | None] = mapped_column()
    available_from: Mapped[date | None] = mapped_column()
    unit: Mapped[str] = mapped_column(String(8), default="kg")

    total_qty: Mapped[float] = mapped_column(Numeric(14, 3))
    reserved_qty: Mapped[float] = mapped_column(Numeric(14, 3), default=0)
    sold_qty: Mapped[float] = mapped_column(Numeric(14, 3), default=0)
    min_order_qty: Mapped[float] = mapped_column(Numeric(14, 3), default=0)

    asking_price: Mapped[float] = mapped_column(Numeric(12, 2))  # per unit
    negotiable: Mapped[bool] = mapped_column(default=True)

    # Farmer-declared cultivation claim; separate from verified certification.
    claim_status: Mapped[str] = mapped_column(String(16), default="conventional")
    claim_evidence: Mapped[dict | None] = mapped_column(JSON)

    mandal_id: Mapped[int | None] = mapped_column(ForeignKey("mandals.id"), index=True)
    pickup_terms: Mapped[str | None] = mapped_column(Text)
    # Farmer-entered product specifications (moisture, cleanliness, drying, packing…).
    specifications: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16), default=ListingStatus.DRAFT, index=True
    )

    # Optional pre-sale agent verification of the lot at the farm gate. Distinct
    # from the per-order inspection; surfaces an "agent verified" badge.
    agent_verified: Mapped[bool] = mapped_column(default=False)
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_note: Mapped[str | None] = mapped_column(String(300))

    media: Mapped[list["ListingMedia"]] = relationship(back_populates="listing")

    @property
    def available_qty(self):
        return self.total_qty - self.reserved_qty - self.sold_qty


class ListingMedia(Base, TimestampMixin):
    __tablename__ = "listing_media"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    object_key: Mapped[str] = mapped_column(String(300))
    media_type: Mapped[str] = mapped_column(String(16), default="image")
    checksum: Mapped[str | None] = mapped_column(String(64))
    access_class: Mapped[str] = mapped_column(String(16), default="public")

    listing: Mapped[Listing] = relationship(back_populates="media")


class RFQ(Base, TimestampMixin):
    __tablename__ = "rfqs"

    id: Mapped[int] = mapped_column(primary_key=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    commodity_id: Mapped[int] = mapped_column(ForeignKey("commodities.id"), index=True)
    variety_id: Mapped[int | None] = mapped_column(ForeignKey("varieties.id"))
    grade_spec_id: Mapped[int | None] = mapped_column(ForeignKey("grade_specs.id"))

    requested_qty: Mapped[float] = mapped_column(Numeric(14, 3))
    unit: Mapped[str] = mapped_column(String(8), default="kg")
    target_price: Mapped[float | None] = mapped_column(Numeric(12, 2))

    destination_mandal_id: Mapped[int | None] = mapped_column(ForeignKey("mandals.id"))
    delivery_window: Mapped[str | None] = mapped_column(String(80))
    packaging: Mapped[str | None] = mapped_column(String(80))
    acceptable_variation: Mapped[dict | None] = mapped_column(JSON)
    inspection_required: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(String(16), default=RFQStatus.OPEN, index=True)


class Offer(Base, TimestampMixin):
    """A negotiation thread between one buyer and one seller.

    Each proposal is an immutable OfferVersion; a counteroffer appends a new version.
    """

    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("listings.id"), index=True)
    rfq_id: Mapped[int | None] = mapped_column(ForeignKey("rfqs.id"), index=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    status: Mapped[str] = mapped_column(String(16), default=OfferStatus.OPEN, index=True)
    accepted_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("offer_versions.id")
    )

    versions: Mapped[list["OfferVersion"]] = relationship(
        back_populates="offer",
        order_by="OfferVersion.version_no",
        foreign_keys="OfferVersion.offer_id",
    )


class OfferVersion(Base):
    """Immutable once created. A counteroffer creates the next version_no."""

    __tablename__ = "offer_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id"), index=True)
    version_no: Mapped[int] = mapped_column()
    proposer_role: Mapped[str] = mapped_column(String(8))  # buyer | seller
    proposer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    price_per_unit: Mapped[float] = mapped_column(Numeric(12, 2))
    quantity: Mapped[float] = mapped_column(Numeric(14, 3))
    unit: Mapped[str] = mapped_column(String(8), default="kg")
    grade_spec_id: Mapped[int | None] = mapped_column(ForeignKey("grade_specs.id"))
    delivery_terms: Mapped[dict | None] = mapped_column(JSON)
    inspection_conditions: Mapped[dict | None] = mapped_column(JSON)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    offer: Mapped[Offer] = relationship(back_populates="versions", foreign_keys=[offer_id])


class Watch(Base, TimestampMixin):
    """A buyer's watched commodity with an optional target price for alerts."""

    __tablename__ = "watches"
    __table_args__ = (UniqueConstraint("user_id", "commodity_id", name="uq_watch_user_commodity"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    commodity_id: Mapped[int] = mapped_column(ForeignKey("commodities.id"), index=True)
    target_price: Mapped[float | None] = mapped_column(Numeric(12, 2))


class SavedSearch(Base, TimestampMixin):
    """A buyer's saved marketplace search (criteria JSON) with optional alerts.

    When a new listing is published that matches the criteria, the buyer is
    alerted (if ``alert`` is on). ``last_match_id`` tracks the highest matching
    listing id already alerted or viewed, so "new since you last looked" and the
    alert de-duplication both work off one marker.
    """

    __tablename__ = "saved_searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    label: Mapped[str | None] = mapped_column(String(120))
    # {q, category, mandal_id, claim_status, max_price, min_qty} — any subset.
    criteria: Mapped[dict] = mapped_column(JSON, default=dict)
    alert: Mapped[bool] = mapped_column(default=True)
    last_match_id: Mapped[int] = mapped_column(default=0)
