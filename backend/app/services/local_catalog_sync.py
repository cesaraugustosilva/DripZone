import hashlib
import json
import shutil
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Brand, Category, ImportImage, ImportItem, ImportRecord, Product, ProductImage, utc_now
from app.services.import_identity import find_existing_import_item as find_existing_identity_item
from app.services.import_identity import resolve_import_identity
from app.services.products import sync_publication_state
from app.services.upload_storage import ensure_canonical_upload_write_allowed, remove_upload_storage_file
from app.utils.slug import unique_slug


LOCAL_CATALOG_SOURCE = "local_catalog"
UNKNOWN_CATEGORY_SLUG = "desconhecidos"


@dataclass
class LocalCatalogSyncOptions:
    catalog_root: Path
    dry_run: bool = False
    limit: int | None = None
    product_id: str | None = None
    category: str | None = None
    verbose: bool = False


@dataclass
class LocalCatalogSyncResult:
    found: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    partial: int = 0
    failed: int = 0
    images_created: int = 0
    images_reused: int = 0
    images_failed: int = 0
    unknown_categories: int = 0
    review_required: int = 0
    errors: list[dict] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "found": self.found,
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "skipped": self.skipped,
            "partial": self.partial,
            "failed": self.failed,
            "images_created": self.images_created,
            "images_reused": self.images_reused,
            "images_failed": self.images_failed,
            "unknown_categories": self.unknown_categories,
            "review_required": self.review_required,
            "errors": self.errors,
            "items": self.items,
        }


def iter_product_files(catalog_root: Path, *, limit: int | None = None, product_id: str | None = None, category: str | None = None) -> list[Path]:
    files = sorted(catalog_root.glob("*/**/product.json"), key=lambda path: path.as_posix())
    selected = []
    for path in files:
        if category and path.parent.parent.name != category:
            continue
        if product_id:
            try:
                payload = read_product_json(path)
            except Exception:
                continue
            if payload.get("id") != product_id and path.parent.name != product_id:
                continue
        selected.append(path)
        if limit and len(selected) >= limit:
            break
    return selected


def read_product_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def stable_external_id(payload: dict) -> str:
    source = payload.get("source") or {}
    return str(source.get("source_id") or payload.get("id") or "").strip()


def source_url(payload: dict) -> str:
    source = payload.get("source") or {}
    return str(source.get("product_url") or source.get("folder_url") or "").strip()


def import_record_reference(catalog_root: Path, brand_slug: str) -> str:
    return f"{catalog_root.resolve().as_posix()}#{brand_slug}"


def sync_local_catalog(db: Session, options: LocalCatalogSyncOptions) -> LocalCatalogSyncResult:
    result = LocalCatalogSyncResult()
    files = iter_product_files(options.catalog_root, limit=options.limit, product_id=options.product_id, category=options.category)
    result.found = len(files)
    for position, path in enumerate(files):
        nested = db.begin_nested()
        item_result = None
        try:
            item_result = sync_product_file(db, path, options, position)
            if options.dry_run:
                nested.rollback()
            else:
                nested.commit()
            created_upload_paths = item_result.pop("_created_upload_paths", [])
            result.items.append(item_result)
            for key in ("created", "updated", "unchanged", "skipped", "partial", "images_created", "images_reused", "images_failed"):
                setattr(result, key, getattr(result, key) + int(item_result.get(key, 0)))
            if item_result.get("unknown_category"):
                result.unknown_categories += 1
            if item_result.get("review_required"):
                result.review_required += 1
        except Exception as exc:
            nested.rollback()
            for created_path in (item_result or {}).get("_created_upload_paths", []):
                remove_upload_storage_file(created_path, context={"operation": "sync_local_catalog", "path": str(path)})
            result.failed += 1
            result.errors.append({"path": str(path), "error": str(exc)})
            if options.verbose:
                result.items.append({"path": str(path), "failed": 1, "error": str(exc)})
    if options.dry_run:
        db.rollback()
    else:
        db.commit()
    return result


