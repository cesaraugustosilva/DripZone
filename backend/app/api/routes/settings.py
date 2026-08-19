from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import current_user, require_csrf, require_roles
from app.models import StoreSetting
from app.schemas.misc import SettingsUpdate
from app.services.activities import record_activity

router = APIRouter(dependencies=[Depends(current_user)])

ALLOWED_KEYS = {
    "store_name": "string",
    "store_description": "string",
    "currency": "string",
    "locale": "string",
    "timezone": "string",
    "products_per_page": "integer",
    "show_out_of_stock": "boolean",
    "default_sort": "string",
    "empty_catalog_message": "string",
    "free_shipping_enabled": "boolean",
    "free_shipping_minimum": "decimal",
    "installments_enabled": "boolean",
    "max_installments": "integer",
    "pix_enabled": "boolean",
    "admin_table_density": "string",
}


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    values = {item.key: coerce(item.value, item.value_type) for item in db.query(StoreSetting).all()}
    return {key: values.get(key) for key in ALLOWED_KEYS}


@router.put("", dependencies=[Depends(require_csrf)])
def put_settings(payload: SettingsUpdate, db: Session = Depends(get_db), user=Depends(require_roles("owner", "admin"))):
    for key, value in payload.model_dump(exclude_unset=True).items():
        item = db.query(StoreSetting).filter(StoreSetting.key == key).first()
        if not item:
            item = StoreSetting(key=key, value_type=ALLOWED_KEYS[key])
            db.add(item)
        item.value = serialize(value)
    record_activity(db, user_id=user.id, action="settings_update", entity_type="settings", summary="Configurações alteradas.")
    return get_settings(db)


def serialize(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def coerce(value: str | None, value_type: str):
    if value is None:
        return None
    if value_type == "boolean":
        return value == "true"
    if value_type == "integer":
        return int(value)
    return value
