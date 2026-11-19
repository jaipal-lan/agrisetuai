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
    "advisory_log": "advisory",
    "reminder": "advisory",
}


# Transactional events worth pushing to WhatsApp (gated). Deliberately a small
# set — the moments a farmer/buyer really wants off-app: order lifecycle, money
# movements, account/security and disputes. Noisy/proactive categories (offers,
# rfq, announcements, price alerts) and bulk broadcasts are intentionally
# excluded, both to avoid spam and to keep broadcast loops off the network.
_WHATSAPP_OBJECTS = {"order", "payout", "payout_account", "dispute", "user"}


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
    """Create an in-app notification, honouring the recipient's per-category
    delivery preference:
      - muted    → suppressed entirely (returns None, no row created);
      - digest   → created but `deferred=True`, so it skips the instant bell and
                   is rolled into the daily digest instead;
      - instant  → created normally (the default).
    Transactional/critical object_types have no category and are always instant."""
    category = category_for(object_type)
    deferred = False
    if category:
        user = db.get(User, user_id)  # identity-map hit if already loaded
        if user is not None:
            if category in (user.muted_notifications or []):
                return None
            if category in (user.digest_notifications or []):
                deferred = True
    n = Notification(
        user_id=user_id,
        title=title,
        body=body,
        channel=channel,
        object_type=object_type,
        object_id=str(object_id) if object_id is not None else None,
        deferred=deferred,
    )
    db.add(n)

    # Mirror important transactional alerts to WhatsApp (gated: no-op unless
    # configured). Skipped for digest-deferred items and for anything outside the
    # small transactional set, so proactive nudges and bulk broadcasts never hit
    # the network here. Best-effort — a messaging failure never breaks the caller.
    if not deferred and object_type in _WHATSAPP_OBJECTS:
        from app.services import whatsapp
        if whatsapp.enabled():
            recipient = db.get(User, user_id)
            if recipient is not None and recipient.phone:
                whatsapp.send_text(recipient.phone, f"{title}\n{body}")
    return n
