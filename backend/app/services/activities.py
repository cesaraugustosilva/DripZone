from sqlalchemy.orm import Session

from app.models import Activity


def record_activity(
    db: Session,
    *,
    user_id: int | None,
    action: str,
    summary: str,
    entity_type: str | None = None,
    entity_id: str | int | None = None,
    metadata: dict | None = None,
    ip_address: str | None = None,
) -> Activity:
    activity = Activity(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        summary=summary,
        activity_metadata=metadata,
        ip_address=ip_address,
    )
    db.add(activity)
    return activity
