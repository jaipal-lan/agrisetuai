from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import TimestampMixin


class MarketPrice(Base, TimestampMixin):
    """Government-declared mandi price for a commodity at a market, so farmers and
    buyers can see today's official price across India (reference only)."""

    __tablename__ = "market_prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str | None] = mapped_column(String(80), index=True)
    market: Mapped[str] = mapped_column(String(120))
    commodity: Mapped[str] = mapped_column(String(80), index=True)
    variety: Mapped[str | None] = mapped_column(String(80))
    min_price: Mapped[float] = mapped_column(Numeric(12, 2))
    max_price: Mapped[float] = mapped_column(Numeric(12, 2))
    modal_price: Mapped[float] = mapped_column(Numeric(12, 2))
    unit: Mapped[str] = mapped_column(String(16), default="₹/qtl")
    arrivals: Mapped[str | None] = mapped_column(String(40))
    as_of: Mapped[str] = mapped_column(String(40))
    source_name: Mapped[str] = mapped_column(String(160))
    source_url: Mapped[str | None] = mapped_column(String(400))
    stale: Mapped[bool] = mapped_column(default=False)
