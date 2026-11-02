from sqlalchemy.orm import Session

from app.models.support import Notification


def send(
    db: Session,
    *,
    user_id: int,
    title: str,
    body: str,
    object_type: str | None = None,
    object_id: str | int | None = None,
    channel: str = "in_app",
) -> Notification:
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