def sync_product_file(db: Session, path: Path, options: LocalCatalogSyncOptions, position: int = 0) -> dict:
    payload = read_product_json(path)
    external_id = stable_external_id(payload)
    if not external_id:
        raise ValueError("product.json sem id/source_id estavel")
    brand_payload = payload.get("brand") or {}
    brand_slug = clean_slug(brand_payload.get("slug") or path.parents[2].name)
    record = get_or_create_import_record(db, options.catalog_root, brand_slug, payload)
    item = find_import_item(db, record, external_id)
    if not item:
        identity = resolve_import_identity(
            source=record.source,
            source_type=record.source_type,
            external_id=external_id,
            source_url=source_url(payload),
            normalized_source_url=source_url(payload) or external_id,
        )
        identity_check = find_existing_identity_item(db, identity, current_record_id=record.id)
        if identity_check.status in {"exact_duplicate", "same_source_existing"}:
            existing = identity_check.existing_item
            return {
                "path": str(path),
                "external_id": external_id,
                "product_id": existing.published_product_id if existing else None,
                "created": 0,
                "updated": 0,
                "unchanged": 1,
                "images_created": 0,
                "images_reused": 0,
                "images_failed": 0,
                "unknown_category": False,
                "review_required": False,
                "duplicate_reason": identity_check.status,
            }
        if identity_check.status in {"conflicting_identity", "manual_review"}:
            raise ValueError(f"identidade de importacao ambigua para local_catalog: {external_id}")
    product = db.get(Product, item.published_product_id) if item and item.published_product_id else None
    created = False
    before = snapshot_product(product) if product else None
    if not product:
        product = create_draft_product(db, payload, path)
        created = True
    brand = get_or_create_brand(db, brand_payload)
    suggested_category, unknown_category = resolve_category(db, payload.get("category") or {})
    if created:
        product.brand_id = brand.id if brand else None
        product.category_id = suggested_category.id if suggested_category else None
        product.audience = (payload.get("supplier_metadata") or {}).get("audience") or product.audience
    product.status = product.status or "draft"
    if product.status != "published":
        product.status = product.status or "draft"
    sync_publication_state(product)
    item = upsert_import_item(db, record, item, product, payload, path, position, brand, suggested_category, unknown_category)
    db.flush()
    created_upload_paths: list[Path] = []
    try:
        image_stats = sync_product_images(db, product, item, payload, path.parent, dry_run=options.dry_run, created_upload_paths=created_upload_paths)
        db.flush()
        after = snapshot_product(product)
        changed = created or before != after or image_stats["images_created"] > 0
        review_required = bool(unknown_category or (payload.get("review") or {}).get("needs_name_review") or (payload.get("review") or {}).get("needs_category_review") or (payload.get("review") or {}).get("brand_conflict") or (payload.get("import") or {}).get("errors"))
        return {
            "path": str(path),
            "external_id": external_id,
            "product_id": product.id,
            "created": int(created),
            "updated": int(not created and changed),
            "unchanged": int(not created and not changed),
            "images_created": image_stats["images_created"],
            "images_reused": image_stats["images_reused"],
            "images_failed": image_stats["images_failed"],
            "unknown_category": unknown_category,
            "review_required": review_required,
            "_created_upload_paths": [str(item) for item in created_upload_paths],
        }
    except Exception:
        for created_path in created_upload_paths:
            remove_upload_storage_file(created_path, context={"operation": "sync_product_file", "path": str(path)})
        raise


def snapshot_product(product: Product | None) -> dict | None:
    if not product:
        return None
    return {
        "name": product.name,
        "description": product.description,
        "price": str(product.price),
        "status": product.status,
        "visibility": product.visibility,
        "brand_id": product.brand_id,
        "category_id": product.category_id,
        "image_count": len(product.images or []),
    }


def clean_slug(value: str | None) -> str:
    return str(value or "").strip().lower()


def get_or_create_import_record(db: Session, catalog_root: Path, brand_slug: str, payload: dict) -> ImportRecord:
    ref = import_record_reference(catalog_root, brand_slug)
    record = db.query(ImportRecord).filter(ImportRecord.source == LOCAL_CATALOG_SOURCE, ImportRecord.external_reference == ref).first()
    if record:
        return record
    record = ImportRecord(
        source=LOCAL_CATALOG_SOURCE,
        external_reference=ref,
        status="preview_ready",
        source_url=(payload.get("source") or {}).get("folder_url"),
        normalized_source_url=(payload.get("source") or {}).get("folder_url"),
        source_type=(payload.get("source") or {}).get("provider") or "local",
        folder_name=brand_slug,
        import_metadata={"catalog_root": str(catalog_root), "brand_slug": brand_slug},
    )
    db.add(record)
    db.flush()
    return record


def find_import_item(db: Session, record: ImportRecord, external_id: str) -> ImportItem | None:
    return db.query(ImportItem).filter(ImportItem.import_record_id == record.id, ImportItem.external_id == external_id).first()


