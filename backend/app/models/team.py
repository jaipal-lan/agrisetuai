"""Field-leader tools: targets set for agents, and team meetings.

A field leader (mandal) or field manager (district) sets a measurable target for
an agent over a period and schedules/records team meetings. Progress against a
target is computed live from the agent's actual work, so these tables store only
the goal + the meeting record, not derived counts.
"""
from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import TimestampMixin

# Metrics a target can be set on. Each maps to a live count in the team API.
TARGET_METRICS = ("inspections", "orders_assigned")


class AgentTarget(Base, TimestampMixin):
    """A goal a leader sets for one field agent over a date window."""

    __tablename__ = "agent_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    set_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    metric: Mapped[str] = mapped_column(String(32), default="inspections")
    target_value: Mapped[int] = mapped_column(Integer, default=0)
    period_start: Mapped[str] = mapped_column(String(10))  # ISO date
    period_end: Mapped[str] = mapped_column(String(10))    # ISO date (inclusive)
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | archived


class TeamMeeting(Base, TimestampMixin):
    """A team meeting a leader schedules and later records minutes for."""

    __tablename__ = "team_meetings"

    id: Mapped[int] = mapped_column(primary_key=True)
    organizer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    scheduled_at: Mapped[str] = mapped_column(String(32))  # ISO datetime
    location: Mapped[str | None] = mapped_column(String(160))
    agenda: Mapped[str | None] = mapped_column(Text)
    attendee_ids: Mapped[list | None] = mapped_column(JSON)  # invited agent user ids
    attended_ids: Mapped[list | None] = mapped_column(JSON)  # who showed up
    notes: Mapped[str | None] = mapped_column(Text)          # minutes
    status: Mapped[str] = mapped_column(String(16), default="scheduled")  # scheduled | done | cancelled
    mandal_id: Mapped[int | None] = mapped_column(ForeignKey("mandals.id"))
    reminded: Mapped[bool] = mapped_column(default=False)  # a pre-meeting reminder was sent
