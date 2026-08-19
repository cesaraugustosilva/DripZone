from decimal import Decimal
import shutil
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.exceptions import ApiError
from app.models import AdminUser, Brand, Category, ImportItem, ImportRecord, Product, ProductImage, utc_now
from app.services.activities import record_activity
from app.services.import_image_ingestion import image_path_from_storage_path, selected_active_images, stored_file_matches, product_storage_root
from app.services.import_review import ensure_not_stale, get_editable_record, get_item, refresh_import_record_counters
from app.utils.files import ensure_child_path
from app.utils.slug import unique_slug


def selected_images(item: ImportItem):
    return selected_active_images(item)


def cover_image(item: ImportItem):
    images = selected_images(item)
    return next((image for image in images if image.is_cover), images[0] if images else None)


def product_images_require_local_storage() -> bool:
    required = {column.name for column in ProductImage.__table__.columns if not column.nullable and column.default is None and column.server_default is None and not column.primary_key}
    return {"filename", "storage_path", "mime_type", "size_bytes", "width", "height"}.issubset(required)


def evaluate_publication_readiness(db: Session, item: ImportItem) -> dict:
    blockers: list[str] = []
    warnings: list[str] = []
    if item.status not in {"reviewed", "approved", "publish_failed", "published"}:
        blockers.append("not_reviewed")
    if item.status == "duplicate":
        blockers.append("duplicate_item")
    if item.status == "invalid":
        blockers.append("invalid_item")
    if item.published_product_id:
        blockers.append("already_published")
    if not (item.suggested_name or "").strip():
        blockers.append("missing_name")
    if not item.brand_id or not db.get(Brand, item.brand_id):
        blockers.append("missing_brand")
    if not item.suggested_category_id or not db.get(Category, item.suggested_category_id):
        blockers.append("missing_category")
    images = selected_images(item)
    if not images:
        blockers.append("missing_images")
    if not cover_image(item):
        blockers.append("missing_cover")
    if product_images_require_local_storage() and images:
        for image in images:
            if image.ingestion_status == "failed":
                blockers.append("image_ingestion_failed")
            elif image.ingestion_status != "stored":
                blockers.append("image_ingestion_required")
            elif not image.local_storage_path or not image.local_public_url or not image.local_mime_type or not image.local_size_bytes or not image.local_width or not image.local_height:
                blockers.append("image_ingestion_required")
            elif not stored_file_matches(image):
                blockers.append("ingested_file_missing")
    if not item.suggested_model:
        warnings.append("missing_model")
    if not item.suggested_color:
        warnings.append("missing_color")
    if len(images) == 1:
        warnings.append("single_image")
    if images:
        warnings.append("external_images")
    if item.overall_confidence is not None and Decimal(item.overall_confidence) < Decimal("0.70"):
        warnings.append("low_confidence")
    duplicate = find_possible_duplicate_product(db, item)
    if duplicate:
        blockers.append("duplicate_product")
    return {"ready": not blockers, "blockers": list(dict.fromkeys(blockers)), "warnings": list(dict.fromkeys(warnings))}


def find_possible_duplicate_product(db: Session, item: ImportItem) -> Product | None:
    if not item.suggested_name:
        return None
    normalized_name = item.suggested_name.strip().casefold()
    slug = unique_slug(db, Product, item.suggested_name)
    existing_slug = db.query(Product).filter(Product.slug == slug).first()
    if existing_slug:
        return existing_slug
    return (
        db.query(Product)
        .filter(Product.brand_id == item.brand_id, Product.category_id == item.suggested_category_id, func.lower(Product.name) == normalized_name)
        .first()
    )


