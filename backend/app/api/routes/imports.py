from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.dependencies import current_user, require_csrf, require_roles
from app.exceptions import ApiError
from app.models import AdminUser, ImportItem, ImportRecord
from app.schemas.imports import (
    ImportImageRead,
    ImportImageIngestionReadiness,
    ImportImageIngestionRequest,
    ImportSelectedImagesIngestionRequest,
    ImportImageIngestionResult,
    ImportSelectedImagesIngestionResult,
    ImportImageReorder,
    ImportImageUpdate,
    ImportItemApprovalRequest,
    ImportItemDetail,
    ImportItemListResponse,
    ImportItemPublicationReadiness,
    ImportItemPublicationResult,
    ImportItemPublishRequest,
    ImportItemUpdate,
    ImportListResponse,
    ImportPreviewCreate,
    ImportPreviewResponse,
    ImportRecordDetail,
    ImportRecordRead,
)
from app.services import imports as service
from app.services import import_review
from app.services import import_publish
from app.services import import_image_ingestion
from app.services.activities import record_activity
from app.utils.pagination import pagination_meta

router = APIRouter(dependencies=[Depends(current_user)])


def get_record(db: Session, import_id: int) -> ImportRecord:
    item = (
        db.query(ImportRecord)
        .options(selectinload(ImportRecord.brand), selectinload(ImportRecord.items).selectinload(ImportItem.images))
        .filter(ImportRecord.id == import_id)
        .first()
    )
    if not item:
        raise ApiError(404, "IMPORT_NOT_FOUND", "Importacao nao encontrada.")
    return item


@router.post("/preview", response_model=ImportPreviewResponse, status_code=201, dependencies=[Depends(require_csrf)])
def create_preview(payload: ImportPreviewCreate, db: Session = Depends(get_db), user: AdminUser = Depends(require_roles("owner", "admin"))):
    record = service.preview_import_folder(db, brand_id=payload.brand_id, brand_name=payload.brand, source_url=str(payload.source_url), user_id=user.id)
    record_activity(db, user_id=user.id, action="preview", entity_type="import", entity_id=record.id, summary=f"Pre-visualizacao criada: {record.folder_name}")
    return {
        "id": record.id,
        "status": record.status,
        "brand": record.brand,
        "source_url": record.normalized_source_url or record.source_url,
        "message": "Pre-visualizacao concluida. Revise os itens encontrados antes da proxima etapa.",
    }


