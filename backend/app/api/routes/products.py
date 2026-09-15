import logging
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import current_user, require_csrf, require_roles
from app.exceptions import ApiError
from app.models import AdminUser, ProductVariant
from app.schemas.product import ProductCreate, ProductPatch, ProductRead, ProductUpdate, VariantCreate, VariantRead
from app.services.activities import record_activity
from app.services import products as service
from app.services.upload_storage import remove_upload_storage_file
from app.utils.client_ip import get_client_ip

router = APIRouter(dependencies=[Depends(current_user)])
logger = logging.getLogger(__name__)
public_catalog_lock = threading.Lock()


def public_products_path() -> Path:
    configured = settings.public_products_file
    if configured:
        return configured
    root = Path(__file__).resolve().parents[4]
    return root / "frontend" / "data" / "products.json"


def regenerate_public_catalog(db: Session) -> dict:
    db.flush()
    with public_catalog_lock:
        return service.export_public_products(db, public_products_path())


def restore_public_catalog(path: Path, existed: bool, content: bytes | None) -> None:
    if existed and content is not None:
        service.write_bytes_atomically(path, content)
    elif not existed and path.exists():
        path.unlink()


def commit_with_public_catalog(db: Session, *, operation: str = "public_catalog", product_id: int | None = None) -> dict:
    path = public_products_path()
    stage = None
    try:
        with public_catalog_lock:
            db.flush()
            stage = service.stage_public_catalog(db, path)
            db.commit()
            try:
                return service.publish_public_catalog_stage(stage)
            except Exception as exc:
                logger.exception("public_catalog_publish_failed", extra={"path": str(path), "operation": operation, "product_id": product_id, "error": str(exc)})
                raise ApiError(
                    503,
                    "PUBLIC_CATALOG_PUBLISH_FAILED",
                    "Alteracao salva, mas nao foi possivel atualizar o catalogo publico. Use a exportacao manual para reparar.",
                    {"path": str(path), "operation": operation, "product_id": product_id, "recoverable": True, "db_committed": True},
                ) from exc
    except ApiError:
        if stage:
            service.cleanup_public_catalog_stage(stage)
        raise
    except Exception:
        db.rollback()
        service.cleanup_public_catalog_stage(stage)
        raise


def public_catalog_was_affected(was_public: bool, product) -> bool:
    return was_public or service.is_public_product(product)


def commit_public_catalog_if_product_public(db: Session, product, relationships: tuple[str, ...] = (), *, operation: str = "public_product_change") -> dict | None:
    if not service.is_public_product(product):
        return None
    db.flush()
    for relationship in relationships:
        db.expire(product, [relationship])
    return commit_with_public_catalog(db, operation=operation, product_id=getattr(product, "id", None))


@router.get("")
def list_products(request: Request, db: Session = Depends(get_db)):
    return service.list_products(db, dict(request.query_params))


@router.post("/export", dependencies=[Depends(require_csrf)])
def export_products(db: Session = Depends(get_db), user: AdminUser = Depends(require_roles("owner", "admin"))):
    data = regenerate_public_catalog(db)
    record_activity(db, user_id=user.id, action="export", entity_type="product", summary="Produtos publicados exportados.")
    return data


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, db: Session = Depends(get_db)):
    return service.get_product(db, product_id)


@router.get("/{product_id}/publication-readiness")
def get_publication_readiness(product_id: int, db: Session = Depends(get_db)):
    product = service.get_product(db, product_id)
    return service.evaluate_publication_readiness(db, product)


@router.post("", response_model=ProductRead, status_code=201, dependencies=[Depends(require_csrf)])
def create_product(payload: ProductCreate, request: Request, db: Session = Depends(get_db), user: AdminUser = Depends(current_user)):
    product = service.create_product(db, payload, user.id)
    record_activity(db, user_id=user.id, action="create", entity_type="product", entity_id=product.id, summary=f"Produto criado: {product.name}", ip_address=get_client_ip(request))
    if service.is_public_product(product):
        commit_with_public_catalog(db, operation="create_product", product_id=product.id)
    return product


@router.put("/{product_id}", response_model=ProductRead, dependencies=[Depends(require_csrf)])
def update_product(product_id: int, payload: ProductUpdate, request: Request, db: Session = Depends(get_db), user: AdminUser = Depends(current_user)):
    was_public = service.is_public_product(service.get_product(db, product_id))
    product = service.update_product(db, product_id, payload, user.id)
    record_activity(db, user_id=user.id, action="update", entity_type="product", entity_id=product.id, summary=f"Produto editado: {product.name}", ip_address=get_client_ip(request))
    if public_catalog_was_affected(was_public, product):
        commit_with_public_catalog(db, operation="update_product", product_id=product.id)
    return product