def approve_import_item(db: Session, *, import_id: int, item_id: int, updated_at, user: AdminUser) -> ImportItem:
    item = get_item(db, import_id, item_id, editable=True)
    ensure_not_stale(item, updated_at)
    if item.status != "reviewed":
        raise ApiError(409, "IMPORT_ITEM_NOT_REVIEWED", "Somente item revisado pode ser aprovado para publicacao.")
    readiness = evaluate_publication_readiness(db, item)
    approval_blockers = [blocker for blocker in readiness["blockers"] if blocker not in {"external_images_require_ingestion", "image_ingestion_required", "duplicate_product"}]
    if approval_blockers:
        raise ApiError(422, "IMPORT_APPROVAL_BLOCKED", "Item ainda possui bloqueadores para aprovacao.", {"blockers": approval_blockers})
    if "duplicate_product" in readiness["blockers"]:
        raise ApiError(409, "IMPORT_DUPLICATE_PRODUCT", "Foi encontrado um possivel produto duplicado. Revise antes de publicar.")
    item.status = "approved"
    item.approved_by_id = user.id
    item.approved_at = utc_now()
    item.publish_error = None
    item.publish_metadata = {"readiness": readiness}
    refresh_import_record_counters(item.import_record)
    record_activity(db, user_id=user.id, action="approve_import_item", entity_type="import_item", entity_id=item.id, summary=f"Item aprovado para publicacao: {item.suggested_name}", metadata={"import_id": import_id, "item_id": item.id})
    db.flush()
    return item


def unapprove_import_item(db: Session, *, import_id: int, item_id: int, updated_at, user: AdminUser) -> ImportItem:
    item = get_item(db, import_id, item_id, editable=True)
    ensure_not_stale(item, updated_at)
    if item.status != "approved" or item.published_product_id:
        raise ApiError(409, "IMPORT_ITEM_NOT_UNAPPROVABLE", "Somente item aprovado e nao publicado pode ter aprovacao cancelada.")
    item.status = "reviewed"
    item.approved_by_id = None
    item.approved_at = None
    refresh_import_record_counters(item.import_record)
    record_activity(db, user_id=user.id, action="unapprove_import_item", entity_type="import_item", entity_id=item.id, summary=f"Aprovacao cancelada: {item.suggested_name}", metadata={"import_id": import_id, "item_id": item.id})
    db.flush()
    return item


def publish_import_item(db: Session, *, import_id: int, item_id: int, updated_at, user: AdminUser) -> dict:
    get_editable_record(db, import_id)
    query = db.query(ImportItem).options(selectinload(ImportItem.images), selectinload(ImportItem.import_record)).filter(ImportItem.id == item_id, ImportItem.import_record_id == import_id)
    if db.bind and db.bind.dialect.name != "sqlite":
        query = query.with_for_update()
    item = query.first()
    if not item:
        raise ApiError(404, "IMPORT_ITEM_NOT_FOUND", "Item de importacao nao encontrado.")
    ensure_not_stale(item, updated_at)
    if item.published_product_id and item.status == "published":
        product = db.get(Product, item.published_product_id)
        record_activity(db, user_id=user.id, action="publish_import_item_idempotent", entity_type="import_item", entity_id=item.id, summary="Item ja publicado anteriormente.", metadata={"import_id": import_id, "item_id": item.id, "product_id": item.published_product_id})
        return {"item": item, "product": product, "created": False, "message": "Este item ja foi publicado anteriormente. Nenhum produto duplicado foi criado."}
    if item.published_product_id:
        raise ApiError(409, "IMPORT_PUBLISH_INCONSISTENT", "Item possui produto associado com status inconsistente.")
    if item.status != "approved":
        raise ApiError(409, "IMPORT_ITEM_NOT_APPROVED", "Somente item aprovado pode ser publicado.")
    readiness = evaluate_publication_readiness(db, item)
    if readiness["blockers"]:
        raise ApiError(422, "IMPORT_PUBLISH_BLOCKED", "Item ainda possui bloqueadores para publicacao.", readiness)
    item.publish_attempts += 1
    item.status = "publishing"
    item.import_record.publishing_started_at = utc_now()
    record_activity(db, user_id=user.id, action="publish_import_item_started", entity_type="import_item", entity_id=item.id, summary=f"Publicacao iniciada: {item.suggested_name}", metadata={"import_id": import_id, "item_id": item.id})
    copied_paths: list[Path] = []
    try:
        product = create_draft_product_from_item(db, item, user.id)
        copied_paths = create_product_images_from_import(db, product, item)
        item.published_product_id = product.id
        item.published_by_id = user.id
        item.published_at = utc_now()
        item.status = "published"
        item.publish_error = None
        item.publish_metadata = {"readiness": readiness, "product_status": product.status, "product_visibility": product.visibility}
        item.import_record.publishing_finished_at = utc_now()
        refresh_import_record_counters(item.import_record)
        record_activity(db, user_id=user.id, action="publish_import_item_finished", entity_type="product", entity_id=product.id, summary=f"Produto criado em rascunho: {product.name}", metadata={"import_id": import_id, "item_id": item.id, "product_id": product.id})
        db.flush()
        return {"item": item, "product": product, "created": True, "message": "Produto criado com sucesso em modo rascunho."}
    except ApiError as exc:
        for path in copied_paths:
            path.unlink(missing_ok=True)
        item.status = "publish_failed"
        item.publish_error = exc.message[:500]
        item.publish_metadata = {"error_code": exc.code}
        item.import_record.publishing_finished_at = utc_now()
        refresh_import_record_counters(item.import_record)
        record_activity(db, user_id=user.id, action="publish_import_item_failed", entity_type="import_item", entity_id=item.id, summary="Publicacao falhou sem produto parcial mantido.", metadata={"import_id": import_id, "item_id": item.id, "code": exc.code})
        raise
    except SQLAlchemyError as exc:
        for path in copied_paths:
            path.unlink(missing_ok=True)
        raise ApiError(500, "IMPORT_PUBLISH_FAILED", "A publicacao falhou e foi revertida.") from exc
    except Exception:
        for path in copied_paths:
            path.unlink(missing_ok=True)
        raise


