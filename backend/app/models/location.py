from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class State(Base):
    __tablename__ = "states"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)

    districts: Mapped[list["District"]] = relationship(back_populates="state")


class District(Base):
    __tablename__ = "districts"

    id: Mapped[int] = mapped_column(primary_key=True)
    state_id: Mapped[int] = mapped_column(ForeignKey("states.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))

    state: Mapped[State] = relationship(back_populates="districts")
    mandals: Mapped[list["Mandal"]] = relationship(back_populates="district")


class Mandal(Base):
    __tablename__ = "mandals"

    id: Mapped[int] = mapped_column(primary_key=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    # Whether the platform currently serves this mandal (agents/logistics present).
    serviceable: Mapped[bool] = mapped_column(default=True)

    district: Mapped[District] = relationship(back_populates="mandals")
