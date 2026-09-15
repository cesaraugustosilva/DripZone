import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.exceptions import ApiError
from app.models import Brand, Category, Collection, ImportItem, Product, ProductVariant, SneakerModel, utc_now
from app.schemas.product import ProductCreate, ProductPatch, ProductUpdate
from app.utils.pagination import pagination_meta
from app.utils.slug import unique_slug


SORT_COLUMNS = {
    "name": Product.name,
    "price": Product.price,
    "stock_quantity": Product.stock_quantity,
    "created_at": Product.created_at,
    "updated_at": Product.updated_at,
    "published_at": Product.published_at,
}

UNKNOWN_BRAND_SLUGS = {"unknown", "desconhecida", "sem-marca", "sem-marca-definida"}
UNKNOWN_CATEGORY_SLUGS = {"desconhecidos", "unknown", "sem-categoria"}


@dataclass
class PublicCatalogStage:
    data: dict
    output_path: Path
    temp_path: Path


def product_query() -> Select:
    return select(Product).options(
        selectinload(Product.brand),
        selectinload(Product.category),
        selectinload(Product.sneaker_model),
        selectinload(Product.variants),
        selectinload(Product.images),
        selectinload(Product.collections),
    )


def is_public_product(product: Product) -> bool:
    return product.status == "published"


def sync_publication_state(product: Product) -> None:
    if product.status == "published":
        product.visibility = "public"
        if not product.published_at:
            product.published_at = utc_now()
    else:
        product.visibility = "hidden"


def readiness_issue(code: str, field: str | None, message: str) -> dict:
    return {"code": code, "field": field, "message": message}