def display_name(payload: dict) -> str:
    return (payload.get("final_name") or payload.get("generated_name") or payload.get("supplier_name") or "Produto importado").strip()


def create_draft_product(db: Session, payload: dict, path: Path) -> Product:
    name = display_name(payload)
    base_slug = clean_slug(path.parent.name) or clean_slug(payload.get("slug")) or name
    product = Product(
        public_id=__import__("uuid").uuid4().hex,
        name=name[:180],
        slug=unique_slug(db, Product, base_slug),
        short_description=None,
        description=(payload.get("description") or {}).get("final") or None,
        price=Decimal("0.00"),
        track_inventory=False,
        stock_quantity=0,
        minimum_stock=0,
        allow_backorder=False,
        availability="unavailable",
        ready_to_ship=False,
        status="draft",
        visibility="hidden",
    )
    db.add(product)
    db.flush()
    return product


def get_or_create_brand(db: Session, payload: dict) -> Brand | None:
    slug = clean_slug(payload.get("slug"))
    name = (payload.get("name") or "").strip()
    if not slug and not name:
        return None
    brand = db.query(Brand).filter(Brand.slug == slug).first() if slug else None
    if not brand and name:
        brand = db.query(Brand).filter(Brand.name.ilike(name)).first()
    if brand:
        return brand
    brand = Brand(name=name or slug.title(), slug=slug or clean_slug(name))
    db.add(brand)
    db.flush()
    return brand


def resolve_category(db: Session, payload: dict) -> tuple[Category | None, bool]:
    slug = clean_slug(payload.get("slug"))
    if not slug or slug == UNKNOWN_CATEGORY_SLUG:
        return None, True
    category = db.query(Category).filter(Category.slug == slug).first()
    if category:
        return category, False
    category = Category(name=(payload.get("name") or slug.replace("-", " ").title()).strip(), slug=slug)
    db.add(category)
    db.flush()
    return category, False


def upsert_import_item(db: Session, record: ImportRecord, item: ImportItem | None, product: Product, payload: dict, path: Path, position: int, brand: Brand | None, category: Category | None, unknown_category: bool) -> ImportItem:
    raw_metadata = local_catalog_metadata(payload, path, unknown_category)
    if not item:
        item = ImportItem(import_record_id=record.id, external_id=stable_external_id(payload))
        db.add(item)
    item.source_url = source_url(payload)
    item.normalized_source_url = source_url(payload) or stable_external_id(payload)
    item.source_title = payload.get("supplier_name")
    item.suggested_name = display_name(payload)
    item.brand_id = brand.id if brand else None
    item.suggested_category = (payload.get("category") or {}).get("name")
    item.suggested_category_id = category.id if category else None
    item.classification_confidence = (payload.get("category") or {}).get("confidence")
    item.status = "published"
    item.image_urls = []
    item.cover_image_url = None
    item.image_count = len((payload.get("images") or {}).get("items") or [])
    item.position = position
    item.warnings = list((payload.get("review") or {}).get("notes") or [])
    item.classification_evidence = payload.get("category")
    item.raw_metadata = raw_metadata
    item.published_product_id = product.id
    item.published_at = item.published_at or utc_now()
    item.publish_metadata = {"created_product_status": product.status, "created_product_visibility": product.visibility, "local_catalog_sync": True}
    return item


def local_catalog_metadata(payload: dict, path: Path, unknown_category: bool) -> dict:
    return {
        "source": "backend/catalog",
        "catalog_path": path.as_posix(),
        "stable_id": stable_external_id(payload),
        "supplier": {
            "name": payload.get("supplier_name"),
            "code": payload.get("supplier_code"),
            "url": (payload.get("description") or {}).get("supplier"),
            "provider": (payload.get("source") or {}).get("provider"),
            "folder_url": (payload.get("source") or {}).get("folder_url"),
            "product_url": (payload.get("source") or {}).get("product_url"),
            "category": (payload.get("category") or {}).get("name"),
        },
        "names": {
            "supplier_name": payload.get("supplier_name"),
            "generated_name": payload.get("generated_name"),
            "final_name": payload.get("final_name"),
        },
        "detected": {
            "brand": payload.get("brand"),
            "category": payload.get("category"),
            "audience": (payload.get("supplier_metadata") or {}).get("audience"),
        },
        "review": payload.get("review") or {},
        "import": payload.get("import") or {},
        "unknown_category": unknown_category,
        "raw": payload,
    }


