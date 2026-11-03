from sqlalchemy.orm import Session

from app.models.support import Notification
from app.models.user import User

# User-muteable notification categories (key, label). These are the proactive
# nudges that can get noisy; order-lifecycle and account/security alerts are
# intentionally NOT here, so they are always delivered.
MUTEABLE_CATEGORIES: list[tuple[str, str]] = [
    ("offers", "Offers & counter-offers"),
    ("price_alerts", "Price alerts & watched products"),
    ("requests", "Buyer requests matching your crops"),
    ("announcements", "Platform announcements"),
    ("advisory", "Crop advisory updates"),
]
_CATEGORY_KEYS = {k for k, _ in MUTEABLE_CATEGORIES}

# Map a notification's object_type to a muteable category. Anything not listed
# here (order, dispute, payout, user, ticket, …) is transactional/critical and
# always sent regardless of preferences.
_CATEGORY_BY_OBJECT: dict[str, str] = {
    "offer": "offers",
    "product": "price_alerts",
    "saved_search": "price_alerts",
    "rfq": "requests",
    "announcement": "announcements",
    "crop_case": "advisory",
}


def category_for(object_type: str | None) -> str | None:
    """The muteable category for an object_type, or None if always-on."""
    return _CATEGORY_BY_OBJECT.get(object_type or "")


def send(
    db: Session,
    *,
    user_id: int,
    title: str,
    body: str,
    object_type: str | None = None,
    object_id: str | int | None = None,
    channel: str = "in_app",
) -> Notification | None:
    """Create an in-app notification, unless the recipient has muted this
    category. Returns the Notification, or None if suppressed by preference."""
    category = category_for(object_type)
    if category:
        user = db.get(User, user_id)  # identity-map hit if already loaded
        if user is not None and category in (user.muted_notifications or []):
            return None
    n = Notification(
        user_id=user_id,
        title=title,
        body=body,
        channel=channel,
        object_type=object_type,
        object_id=str(object_id) if object_id is not None else None,
    )
    db.add(n)
    return n
