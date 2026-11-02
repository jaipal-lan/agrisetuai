from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import TimestampMixin


class Review(Base, TimestampMixin):
    """A buyer's rating of a farmer (seller) or a transport courier after an order."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    subject_type: Mapped[str] = mapped_column(String(16), index=True)  # farmer | courier
    subject_id: Mapped[int] = mapped_column(Integer, index=True)  # user id or carrier id
    rating: Mapped[int] = mapped_column(Integer)  # 1..5
    comment: Mapped[str | None] = mapped_column(Text)
