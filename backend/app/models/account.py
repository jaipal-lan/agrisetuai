"""Partner payout details and buyer saved delivery addresses.

PayoutAccount — where a seller or transport partner gets paid (UPI or bank), so
payouts are real-world ready. One per user.
SavedAddress — a buyer's reusable delivery address, so reorder/checkout can
prefill the destination.
"""
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import TimestampMixin


class PayoutAccount(Base, TimestampMixin):
    __tablename__ = "payout_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    method: Mapped[str] = mapped_column(String(8), default="upi")  # upi | bank
    upi_id: Mapped[str | None] = mapped_column(String(80))
    account_name: Mapped[str | None] = mapped_column(String(120))
    account_number: Mapped[str | None] = mapped_column(String(40))
    ifsc: Mapped[str | None] = mapped_column(String(16))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class SavedAddress(Base, TimestampMixin):
    __tablename__ = "saved_addresses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    label: Mapped[str] = mapped_column(String(60), default="Home")
    mandal_id: Mapped[int] = mapped_column(ForeignKey("mandals.id"))
    address_line: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    # Captured from the device (browser geolocation) at save time, so checkout /
    # routing can use the exact drop point rather than just the mandal centroid.
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