def sync_product_images(db: Session, product: Product, item: ImportItem, payload: dict, product_dir: Path, *, dry_run: bool = False, created_upload_paths: list[Path] | None = None) -> dict:
    stats = {"images_created": 0, "images_reused": 0, "images_failed": 0}
    images = sorted((payload.get("images") or {}).get("items") or [], key=lambda image: image.get("position", 0))
    existing_by_filename = {image.filename: image for image in product.images or []}
    upload_dir = Path(settings.upload_directory) / "products" / product.public_id
    if not dry_run:
        ensure_canonical_upload_write_allowed()
        upload_dir.mkdir(parents=True, exist_ok=True)
    image_urls = []
    cover_url = None
    for image in images:
        source_path = product_dir / str(image.get("filename") or "")
        if not source_path.exists():
            stats["images_failed"] += 1
            continue
        filename = deterministic_image_filename(image, source_path)
        public_url = f"/uploads/products/{product.public_id}/{filename}"
        target_path = upload_dir / filename
        if filename in existing_by_filename:
            record = existing_by_filename[filename]
            record.position = int(image.get("position") or 0)
            record.is_primary = image.get("filename") == (payload.get("images") or {}).get("cover")
            record.public_url = public_url
            record.storage_path = str(target_path)
            record.mime_type = image.get("mime_type") or record.mime_type or "application/octet-stream"
            record.size_bytes = int(source_path.stat().st_size)
            record.width = int(image.get("width") or record.width or 0)
            record.height = int(image.get("height") or record.height or 0)
            if not dry_run and not target_path.exists():
                shutil.copy2(source_path, target_path)
                if created_upload_paths is not None:
                    created_upload_paths.append(target_path)
                stats["images_created"] += 1
            else:
                stats["images_reused"] += 1
        else:
            if not dry_run:
                shutil.copy2(source_path, target_path)
                if created_upload_paths is not None:
                    created_upload_paths.append(target_path)
            record = ProductImage(
                product_id=product.id,
                filename=filename,
                storage_path=str(target_path),
                public_url=public_url,
                mime_type=image.get("mime_type") or "application/octet-stream",
                size_bytes=int(source_path.stat().st_size),
                width=int(image.get("width") or 0),
                height=int(image.get("height") or 0),
                alt_text=payload.get("final_name") or payload.get("generated_name"),
                is_primary=image.get("filename") == (payload.get("images") or {}).get("cover"),
                position=int(image.get("position") or 0),
            )
            db.add(record)
            stats["images_created"] += 1
        db.flush()
        image_urls.append(public_url)
        if record.is_primary:
            cover_url = public_url
        upsert_import_image(db, item, image, public_url, source_path, record)
    item.image_urls = image_urls
    item.cover_image_url = cover_url or (image_urls[0] if image_urls else None)
    item.image_count = len(image_urls)
    return stats


def deterministic_image_filename(image: dict, source_path: Path) -> str:
    sha = str(image.get("sha256") or file_sha256(source_path))
    suffix = source_path.suffix.lower() or ".jpg"
    return f"{int(image.get('position') or 0):02d}-{sha[:16]}{suffix}"


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def upsert_import_image(db: Session, item: ImportItem, image: dict, public_url: str, source_path: Path, record: ProductImage) -> None:
    normalized = str(image.get("source_url") or image.get("sha256") or public_url)
    import_image = next((candidate for candidate in item.images if candidate.normalized_source_url == normalized), None)
    if not import_image:
        import_image = ImportImage(import_item_id=item.id, source_url=str(image.get("source_url") or public_url), normalized_source_url=normalized)
        db.add(import_image)
    import_image.position = int(image.get("position") or 0)
    import_image.is_cover = bool(record.is_primary)
    import_image.is_selected = True
    import_image.status = "active"
    import_image.width = int(image.get("width") or 0)
    import_image.height = int(image.get("height") or 0)
    import_image.alt_text = record.alt_text
    import_image.source_type = "local_catalog"
    import_image.image_metadata = image
    import_image.ingestion_status = "stored"
    import_image.local_filename = record.filename
    import_image.local_storage_path = record.storage_path
    import_image.local_public_url = public_url
    import_image.local_mime_type = record.mime_type
    import_image.local_size_bytes = record.size_bytes
    import_image.local_width = record.width
    import_image.local_height = record.height
    import_image.content_sha256 = str(image.get("sha256") or "")
