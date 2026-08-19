from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_roles
from app.models import Activity
from app.schemas.misc import ActivityRead
from app.utils.pagination import pagination_meta

router = APIRouter()


@router.get("", dependencies=[Depends(require_roles("owner", "admin"))])
def list_activities(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    query = db.query(Activity).order_by(Activity.created_at.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [ActivityRead.model_validate(item) for item in items], "pagination": pagination_meta(page, page_size, total)}
