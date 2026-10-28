from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.common import utcnow


def record(
    db: Session,
    *,
    actor_id: int | None,
    action: str,
    object_type: str | None = None,
    object_id: str | int | None = None,
    reason: str | None = None,
    old_values: dict | None = None,
    new_values: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id is not None else None,
        reason=reason,
        old_values=old_values,
        new_values=new_values,
        at=utcnow(),
    )
    db.add(entry)
    return entry
