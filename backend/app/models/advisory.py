from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import TimestampMixin


class KnowledgeSource(Base, TimestampMixin):
    """Reviewed agronomy / IPM / label-sourced content. Never AI-invented."""

    __tablename__ = "knowledge_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    crop: Mapped[str] = mapped_column(String(40), index=True)
    region: Mapped[str] = mapped_column(String(40), default="AP_TG")
    season: Mapped[str | None] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(200))
    title_te: Mapped[str | None] = mapped_column(String(200))
    keywords: Mapped[dict | None] = mapped_column(JSON)  # list of strings
    content: Mapped[dict] = mapped_column(JSON)
    source_name: Mapped[str] = mapped_column(String(160))
    source_url: Mapped[str | None] = mapped_column(String(400))
    reviewed_by: Mapped[str] = mapped_column(String(120))
    reviewed_on: Mapped[str] = mapped_column(String(40))
    version: Mapped[str] = mapped_column(String(16), default="1")
    status: Mapped[str] = mapped_column(String(16), default="published")


class AdvisoryLog(Base, TimestampMixin):
    """A field agent's advisory / farmer-education record from a visit.

    Field agents double as local agricultural experts; this logs observations,
    recommendations and follow-ups so advice is auditable and trackable.
    """

    __tablename__ = "advisory_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    farmer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("listings.id"))
    crop: Mapped[str | None] = mapped_column(String(40))
    topic: Mapped[str] = mapped_column(String(40), default="advisory")  # advisory|education|follow_up
    observation: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(Text)
    follow_up_on: Mapped[str | None] = mapped_column(String(40))
    # Follow-up tracking: done = the agent has acted on it; notified = a due
    # reminder has already been raised (so it isn't re-raised on every load).
    follow_up_done: Mapped[bool] = mapped_column(Boolean, default=False)
    follow_up_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    # Offline-first idempotency key: a re-synced draft returns the existing row
    # instead of creating a duplicate (mirrors Inspection.client_draft_id).
    client_draft_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    # Farmer's acknowledgement back to the agent — closes the advisory loop so
    # the agent knows the farmer saw and acted on the advice.
    farmer_ack: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    farmer_ack_status: Mapped[str | None] = mapped_column(String(16))  # done | doing | question
    farmer_ack_note: Mapped[str | None] = mapped_column(Text)
    farmer_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Whether the agent has seen this acknowledgement (clears the "new" badge).
    agent_ack_seen: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class CropCase(Base, TimestampMixin):
    __tablename__ = "crop_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    commodity_id: Mapped[int | None] = mapped_column(ForeignKey("commodities.id"))
    crop: Mapped[str] = mapped_column(String(40))
    variety: Mapped[str | None] = mapped_column(String(80))
    growth_stage: Mapped[str | None] = mapped_column(String(40))
    mandal_id: Mapped[int | None] = mapped_column(ForeignKey("mandals.id"))
    symptoms_began: Mapped[str | None] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text)
    media_refs: Mapped[dict | None] = mapped_column(JSON)
    context: Mapped[dict | None] = mapped_column(JSON)
    ai_output: Mapped[dict | None] = mapped_column(JSON)
    confidence: Mapped[str] = mapped_column(String(16), default="low")  # low|medium|high
    knowledge_source_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_sources.id"))
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    escalated: Mapped[bool] = mapped_column(default=False)
    expert_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    expert_review: Mapped[dict | None] = mapped_column(JSON)
    farmer_ack: Mapped[bool] = mapped_column(default=False)


class WeatherSnapshot(Base, TimestampMixin):
    __tablename__ = "weather_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    mandal_id: Mapped[int] = mapped_column(ForeignKey("mandals.id"), index=True)
    provider: Mapped[str] = mapped_column(String(80))
    observed_at: Mapped[str] = mapped_column(String(40))
    forecast_horizon: Mapped[str] = mapped_column(String(24), default="3d")
    payload: Mapped[dict] = mapped_column(JSON)
    stale: Mapped[bool] = mapped_column(default=False)


class CropCalendarTask(Base, TimestampMixin):
    __tablename__ = "crop_calendar_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    crop: Mapped[str] = mapped_column(String(40), index=True)
    window: Mapped[str] = mapped_column(String(80))
    task: Mapped[str] = mapped_column(String(200))
    task_te: Mapped[str | None] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(24), default="general")  # general | reviewed
    source: Mapped[str] = mapped_column(String(160))
    version: Mapped[str] = mapped_column(String(16), default="1")


class Reminder(Base, TimestampMixin):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    calendar_task_id: Mapped[int | None] = mapped_column(ForeignKey("crop_calendar_tasks.id"))
    due_on: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16), default="open")  # open|snoozed|done
    note: Mapped[str | None] = mapped_column(Text)


class MarketPrice(Base, TimestampMixin):
    __tablename__ = "market_prices"

    id: Mapped[int] = mapped_column(primary_key=True)
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


class Scheme(Base, TimestampMixin):
    __tablename__ = "schemes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    name_te: Mapped[str | None] = mapped_column(String(200))
    department: Mapped[str] = mapped_column(String(200))
    eligibility: Mapped[str] = mapped_column(Text)
    documents: Mapped[str | None] = mapped_column(Text)
    apply_route: Mapped[str | None] = mapped_column(Text)
    deadline: Mapped[str | None] = mapped_column(String(80))
    source_url: Mapped[str] = mapped_column(String(400))
    last_checked: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16), default="published")


