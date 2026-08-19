import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session, selectinload

from app.exceptions import ApiError
from app.models import AdminUser, Category, ImportImage, ImportItem, ImportRecord, utc_now
from app.services.activities import record_activity
from app.services.imports import normalize_product_text, normalize_url

EDITABLE_IMPORT_STATUSES = {"draft", "preview_ready"}
ITEM_STATUSES = {"pending", "duplicate", "needs_review", "invalid", "reviewed", "approved", "publishing", "published", "publish_failed"}
IMAGE_STATUSES = {"active", "ignored", "duplicate", "invalid"}


def normalized_space(value: str | None, *, max_length: int, field: str, required: bool = False) -> str | None:
    if value is None:
        return None
    if re.search(r"<[^>]+>", value):
        raise ApiError(422, "IMPORT_REVIEW_INVALID_TEXT", f"{field} nao aceita HTML.")
    cleaned = re.sub(r"\s+", " ", value).strip()
    if required and not cleaned:
        raise ApiError(422, "IMPORT_REVIEW_REQUIRED_FIELD", f"{field} e obrigatorio.")
    if len(cleaned) > max_length:
        raise ApiError(422, "IMPORT_REVIEW_TEXT_TOO_LONG", f"{field} excede o limite de caracteres.")
    return cleaned or None


def get_editable_record(db: Session, import_id: int) -> ImportRecord:
    record = db.query(ImportRecord).options(selectinload(ImportRecord.items)).filter(ImportRecord.id == import_id).first()
    if not record:
        raise ApiError(404, "IMPORT_NOT_FOUND", "Importacao nao encontrada.")
    if record.status not in EDITABLE_IMPORT_STATUSES:
        raise ApiError(409, "IMPORT_NOT_EDITABLE", "Esta importacao nao pode ser editada neste estado.")
    return record


def get_item(db: Session, import_id: int, item_id: int, *, editable: bool = False) -> ImportItem:
    if editable:
        get_editable_record(db, import_id)
    item = db.query(ImportItem).options(selectinload(ImportItem.images), selectinload(ImportItem.import_record)).filter(ImportItem.id == item_id, ImportItem.import_record_id == import_id).first()
    if not item:
        raise ApiError(404, "IMPORT_ITEM_NOT_FOUND", "Item de importacao nao encontrado.")
    return item


def get_image(item: ImportItem, image_id: int) -> ImportImage:
    for image in item.images:
        if image.id == image_id:
            return image
    raise ApiError(404, "IMPORT_IMAGE_NOT_FOUND", "Imagem de importacao nao encontrada.")


def ensure_not_stale(item: ImportItem, expected_updated_at: datetime | None):
    if not expected_updated_at:
        return
    expected = expected_updated_at
    current = item.updated_at
    if expected.tzinfo is None:
        expected = expected.replace(tzinfo=timezone.utc)
    if current and current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    if current and current > expected:
        raise ApiError(409, "IMPORT_ITEM_STALE", "Este item foi alterado por outra sessao. Recarregue os dados antes de salvar.")


def sync_import_item_image_summary(item: ImportItem):
    ordered = sorted(item.images, key=lambda image: (image.position, image.id or 0))
    selected = [image for image in ordered if image.status == "active" and image.is_selected]
    covers = [image for image in selected if image.is_cover]
    if len(covers) != 1:
        for image in ordered:
            image.is_cover = False
        if selected:
            selected[0].is_cover = True
    else:
        for image in ordered:
            if image.id != covers[0].id:
                image.is_cover = False
    active_selected = [image for image in ordered if image.status == "active" and image.is_selected]
    cover = next((image for image in active_selected if image.is_cover), None)
    item.image_urls = [url for image in active_selected if (url := display_image_url(image))]
    item.cover_image_url = display_image_url(cover) if cover else None
    item.image_count = len(active_selected)
    warnings = list(item.warnings or [])
    if not active_selected:
        if "no_selected_images" not in warnings:
            warnings.append("no_selected_images")
        if item.status not in {"duplicate", "invalid"}:
            item.status = "needs_review"
    else:
        warnings = [warning for warning in warnings if warning != "no_selected_images"]
    item.warnings = warnings


def display_image_url(image: ImportImage | None) -> str | None:
    if not image:
        return None
    if image.ingestion_status == "stored" and image.local_public_url:
        try:
            from app.services.import_image_ingestion import stored_file_matches

            if stored_file_matches(image):
                return image.local_public_url
        except Exception:
            return None
    return None


