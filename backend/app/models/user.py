from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(32), index=True)
    preferred_language: Mapped[str] = mapped_column(String(8), default="te")  # te | en
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|suspended
    consent_at: Mapped[str | None] = mapped_column(String(40))
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    # Bump to revoke all outstanding sessions (staff leave, logout-all).
    token_version: Mapped[int] = mapped_column(default=0)
    # Muted proactive-notification categories (keys from notify.MUTEABLE_CATEGORIES).
    # Transactional order/account alerts are never muteable and ignore this.
    muted_notifications: Mapped[list | None] = mapped_column(JSON, default=list)
    # Categories the user wants batched into a once-a-day digest instead of
    # pinging the bell instantly. A category muted above takes precedence.
    digest_notifications: Mapped[list | None] = mapped_column(JSON, default=list)
    # Watermark: the highest deferred-notification id already rolled into a sent
    # digest, so the scheduler only summarises newly-batched alerts.
    last_digest_id: Mapped[int] = mapped_column(default=0)

    # Optional organisation membership (FPO / business).
    organisation_id: Mapped[int | None] = mapped_column(
        ForeignKey("organisations.id"), index=True
    )

    farmer_profile: Mapped["FarmerProfile | None"] = relationship(
        back_populates="user", uselist=False
    )
    buyer_profile: Mapped["BuyerProfile | None"] = relationship(
        back_populates="user", uselist=False
    )
    agent_profile: Mapped["AgentProfile | None"] = relationship(
        back_populates="user",
        uselist=False,
        foreign_keys="AgentProfile.user_id",
    )


class Organisation(Base, TimestampMixin):
    __tablename__ = "organisations"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(16))  # fpo | business | platform
    legal_name: Mapped[str] = mapped_column(String(200))
    verification_status: Mapped[str] = mapped_column(String(16), default="unverified")
    licence_refs: Mapped[dict | None] = mapped_column(JSON)


class FarmerProfile(Base, TimestampMixin):
    __tablename__ = "farmer_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    state_id: Mapped[int | None] = mapped_column(ForeignKey("states.id"))
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"))
    mandal_id: Mapped[int | None] = mapped_column(ForeignKey("mandals.id"), index=True)
    village: Mapped[str | None] = mapped_column(String(120))
    pickup_point: Mapped[str | None] = mapped_column(String(200))
    # Payout beneficiary is referenced, never stored raw/returned by the API.
    payout_beneficiary_ref: Mapped[str | None] = mapped_column(String(80))
    verification_status: Mapped[str] = mapped_column(String(16), default="unverified")

    user: Mapped[User] = relationship(back_populates="farmer_profile")


class BuyerProfile(Base, TimestampMixin):
    __tablename__ = "buyer_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    buyer_type: Mapped[str] = mapped_column(String(16), default="household")
    delivery_zones: Mapped[dict | None] = mapped_column(JSON)
    billing: Mapped[dict | None] = mapped_column(JSON)
    verification_status: Mapped[str] = mapped_column(String(16), default="unverified")

    user: Mapped[User] = relationship(back_populates="buyer_profile")


class AgentProfile(Base, TimestampMixin):
    __tablename__ = "agent_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    # Trainee | Field Agricultural Advisor | Senior Agronomy Reviewer
    skill_level: Mapped[str] = mapped_column(String(40), default="Trainee")
    service_mandals: Mapped[list | None] = mapped_column(JSON)  # list of mandal ids
    languages: Mapped[str | None] = mapped_column(String(120))
    equipment: Mapped[dict | None] = mapped_column(JSON)
    training_modules: Mapped[dict | None] = mapped_column(JSON)
    supervisor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    performance_status: Mapped[str] = mapped_column(String(16), default="ok")

    user: Mapped[User] = relationship(
        back_populates="agent_profile", foreign_keys=[user_id]
    )
