from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import TimestampMixin


class SupportTicket(Base, TimestampMixin):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    opener_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    issue_type: Mapped[str] = mapped_column(String(40))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    sla_hours: Mapped[int] = mapped_column(default=48)


class Dispute(Base, TimestampMixin):
    __tablename__ = "disputes"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    opener_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    issue_type: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    decision: Mapped[str | None] = mapped_column(String(40))
    decision_note: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    financial_consequence: Mapped[dict | None] = mapped_column(JSON)


class ConsentRecord(Base, TimestampMixin):
    __tablename__ = "consent_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))  # terms | privacy | marketing | advisory
    granted: Mapped[bool] = mapped_column(default=True)
    version: Mapped[str] = mapped_column(String(20), default="1")


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(16), default="in_app")
    object_type: Mapped[str | None] = mapped_column(String(32))
    object_id: Mapped[str | None] = mapped_column(String(40))
    read_at: Mapped[str | None] = mapped_column(String(40))


class MediaObject(Base, TimestampMixin):
    __tablename__ = "media_objects"

    id: Mapped[int] = mapped_column(primary_key=True)
    object_key: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    media_type: Mapped[str] = mapped_column(String(16), default="image")
    content_type: Mapped[str] = mapped_column(String(80), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(default=0)
    checksum: Mapped[str | None] = mapped_column(String(64))
    access_class: Mapped[str] = mapped_column(String(16), default="restricted")


class QualityCase(Base, TimestampMixin):
    __tablename__ = "quality_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    opener_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("listings.id"))
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("lots.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    layer: Mapped[str] = mapped_column(String(24), default="camera")  # camera|instrument|lab|qr|ai_flag
    notes: Mapped[str | None] = mapped_column(Text)
    media_refs: Mapped[dict | None] = mapped_column(JSON)
    flags: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="open")
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    review_note: Mapped[str | None] = mapped_column(Text)