def create_draft_product_from_item(db: Session, item: ImportItem, user_id: int | None) -> Product:
    if find_possible_duplicate_product(db, item):
        raise ApiError(409, "IMPORT_DUPLICATE_PRODUCT", "Foi encontrado um possivel produto duplicado. Revise antes de publicar.")
    product = Product(
        public_id=__import__("uuid").uuid4().hex,
        name=item.suggested_name.strip(),
        slug=unique_slug(db, Product, item.suggested_name.strip()),
        brand_id=item.brand_id,
        category_id=item.suggested_category_id,
        short_description=None,
        description=None,
        price=Decimal("0.00"),
        track_inventory=False,
        stock_quantity=0,
        minimum_stock=0,
        allow_backorder=False,
        availability="unavailable",
        ready_to_ship=False,
        status="draft",
        visibility="hidden",
        main_image_alt=cover_image(item).alt_text if cover_image(item) else None,
        created_by_id=user_id,
        updated_by_id=user_id,
    )
    db.add(product)
    db.flush()
    return product


def create_product_images_from_import(db: Session, product: Product, item: ImportItem) -> list[Path]:
    if product_images_require_local_storage():
        copied_paths: list[Path] = []
        try:
            product_dir = product_storage_root(product.public_id)
            for position, image in enumerate(selected_images(item)):
                if image.ingestion_status != "stored" or not stored_file_matches(image):
                    raise ApiError(422, "IMPORT_IMAGE_INGESTION_REQUIRED", "Todas as imagens selecionadas precisam estar ingeridas antes da publicacao.")
                source_path = image_path_from_storage_path(image.local_storage_path)
                filename = image.local_filename or source_path.name
                target_path = ensure_child_path(product_dir, product_dir / filename)
                if target_path.exists() and image.content_sha256:
                    filename = f"{image.content_sha256}-{position}.{target_path.suffix.lstrip('.')}"
                    target_path = ensure_child_path(product_dir, product_dir / filename)
                shutil.copy2(source_path, target_path)
                copied_paths.append(target_path)
                record = ProductImage(
                    product_id=product.id,
                    filename=filename,
                    storage_path=str(target_path),
                    public_url=f"/uploads/products/{product.public_id}/{filename}",
                    mime_type=image.local_mime_type,
                    size_bytes=image.local_size_bytes or target_path.stat().st_size,
                    width=image.local_width or image.width or 0,
                    height=image.local_height or image.height or 0,
                    alt_text=image.alt_text,
                    is_primary=image.is_cover,
                    position=position,
                )
                db.add(record)
            db.flush()
        except Exception:
            for path in copied_paths:
                path.unlink(missing_ok=True)
            raise
        return copied_paths
    for position, image in enumerate(selected_images(item)):
        record = ProductImage(
            product_id=product.id,
            filename=None,
            storage_path=None,
            public_url=image.source_url,
            mime_type=None,
            size_bytes=0,
            width=image.width or 0,
            height=image.height or 0,
            alt_text=image.alt_text,
            is_primary=image.is_cover,
            position=position,
        )
        db.add(record)
    db.flush()
    return []
