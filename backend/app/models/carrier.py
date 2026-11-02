from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import TimestampMixin


class Carrier(Base, TimestampMixin):
    """A transport courier the platform ties up with (multiple couriers supported).

    Onboarded and KYC-gated by the superadmin; assignable to a shipment.
    """

    __tablename__ = "carriers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    contact_email: Mapped[str | None] = mapped_column(String(120))
    # Vehicle classes offered, e.g. ["bike", "auto", "mini_truck", "truck"].
    vehicle_classes: Mapped[list | None] = mapped_column(JSON)
    # Service areas as mandal/district/state names (free-form for the pilot).
    service_areas: Mapped[list | None] = mapped_column(JSON)
    kyc_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|verified|suspended
    active: Mapped[bool] = mapped_column(default=True)
    rating: Mapped[float | None] = mapped_column()