@router.patch("/{product_id}", response_model=ProductRead, dependencies=[Depends(require_csrf)])
def patch_product(product_id: int, payload: ProductPatch, db: Session = Depends(get_db), user: AdminUser = Depends(current_user)):
    was_public = service.is_public_product(service.get_product(db, product_id))
    product = service.patch_product(db, product_id, payload, user.id)
    if public_catalog_was_affected(was_public, product):
        commit_with_public_catalog(db, operation="patch_product", product_id=product.id)
    return product


@router.delete("/{product_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_product(product_id: int, db: Session = Depends(get_db), user: AdminUser = Depends(require_roles("owner", "admin"))):
    product = service.get_product(db, product_id)
    was_public = service.is_public_product(product)
    storage_paths = [image.storage_path for image in product.images or [] if image.storage_path]
    record_activity(db, user_id=user.id, action="delete", entity_type="product", entity_id=product_id, summary="Produto excluido.")
    db.delete(product)
    if was_public:
        commit_with_public_catalog(db, operation="delete_product", product_id=product_id)
    else:
        db.commit()
    for storage_path in storage_paths:
        remove_upload_storage_file(storage_path, context={"operation": "delete_product", "product_id": product_id})


@router.post("/{product_id}/publish", response_model=ProductRead, dependencies=[Depends(require_csrf)])
def publish_product(product_id: int, db: Session = Depends(get_db), user: AdminUser = Depends(current_user)):
    product = service.publish_product(db, product_id)
    record_activity(db, user_id=user.id, action="publish", entity_type="product", entity_id=product.id, summary=f"Produto publicado: {product.name}")
    commit_with_public_catalog(db, operation="publish_product", product_id=product.id)
    return product


@router.post("/{product_id}/unpublish", response_model=ProductRead, dependencies=[Depends(require_csrf)])
def unpublish_product(product_id: int, db: Session = Depends(get_db), user: AdminUser = Depends(current_user)):
    product = service.unpublish_product(db, product_id)
    record_activity(db, user_id=user.id, action="unpublish", entity_type="product", entity_id=product.id, summary=f"Produto despublicado: {product.name}")
    commit_with_public_catalog(db, operation="unpublish_product", product_id=product.id)
    return product


@router.post("/{product_id}/duplicate", response_model=ProductRead, dependencies=[Depends(require_csrf)])
def duplicate_product(product_id: int, db: Session = Depends(get_db), user: AdminUser = Depends(current_user)):
    return service.duplicate_product(db, product_id, user.id)


@router.get("/{product_id}/variants", response_model=list[VariantRead])
def list_variants(product_id: int, db: Session = Depends(get_db)):
    service.get_product(db, product_id)
    return db.query(ProductVariant).filter(ProductVariant.product_id == product_id).order_by(ProductVariant.position.asc()).all()


@router.post("/{product_id}/variants", response_model=VariantRead, status_code=201, dependencies=[Depends(require_csrf)])
def create_variant(product_id: int, payload: VariantCreate, db: Session = Depends(get_db)):
    product = service.get_product(db, product_id)
    variant = ProductVariant(product_id=product_id, **payload.model_dump())
    db.add(variant)
    db.flush()
    commit_public_catalog_if_product_public(db, product, ("variants",), operation="create_variant")
    return variant


@router.put("/{product_id}/variants/{variant_id}", response_model=VariantRead, dependencies=[Depends(require_csrf)])
def update_variant(product_id: int, variant_id: int, payload: VariantCreate, db: Session = Depends(get_db)):
    product = service.get_product(db, product_id)
    variant = db.get(ProductVariant, variant_id)
    if not variant or variant.product_id != product_id:
        from app.exceptions import ApiError
        raise ApiError(404, "VARIANT_NOT_FOUND", "Variação não encontrada.")
    for key, value in payload.model_dump().items():
        setattr(variant, key, value)
    commit_public_catalog_if_product_public(db, product, ("variants",), operation="update_variant")
    return variant


@router.delete("/{product_id}/variants/{variant_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_variant(product_id: int, variant_id: int, db: Session = Depends(get_db)):
    product = service.get_product(db, product_id)
    variant = db.get(ProductVariant, variant_id)
    if variant and variant.product_id == product_id:
        db.delete(variant)
        commit_public_catalog_if_product_public(db, product, ("variants",), operation="delete_variant")