@router.get("", response_model=ImportListResponse)
def list_imports(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(ImportRecord).options(selectinload(ImportRecord.brand)).order_by(ImportRecord.created_at.desc())
    count_query = db.query(ImportRecord)
    if status:
        query = query.filter(ImportRecord.status == status)
        count_query = count_query.filter(ImportRecord.status == status)
    total = count_query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": items, "pagination": pagination_meta(page, page_size, total)}


@router.get("/{import_id}/items/{item_id}", response_model=ImportItemDetail)
def get_item(import_id: int, item_id: int, db: Session = Depends(get_db)):
    item = import_review.get_item(db, import_id, item_id)
    item.publication_readiness = import_publish.evaluate_publication_readiness(db, item)
    return item


@router.patch("/{import_id}/items/{item_id}", response_model=ImportItemDetail)
def update_item(import_id: int, item_id: int, payload: ImportItemUpdate, db: Session = Depends(get_db), user: AdminUser = Depends(require_roles("owner", "admin")), csrf: None = Depends(require_csrf)):
    return import_review.update_import_item(db, import_id=import_id, item_id=item_id, payload=payload, user=user)


@router.get("/{import_id}/items/{item_id}/images", response_model=list[ImportImageRead])
def list_item_images(import_id: int, item_id: int, db: Session = Depends(get_db)):
    item = import_review.get_item(db, import_id, item_id)
    return item.images


@router.get("/{import_id}/items/{item_id}/images/{image_id}/ingestion-readiness", response_model=ImportImageIngestionReadiness)
def get_image_ingestion_readiness(import_id: int, item_id: int, image_id: int, db: Session = Depends(get_db)):
    image = import_review.get_image(import_review.get_item(db, import_id, item_id), image_id)
    return import_image_ingestion.evaluate_ingestion_readiness(image)


@router.patch("/{import_id}/items/{item_id}/images/{image_id}", response_model=ImportImageRead)
def update_image(import_id: int, item_id: int, image_id: int, payload: ImportImageUpdate, db: Session = Depends(get_db), user: AdminUser = Depends(require_roles("owner", "admin")), csrf: None = Depends(require_csrf)):
    return import_review.update_import_image(db, import_id=import_id, item_id=item_id, image_id=image_id, payload=payload, user=user)


@router.post("/{import_id}/items/{item_id}/images/reorder", response_model=ImportItemDetail)
def reorder_images(import_id: int, item_id: int, payload: ImportImageReorder, db: Session = Depends(get_db), user: AdminUser = Depends(require_roles("owner", "admin")), csrf: None = Depends(require_csrf)):
    return import_review.reorder_import_images(db, import_id=import_id, item_id=item_id, image_ids=payload.image_ids, updated_at=payload.updated_at, user=user)


@router.post("/{import_id}/items/{item_id}/images/{image_id}/ingest", response_model=ImportImageIngestionResult)
def ingest_image(import_id: int, item_id: int, image_id: int, payload: ImportImageIngestionRequest, db: Session = Depends(get_db), user: AdminUser = Depends(require_roles("owner", "admin")), csrf: None = Depends(require_csrf)):
    return import_image_ingestion.ingest_import_image(db, import_id=import_id, item_id=item_id, image_id=image_id, updated_at=payload.updated_at, user=user)


@router.post("/{import_id}/items/{item_id}/images/ingest-selected", response_model=ImportSelectedImagesIngestionResult)
def ingest_selected_images(import_id: int, item_id: int, payload: ImportSelectedImagesIngestionRequest, db: Session = Depends(get_db), user: AdminUser = Depends(require_roles("owner", "admin")), csrf: None = Depends(require_csrf)):
    images = import_image_ingestion.ingest_selected_images(db, import_id=import_id, item_id=item_id, image_ids=payload.image_ids, updated_at=payload.updated_at, user=user)
    return {"images": images, "message": "Imagens selecionadas processadas. Nenhum produto foi publicado."}


@router.get("/{import_id}/items/{item_id}/publication-readiness", response_model=ImportItemPublicationReadiness)
def get_publication_readiness(import_id: int, item_id: int, db: Session = Depends(get_db)):
    item = import_review.get_item(db, import_id, item_id)
    return import_publish.evaluate_publication_readiness(db, item)


@router.post("/{import_id}/items/{item_id}/approve", response_model=ImportItemDetail)
def approve_item(import_id: int, item_id: int, payload: ImportItemApprovalRequest, db: Session = Depends(get_db), user: AdminUser = Depends(require_roles("owner", "admin")), csrf: None = Depends(require_csrf)):
    item = import_publish.approve_import_item(db, import_id=import_id, item_id=item_id, updated_at=payload.updated_at, user=user)
    item.publication_readiness = import_publish.evaluate_publication_readiness(db, item)
    return item


@router.post("/{import_id}/items/{item_id}/unapprove", response_model=ImportItemDetail)
def unapprove_item(import_id: int, item_id: int, payload: ImportItemApprovalRequest, db: Session = Depends(get_db), user: AdminUser = Depends(require_roles("owner", "admin")), csrf: None = Depends(require_csrf)):
    item = import_publish.unapprove_import_item(db, import_id=import_id, item_id=item_id, updated_at=payload.updated_at, user=user)
    item.publication_readiness = import_publish.evaluate_publication_readiness(db, item)
    return item


@router.post("/{import_id}/items/{item_id}/publish", response_model=ImportItemPublicationResult)
def publish_item(import_id: int, item_id: int, payload: ImportItemPublishRequest, db: Session = Depends(get_db), user: AdminUser = Depends(require_roles("owner", "admin")), csrf: None = Depends(require_csrf)):
    result = import_publish.publish_import_item(db, import_id=import_id, item_id=item_id, updated_at=payload.updated_at, user=user)
    item = result["item"]
    item.publication_readiness = import_publish.evaluate_publication_readiness(db, item)
    product = result.get("product")
    return {"item": item, "product_id": product.id if product else item.published_product_id, "created": result["created"], "message": result["message"]}


@router.get("/{import_id}", response_model=ImportRecordDetail)
def get_import(import_id: int, db: Session = Depends(get_db)):
    return get_record(db, import_id)


@router.get("/{import_id}/items", response_model=ImportItemListResponse)
def list_items(
    import_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    suggested_category: str | None = None,
    suggested_model: str | None = None,
    suggested_color: str | None = None,
    min_confidence: float | None = Query(None, ge=0, le=1),
    needs_review: bool | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
):
    get_record(db, import_id)
    query = db.query(ImportItem).filter(ImportItem.import_record_id == import_id).order_by(ImportItem.page_number.asc(), ImportItem.position.asc(), ImportItem.id.asc())
    if status:
        query = query.filter(ImportItem.status == status)
    if needs_review is True:
        query = query.filter(ImportItem.status == "needs_review")
    elif needs_review is False:
        query = query.filter(ImportItem.status != "needs_review")
    if suggested_category:
        query = query.filter(ImportItem.suggested_category == suggested_category)
    if suggested_model:
        query = query.filter(ImportItem.suggested_model.ilike(f"%{suggested_model}%"))
    if suggested_color:
        query = query.filter(ImportItem.suggested_color_normalized == service.normalize_product_text(suggested_color))
    if min_confidence is not None:
        query = query.filter(ImportItem.overall_confidence >= min_confidence)
    if search:
        term = f"%{search}%"
        query = query.filter(or_(ImportItem.source_title.ilike(term), ImportItem.suggested_name.ilike(term), ImportItem.suggested_model.ilike(term), ImportItem.suggested_color.ilike(term)))
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": items, "pagination": pagination_meta(page, page_size, total)}


@router.post("/{import_id}/cancel", response_model=ImportRecordRead, dependencies=[Depends(require_csrf)])
def cancel_import(import_id: int, db: Session = Depends(get_db), user: AdminUser = Depends(require_roles("owner", "admin"))):
    record = get_record(db, import_id)
    if record.status not in {"draft", "scanning"}:
        raise ApiError(409, "IMPORT_NOT_CANCELLABLE", "Esta importacao nao pode ser cancelada neste estado.")
    record.status = "cancelled"
    record_activity(db, user_id=user.id, action="cancel", entity_type="import", entity_id=record.id, summary=f"Importacao cancelada: {record.folder_name}")
    return record


@router.delete("/{import_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_import(import_id: int, db: Session = Depends(get_db), user: AdminUser = Depends(require_roles("owner", "admin"))):
    record = get_record(db, import_id)
    if record.items_approved or record.items_rejected or record.published_product_id:
        raise ApiError(409, "IMPORT_ALREADY_APPLIED", "Importacao com aplicacao futura nao pode ser excluida.")
    removed_files = import_image_ingestion.remove_import_image_files(import_id)
    db.delete(record)
    record_activity(db, user_id=user.id, action="delete", entity_type="import", entity_id=import_id, summary="Importacao de pre-visualizacao excluida.", metadata={"removed_files": len(removed_files)})
