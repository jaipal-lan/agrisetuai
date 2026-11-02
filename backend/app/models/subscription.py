from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import TimestampMixin


class SubscriptionPlan(Base, TimestampMixin):
    """A membership tier a farmer or buyer can subscribe to."""

    __tablename__ = "subscription_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    name_te: Mapped[str | None] = mapped_column(String(80))
    audience: Mapped[str] = mapped_column(String(20), index=True)  # farmer | buyer
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    period_days: Mapped[int] = mapped_column(default=30)
    # {max_active_listings, fee_discount_pct, featured_listings, advisory_full,
    #  priority_support, rfq_boost}
    benefits: Mapped[dict | None] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(default=True)
    sort: Mapped[int] = mapped_column(default=0)


class Subscription(Base, TimestampMixin):
    """A user's purchased membership. Benefits snapshotted so later plan edits
    don't retroactively change an active subscription."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    plan_code: Mapped[str] = mapped_column(String(40), index=True)
    plan_name: Mapped[str] = mapped_column(String(80))
    audience: Mapped[str] = mapped_column(String(20))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    benefits: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)  # active|expired|cancelled
    started_at: Mapped[datetime] = mapped_column()
    expires_at: Mapped[datetime] = mapped_column(index=True)
    txn_group: Mapped[str | None] = mapped_column(String(64))