def dedupe_issues(issues: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for issue in issues:
        key = issue["code"]
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result


def latest_import_metadata(db: Session, product: Product) -> dict | None:
    item = (
        db.query(ImportItem)
        .filter(ImportItem.published_product_id == product.id)
        .order_by(ImportItem.updated_at.desc(), ImportItem.id.desc())
        .first()
    )
    return item.raw_metadata if item else None


def valid_primary_image(product: Product) -> bool:
    primary = next((image for image in product.images if image.is_primary), None)
    if not primary or not is_public_image_url(primary.public_url):
        return False
    if primary.public_url.startswith("/uploads/") and primary.storage_path:
        return Path(primary.storage_path).exists()
    return True


def evaluate_publication_readiness(db: Session, product: Product) -> dict:
    blockers: list[dict] = []
    warnings: list[dict] = []
    if not (product.name or "").strip():
        blockers.append(readiness_issue("PRODUCT_NAME_REQUIRED", "name", "Informe o nome do produto."))
    try:
        price = Decimal(str(product.price)) if product.price is not None else None
    except Exception:
        price = None
    if price is None or price <= 0:
        blockers.append(readiness_issue("PRICE_NOT_DEFINED", "price", "Defina um preço comercial maior que zero."))
    brand_slug = (product.brand.slug if product.brand else "").strip().lower()
    brand_name = (product.brand.name if product.brand else "").strip().lower()
    if not product.brand or brand_slug in UNKNOWN_BRAND_SLUGS or brand_name in {"unknown", "desconhecida", "sem marca"}:
        blockers.append(readiness_issue("BRAND_REQUIRED", "brand_id", "Selecione uma marca válida."))
    category_slug = (product.category.slug if product.category else "").strip().lower()
    if not product.category or category_slug in UNKNOWN_CATEGORY_SLUGS:
        blockers.append(readiness_issue("CATEGORY_REQUIRED", "category_id", "Selecione uma categoria válida."))
    if not product.images or not valid_primary_image(product):
        blockers.append(readiness_issue("PRIMARY_IMAGE_REQUIRED", "images", "Selecione uma imagem principal pública válida."))

    metadata = latest_import_metadata(db, product) or {}
    review = metadata.get("review") or {}
    import_data = metadata.get("import") or {}
    if metadata.get("unknown_category") or review.get("needs_category_review"):
        blockers.append(readiness_issue("CATEGORY_REVIEW_REQUIRED", "category_id", "Resolva a revisão de categoria."))
    if review.get("needs_name_review"):
        blockers.append(readiness_issue("NAME_REVIEW_REQUIRED", "name", "Resolva a revisão do nome comercial."))
    if review.get("brand_conflict"):
        blockers.append(readiness_issue("BRAND_CONFLICT", "brand_id", "Resolva o conflito de marca antes de publicar."))
    if import_data.get("status") in {"partial", "failed"}:
        blockers.append(readiness_issue("IMPORT_PARTIAL", None, "Resolva a importação parcial antes de publicar."))
    if import_data.get("errors") or int(import_data.get("images_failed") or 0) > 0:
        blockers.append(readiness_issue("IMPORT_ERROR", None, "Resolva os erros técnicos da importação antes de publicar."))
    if review.get("status") == "review_required" or metadata.get("review_required"):
        blockers.append(readiness_issue("REVIEW_REQUIRED", None, "Revise o produto antes de publicar."))

    if not (product.description or "").strip():
        warnings.append(readiness_issue("DESCRIPTION_EMPTY", "description", "Descrição vazia."))
    if len(product.images or []) == 1:
        warnings.append(readiness_issue("SINGLE_IMAGE", "images", "Produto possui apenas uma imagem."))
    if not product.variants:
        warnings.append(readiness_issue("SIZES_EMPTY", "sizes", "Tamanhos não cadastrados."))
    if not product.seo_title or not product.seo_description:
        warnings.append(readiness_issue("SEO_EMPTY", "seo", "SEO incompleto."))

    blockers = dedupe_issues(blockers)
    warnings = dedupe_issues(warnings)
    return {"eligible": not blockers, "blockers": blockers, "warnings": warnings}


def is_purchasable_product(product: Product) -> bool:
    price = public_product_price(product.price)
    return price is not None and price > 0


def public_availability(product: Product) -> str:
    return "available" if is_purchasable_product(product) else "coming_soon"


def evaluate_showcase_readiness(db: Session, product: Product) -> dict:
    blockers: list[dict] = []
    warnings: list[dict] = []
    if not (product.name or "").strip():
        blockers.append(readiness_issue("PRODUCT_NAME_REQUIRED", "name", "Informe o nome do produto."))
    brand_slug = (product.brand.slug if product.brand else "").strip().lower()
    brand_name = (product.brand.name if product.brand else "").strip().lower()
    if not product.brand or brand_slug in UNKNOWN_BRAND_SLUGS or brand_name in {"unknown", "desconhecida", "sem marca"}:
        blockers.append(readiness_issue("BRAND_REQUIRED", "brand_id", "Selecione uma marca valida."))
    category_slug = (product.category.slug if product.category else "").strip().lower()
    if not product.category or category_slug in UNKNOWN_CATEGORY_SLUGS:
        blockers.append(readiness_issue("CATEGORY_REQUIRED", "category_id", "Selecione uma categoria valida."))
    if not product.images or not valid_primary_image(product):
        blockers.append(readiness_issue("PRIMARY_IMAGE_REQUIRED", "images", "Selecione uma imagem principal publica valida."))

    metadata = latest_import_metadata(db, product) or {}
    review = metadata.get("review") or {}
    import_data = metadata.get("import") or {}
    if metadata.get("unknown_category") and category_slug in UNKNOWN_CATEGORY_SLUGS:
        blockers.append(readiness_issue("CATEGORY_REVIEW_REQUIRED", "category_id", "Resolva a categoria desconhecida."))
    if review.get("needs_category_review") and category_slug in UNKNOWN_CATEGORY_SLUGS:
        blockers.append(readiness_issue("CATEGORY_REVIEW_REQUIRED", "category_id", "Resolva a categoria desconhecida."))
    if review.get("brand_conflict"):
        blockers.append(readiness_issue("BRAND_CONFLICT", "brand_id", "Resolva o conflito de marca antes de publicar em vitrine."))
    if import_data.get("status") in {"partial", "failed"}:
        blockers.append(readiness_issue("IMPORT_PARTIAL", None, "Resolva a importacao parcial antes de publicar em vitrine."))
    if import_data.get("errors") or int(import_data.get("images_failed") or 0) > 0:
        blockers.append(readiness_issue("IMPORT_ERROR", None, "Resolva os erros tecnicos da importacao antes de publicar em vitrine."))

    try:
        price = Decimal(str(product.price)) if product.price is not None else None
    except Exception:
        price = None
    if price is None or price <= 0:
        warnings.append(readiness_issue("SHOWCASE_WITHOUT_PRICE", "price", "Produto sera publicado como vitrine, sem compra."))
    if review.get("needs_name_review"):
        warnings.append(readiness_issue("NAME_REVIEW_WARNING", "name", "Nome ainda pede revisao editorial."))
    if review.get("needs_category_review") and category_slug not in UNKNOWN_CATEGORY_SLUGS:
        warnings.append(readiness_issue("CATEGORY_REVIEW_WARNING", "category_id", "Categoria foi corrigida para vitrine emergencial."))
    if not (product.description or "").strip():
        warnings.append(readiness_issue("DESCRIPTION_EMPTY", "description", "Descricao vazia."))

    blockers = dedupe_issues(blockers)
    warnings = dedupe_issues(warnings)
    return {"eligible": not blockers, "blockers": blockers, "warnings": warnings}


def ensure_publication_ready(db: Session, product: Product) -> dict:
    readiness = evaluate_publication_readiness(db, product)
    if readiness["blockers"]:
        raise ApiError(
            422,
            "PRODUCT_NOT_READY_FOR_PUBLICATION",
            "O produto ainda não está pronto para publicação.",
            readiness,
        )
    return readiness


def get_product(db: Session, product_id: int) -> Product:
    product = db.execute(product_query().where(Product.id == product_id)).scalar_one_or_none()
    if not product:
        raise ApiError(404, "PRODUCT_NOT_FOUND", "Produto não encontrado.")
    return product


def list_products(db: Session, params: dict) -> dict:
    page = max(int(params.get("page", 1)), 1)
    page_size = min(max(int(params.get("page_size", 20)), 1), 100)
    stmt = product_query()
    count_stmt = select(func.count(Product.id))
    filters = []
    search = params.get("search")
    if search:
        term = f"%{search}%"
        filters.append(or_(Product.name.ilike(term), Product.slug.ilike(term), Product.sku.ilike(term)))
    for key in ("status", "availability"):
        if params.get(key):
            filters.append(getattr(Product, key) == params[key])
    for key in ("brand_id", "category_id"):
        if params.get(key):
            filters.append(getattr(Product, key) == int(params[key]))
    for key in ("is_featured", "is_new", "is_best_seller"):
        if params.get(key) is not None:
            filters.append(getattr(Product, key) == (str(params[key]).lower() == "true"))
    if params.get("stock_state") == "low":
        filters.append(Product.stock_quantity <= Product.minimum_stock)
    elif params.get("stock_state") == "out":
        filters.append(Product.stock_quantity <= 0)
    for item in filters:
        stmt = stmt.where(item)
        count_stmt = count_stmt.where(item)
    sort = params.get("sort", "updated_at")
    if sort not in SORT_COLUMNS:
        raise ApiError(400, "INVALID_SORT", "Ordenação inválida.")
    column = SORT_COLUMNS[sort]
    stmt = stmt.order_by(column.asc() if params.get("order") == "asc" else column.desc())
    total = db.execute(count_stmt).scalar_one()
    items = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return {"items": items, "pagination": pagination_meta(page, page_size, total)}


def validate_refs(db: Session, data, product: Product | None = None) -> None:
    fields_set = getattr(data, "model_fields_set", set())
    brand_id = getattr(data, "brand_id", None)
    category_id = getattr(data, "category_id", None)
    sneaker_model_id = getattr(data, "sneaker_model_id", None)
    if "sneaker_model_id" not in fields_set and sneaker_model_id is None and brand_id is not None and product is not None:
        sneaker_model_id = product.sneaker_model_id

    if brand_id and not db.get(Brand, brand_id):
        raise ApiError(422, "BRAND_NOT_FOUND", "Marca informada não existe.")
    if category_id and not db.get(Category, category_id):
        raise ApiError(422, "CATEGORY_NOT_FOUND", "Categoria informada não existe.")
    if sneaker_model_id:
        sneaker_model = db.get(SneakerModel, sneaker_model_id)
        if not sneaker_model:
            raise ApiError(422, "SNEAKER_MODEL_NOT_FOUND", "Modelo de sneaker informado não existe.")
        effective_brand_id = brand_id if brand_id is not None else getattr(product, "brand_id", None)
        if sneaker_model.brand_id and effective_brand_id and sneaker_model.brand_id != effective_brand_id:
            raise ApiError(422, "SNEAKER_MODEL_BRAND_MISMATCH", "Modelo de sneaker não pertence à marca informada.")
    for collection_id in getattr(data, "collection_ids", []) or []:
        if not db.get(Collection, collection_id):
            raise ApiError(422, "COLLECTION_NOT_FOUND", "Coleção informada não existe.")


def ensure_unique(db: Session, *, slug: str, sku: str | None, current_id: int | None = None) -> None:
    slug_query = db.query(Product).filter(Product.slug == slug)
    if current_id:
        slug_query = slug_query.filter(Product.id != current_id)
    if slug_query.first():
        raise ApiError(409, "PRODUCT_SLUG_CONFLICT", "Slug já está em uso.")
    if sku:
        sku_query = db.query(Product).filter(Product.sku == sku)
        if current_id:
            sku_query = sku_query.filter(Product.id != current_id)
        if sku_query.first():
            raise ApiError(409, "PRODUCT_SKU_CONFLICT", "SKU já está em uso.")


def apply_product_data(db: Session, product: Product, data) -> Product:
    validate_refs(db, data, product)
    payload = data.model_dump(exclude={"variants", "collection_ids"}, exclude_unset=False)
    slug = payload.get("slug") or unique_slug(db, Product, payload["name"], getattr(product, "id", None))
    ensure_unique(db, slug=slug, sku=payload.get("sku"), current_id=getattr(product, "id", None))
    for key, value in payload.items():
        setattr(product, key, value)
    product.slug = slug
    product.collections = [db.get(Collection, cid) for cid in data.collection_ids or []]
    return product


def create_product(db: Session, data: ProductCreate, user_id: int | None) -> Product:
    product = Product(public_id=uuid4().hex, created_by_id=user_id, updated_by_id=user_id)
    apply_product_data(db, product, data)
    product.variants = [ProductVariant(**variant.model_dump()) for variant in data.variants]
    sync_publication_state(product)
    db.add(product)
    db.flush()
    if product.status == "published":
        ensure_publication_ready(db, product)
    return product


def update_product(db: Session, product_id: int, data: ProductUpdate, user_id: int | None) -> Product:
    product = get_product(db, product_id)
    apply_product_data(db, product, data)
    product.updated_by_id = user_id
    variants = getattr(data, "variants", None)
    if variants is not None:
        product.variants = [ProductVariant(**variant.model_dump()) for variant in variants]
    sync_publication_state(product)
    if product.status == "published":
        ensure_publication_ready(db, product)
    return product


def patch_product(db: Session, product_id: int, data: ProductPatch, user_id: int | None) -> Product:
    product = get_product(db, product_id)
    validate_refs(db, data, product)
    payload = data.model_dump(exclude_unset=True)
    if "slug" in payload or "sku" in payload:
        ensure_unique(db, slug=payload.get("slug", product.slug), sku=payload.get("sku", product.sku), current_id=product.id)
    for key, value in payload.items():
        setattr(product, key, value)
    product.updated_by_id = user_id
    sync_publication_state(product)
    if product.status == "published":
        ensure_publication_ready(db, product)
    return product


def publish_product(db: Session, product_id: int) -> Product:
    product = get_product(db, product_id)
    ensure_publication_ready(db, product)
    product.status = "published"
    sync_publication_state(product)
    return product


def unpublish_product(db: Session, product_id: int) -> Product:
    product = get_product(db, product_id)
    product.status = "draft"
    sync_publication_state(product)
    return product


def duplicate_product(db: Session, product_id: int, user_id: int | None) -> Product:
    original = get_product(db, product_id)
    copy = Product(public_id=uuid4().hex, created_by_id=user_id, updated_by_id=user_id)
    for field in ["name", "short_description", "description", "brand_id", "category_id", "sneaker_model_id", "product_type", "audience", "price", "stock_quantity"]:
        setattr(copy, field, getattr(original, field))
    copy.slug = unique_slug(db, Product, f"{original.slug}-copia")
    copy.status = "draft"
    copy.visibility = "hidden"
    copy.availability = original.availability
    db.add(copy)
    db.flush()
    return copy


def public_product_price(value) -> float | None:
    if value is None:
        return None
    amount = Decimal(str(value))
    if amount <= 0:
        return None
    return float(amount)


def is_public_image_url(value: str | None) -> bool:
    if not value:
        return False
    return "\\" not in value and not value.lower().startswith("file:") and "://" not in value and ":" not in value


def ordered_public_image_urls(product: Product) -> list[str]:
    images = sorted(product.images, key=lambda image: (not image.is_primary, image.position, image.id or 0))
    urls = []
    for image in images:
        if is_public_image_url(image.public_url) and image.public_url not in urls:
            urls.append(image.public_url)
    return urls


def public_product_sizes(product: Product) -> list[str]:
    variants = sorted(product.variants, key=lambda variant: (variant.position, variant.id or 0))
    sizes = []
    for variant in variants:
        if variant.is_active and variant.size and variant.size not in sizes:
            sizes.append(variant.size)
    return sizes


def public_product_collection_ids(product: Product) -> list[str]:
    collections = sorted(product.collections, key=lambda collection: (collection.position, collection.id or 0))
    return [collection.slug for collection in collections if collection.slug]


def public_product_description(product: Product) -> str:
    description = (product.description or "").strip()
    if not description:
        return ""
    if "taobao.com" in description.lower() or "weidian.com" in description.lower() or description.lower().startswith(("http://", "https://")):
        return "Produto em vitrine temporária. Detalhes comerciais em revisão."
    return description


def public_timestamp(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def serialize_public_product(product: Product) -> dict:
    gallery = ordered_public_image_urls(product)
    collection_ids = public_product_collection_ids(product)
    price = public_product_price(product.price)
    purchasable = price is not None and price > 0
    return {
        "id": product.slug,
        "slug": product.slug,
        "name": product.name,
        "price": price,
        "purchasable": purchasable,
        "availability": "available" if purchasable else "coming_soon",
        "image": gallery[0] if gallery else None,
        "gallery": gallery,
        "category": product.category.name if product.category else "",
        "categoryId": product.category.slug if product.category else "",
        "brand": product.brand.name if product.brand else "",
        "brandId": product.brand.slug if product.brand else "",
        "model": product.sneaker_model.name if product.sneaker_model else "",
        "modelId": product.sneaker_model.slug if product.sneaker_model else "",
        "collectionId": collection_ids[0] if collection_ids else "",
        "collectionIds": collection_ids,
        "sizes": public_product_sizes(product),
        "description": public_product_description(product),
        "createdAt": public_timestamp(product.created_at),
        "badges": [],
    }


def public_catalog_json_bytes(data: dict) -> bytes:
    content = json.dumps(data, ensure_ascii=False, indent=2)
    json.loads(content)
    return content.encode("utf-8")


def build_public_catalog(db: Session) -> dict:
    items = db.execute(product_query().where(Product.status == "published").order_by(Product.slug.asc(), Product.id.asc())).scalars().all()
    updated_at = max((product.updated_at for product in items), default=None)
    return {"version": 1, "updatedAt": public_timestamp(updated_at) if updated_at else None, "products": [serialize_public_product(product) for product in items]}


def write_json_atomically(output_path: Path, data: dict) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = public_catalog_json_bytes(data)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=output_path.parent, prefix=f".{output_path.name}.", suffix=".tmp", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, output_path)
        tmp_path = None
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()


def stage_public_catalog(db: Session, output_path: Path) -> PublicCatalogStage:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = build_public_catalog(db)
    content = public_catalog_json_bytes(data)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=output_path.parent, prefix=f".{output_path.name}.", suffix=".stage", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
        return PublicCatalogStage(data=data, output_path=output_path, temp_path=tmp_path)
    except Exception:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()
        raise


def cleanup_public_catalog_stage(stage: PublicCatalogStage | None) -> None:
    if stage and stage.temp_path.exists():
        stage.temp_path.unlink()


def publish_public_catalog_stage(stage: PublicCatalogStage) -> dict:
    os.replace(stage.temp_path, stage.output_path)
    return stage.data


def write_bytes_atomically(output_path: Path, content: bytes) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=output_path.parent, prefix=f".{output_path.name}.", suffix=".tmp", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, output_path)
        tmp_path = None
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()


def export_public_products(db: Session, output_path: Path) -> dict:
    data = build_public_catalog(db)
    write_json_atomically(output_path, data)
    return data