def refresh_import_record_counters(record: ImportRecord):
    items = list(record.items)
    apply_import_record_counters(record, items)


def refresh_import_record_counters_from_db(db: Session, record: ImportRecord):
    items = db.query(ImportItem).filter(ImportItem.import_record_id == record.id).all()
    apply_import_record_counters(record, items)


def apply_import_record_counters(record: ImportRecord, items: list[ImportItem]):
    record.items_found = len(items)
    record.duplicate_items = sum(1 for item in items if item.status == "duplicate")
    record.items_reviewed = sum(1 for item in items if item.status == "reviewed")
    record.items_needs_review = sum(1 for item in items if item.status == "needs_review")
    record.items_approved = sum(1 for item in items if item.status == "approved")
    record.items_published = sum(1 for item in items if item.status == "published")
    record.items_publish_failed = sum(1 for item in items if item.status == "publish_failed")
    record.items_pending = sum(1 for item in items if item.status in {"pending", "needs_review", "invalid"})
    record.items_rejected = 0


def create_import_images_for_item(item: ImportItem, images: list[dict]):
    seen: set[str] = set()
    item.images.clear()
    for position, image in enumerate(images):
        source_url = image.get("src") or image.get("source_url")
        if not source_url:
            continue
        normalized = normalize_url(source_url)
        if normalized in seen:
            continue
        seen.add(normalized)
        item.images.append(
            ImportImage(
                source_url=source_url,
                normalized_source_url=normalized,
                position=position,
                is_cover=position == 0,
                is_selected=True,
                status="active",
                width=_optional_int(image.get("width")),
                height=_optional_int(image.get("height")),
                alt_text=normalized_space(image.get("alt") or image.get("alt_text"), max_length=300, field="alt_text"),
                source_type=image.get("source_type") or "scanner",
                warnings=list(image.get("warnings") or []),
                image_metadata={key: value for key, value in image.items() if key not in {"src", "source_url", "width", "height", "alt", "alt_text", "warnings"}},
            )
        )
    sync_import_item_image_summary(item)


def _optional_int(value) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def update_import_item(db: Session, *, import_id: int, item_id: int, payload, user: AdminUser) -> ImportItem:
    item = get_item(db, import_id, item_id, editable=True)
    ensure_not_stale(item, payload.updated_at)
    changes: dict[str, dict[str, object]] = {}

    data = payload.model_dump(exclude_unset=True)
    data.pop("updated_at", None)
    if "suggested_name" in data:
        value = normalized_space(data["suggested_name"], max_length=300, field="Nome sugerido")
        changes["suggested_name"] = {"from": item.suggested_name, "to": value}
        item.suggested_name = value
    if "suggested_category_id" in data:
        category_id = data["suggested_category_id"]
        category = db.get(Category, category_id) if category_id is not None else None
        if category_id is not None and not category:
            raise ApiError(422, "IMPORT_REVIEW_CATEGORY_NOT_FOUND", "Categoria informada nao existe.")
        changes["suggested_category_id"] = {"from": item.suggested_category_id, "to": category_id}
        item.suggested_category_id = category.id if category else None
        item.suggested_category = category.name if category else None
    if "suggested_model" in data:
        value = normalized_space(data["suggested_model"], max_length=180, field="Modelo")
        changes["suggested_model"] = {"from": item.suggested_model, "to": value}
        item.suggested_model = value
    if "suggested_color" in data:
        value = normalized_space(data["suggested_color"], max_length=120, field="Cor")
        changes["suggested_color"] = {"from": item.suggested_color, "to": value}
        item.suggested_color = value
        item.suggested_color_normalized = normalize_product_text(value) if value else None
    if "warnings" in data:
        warnings = [normalized_space(value, max_length=120, field="Aviso", required=True) for value in data["warnings"]]
        changes["warnings"] = {"from": item.warnings, "to": warnings}
        item.warnings = warnings
    if "status" in data:
        status = data["status"]
        validate_item_status(item, status)
        changes["status"] = {"from": item.status, "to": status}
        item.status = status
        if status == "reviewed":
            item.reviewed_by_id = user.id
            item.reviewed_at = utc_now()

    if item.status == "reviewed":
        validate_reviewed_item(item)
    sync_import_item_image_summary(item)
    refresh_import_record_counters(item.import_record)
    record_activity(db, user_id=user.id, action="review_item", entity_type="import_item", entity_id=item.id, summary=f"Revisao salva: {item.suggested_name or item.source_title or item.id}", metadata={"changes": changes})
    db.flush()
    return item


