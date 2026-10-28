from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import TimestampMixin


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32), default="mock")
    provider_ref: Mapped[str | None] = mapped_column(String(120))
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(4), default="INR")
    status: Mapped[str] = mapped_column(String(16), default="created")  # created|paid|failed|refunded
    raw: Mapped[dict | None] = mapped_column(JSON)


class LedgerEntry(Base):
    """Append-only, double-entry-friendly ledger.

    The ledger — not the mutable Order.status — is the financial source of truth.
    Each economic event writes balanced debit/credit rows sharing a `txn_group`.
    """

    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    txn_group: Mapped[str] = mapped_column(String(64), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    account: Mapped[str] = mapped_column(String(40), index=True)
    # account examples: buyer_receivable, platform_revenue, seller_payable,
    #   transport_payable, agent_fee, tax_payable, refunds, payment_fees
    direction: Mapped[str] = mapped_column(String(8))  # debit | credit
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(4), default="INR")
    memo: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Payout(Base, TimestampMixin):
    __tablename__ = "payouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(4), default="INR")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    provider_ref: Mapped[str | None] = mapped_column(String(120))
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