def validate_item_status(item: ImportItem, status: str):
    if status not in ITEM_STATUSES:
        raise ApiError(422, "IMPORT_REVIEW_INVALID_STATUS", "Status de item invalido.")
    if status == "reviewed" and item.status == "duplicate":
        raise ApiError(409, "IMPORT_REVIEW_DUPLICATE_ITEM", "Item duplicado nao pode ser marcado como revisado nesta fase.")
    if status == "reviewed" and item.status == "invalid":
        raise ApiError(409, "IMPORT_REVIEW_INVALID_ITEM", "Item invalido nao pode ser marcado como revisado silenciosamente.")
    if status in {"approved", "publishing", "published", "publish_failed"}:
        raise ApiError(422, "IMPORT_REVIEW_PUBLICATION_STATUS", "Use as acoes de publicacao para alterar este status.")


def validate_reviewed_item(item: ImportItem):
    name = normalized_space(item.suggested_name, max_length=300, field="Nome sugerido", required=True)
    if not name:
        raise ApiError(422, "IMPORT_REVIEW_NAME_REQUIRED", "Nome sugerido e obrigatorio para marcar como revisado.")
    if not item.suggested_category_id:
        raise ApiError(422, "IMPORT_REVIEW_CATEGORY_REQUIRED", "Categoria e obrigatoria para marcar como revisado.")
    if not any(image.status == "active" and image.is_selected for image in item.images):
        raise ApiError(422, "IMPORT_REVIEW_IMAGE_REQUIRED", "Ao menos uma imagem selecionada e obrigatoria para marcar como revisado.")


def update_import_image(db: Session, *, import_id: int, item_id: int, image_id: int, payload, user: AdminUser) -> ImportImage:
    item = get_item(db, import_id, item_id, editable=True)
    ensure_not_stale(item, payload.updated_at)
    image = get_image(item, image_id)
    data = payload.model_dump(exclude_unset=True)
    data.pop("updated_at", None)
    if "status" in data:
        if data["status"] not in IMAGE_STATUSES:
            raise ApiError(422, "IMPORT_IMAGE_INVALID_STATUS", "Status de imagem invalido.")
        image.status = data["status"]
        if image.status != "active":
            image.is_selected = False
            image.is_cover = False
    if "is_selected" in data:
        image.is_selected = bool(data["is_selected"])
        if not image.is_selected:
            image.is_cover = False
    if "is_cover" in data and data["is_cover"]:
        if image.status != "active" or not image.is_selected:
            raise ApiError(422, "IMPORT_IMAGE_COVER_NOT_SELECTABLE", "Somente imagem ativa e selecionada pode ser capa.")
        for other in item.images:
            other.is_cover = False
        image.is_cover = True
    elif "is_cover" in data and not data["is_cover"]:
        image.is_cover = False
    if image.status == "ignored":
        image.is_selected = False
        image.is_cover = False
    elif image.status == "active" and "is_selected" not in data:
        image.is_selected = True
    sync_import_item_image_summary(item)
    refresh_import_record_counters(item.import_record)
    record_activity(db, user_id=user.id, action="review_image", entity_type="import_image", entity_id=image.id, summary=f"Imagem revisada do item {item.id}", metadata={"item_id": item.id})
    db.flush()
    return image


def reorder_import_images(db: Session, *, import_id: int, item_id: int, image_ids: list[int], updated_at: datetime | None, user: AdminUser) -> ImportItem:
    item = get_item(db, import_id, item_id, editable=True)
    ensure_not_stale(item, updated_at)
    existing_ids = [image.id for image in item.images]
    if len(image_ids) != len(existing_ids) or set(image_ids) != set(existing_ids):
        raise ApiError(422, "IMPORT_IMAGE_REORDER_MISMATCH", "A ordenacao deve conter exatamente as imagens do item.")
    if len(image_ids) != len(set(image_ids)):
        raise ApiError(422, "IMPORT_IMAGE_REORDER_DUPLICATE", "A ordenacao nao pode repetir imagens.")
    by_id = {image.id: image for image in item.images}
    for position, image_id in enumerate(image_ids):
        by_id[image_id].position = position
    sync_import_item_image_summary(item)
    item.images.sort(key=lambda image: (image.position, image.id or 0))
    refresh_import_record_counters(item.import_record)
    record_activity(db, user_id=user.id, action="reorder_images", entity_type="import_item", entity_id=item.id, summary=f"Imagens reordenadas do item {item.id}", metadata={"image_ids": image_ids})
    db.flush()
    return item
