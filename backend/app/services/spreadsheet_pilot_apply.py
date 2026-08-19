from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Brand, Category, ImportImage, ImportItem, ImportRecord, Product, ProductImage, utc_now
from app.services.import_identity import find_existing_import_item as find_existing_identity_item
from app.services.import_identity import resolve_import_identity
from app.services.products import sync_publication_state
from app.services.spreadsheet_pilot import normalize_url
from app.services.upload_storage import ensure_canonical_upload_write_allowed, remove_upload_storage_file
from app.utils.slug import make_slug, unique_slug


SPREADSHEET_SOURCE = "spreadsheet/fansbuy"
EXPECTED_RUN_ID = "pilot-51fcc229-limit10-20260803163159"
SPREADSHEET_ID = "dripzone-piloto-mais-vendidos.xlsx"
SHEET_NAME = "Mais Vendidos"
TECHNICAL_PRICE = Decimal("0.00")

PRODUCT_NAMES = {
    "7792640380": "Air Jordan 4",
    "7792628442": "Adidas Campus",
    "7792489288": "Adidas Samba",
    "7789591169": "Adidas Hoodie",
    "7792669908": "Adwysd Hoodie",
    "7789652245": "Bolsa Adidas",
    "7789569421": "Calça Jeans Amiri",
    "7792588954": "Conjunto 6PM",
    "7792596868": "Jaqueta Moncler Couyere",
}
BLOCKED_CODES = {"7789575461": "ambiguous_brand_manual_review"}
CREATABLE_BRANDS = {"Adwysd", "6PM"}
AMBIGUOUS_BRANDS = {"Ami"}


@dataclass
class ApplyPilotResult:
    run_id: str
    dry_run: bool = False
    products_created: int = 0
    products_existing: int = 0
    brands_created: list[dict] = field(default_factory=list)
    brands_existing: list[dict] = field(default_factory=list)
    blocked: list[dict] = field(default_factory=list)
    images_created: int = 0
    images_reused: int = 0
    import_items_created: int = 0
    import_items_existing: int = 0
    failed: list[dict] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "dry_run": self.dry_run,
            "products_created": self.products_created,
            "products_existing": self.products_existing,
            "brands_created": self.brands_created,
            "brands_existing": self.brands_existing,
            "blocked": self.blocked,
            "images_created": self.images_created,
            "images_reused": self.images_reused,
            "import_items_created": self.import_items_created,
            "import_items_existing": self.import_items_existing,
            "failed": self.failed,
            "items": self.items,
        }


def load_manifest(run_dir: Path) -> dict:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"manifest.json ausente: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("run_id") != EXPECTED_RUN_ID:
        raise ValueError(f"run_id invalido: {manifest.get('run_id')}")
    if int(manifest.get("products_count") or 0) != 10:
        raise ValueError("run validado deve conter exatamente 10 produtos")
    return manifest


def load_proposals(run_dir: Path) -> list[dict]:
    manifest = load_manifest(run_dir)
    proposals = []
    for relative in manifest.get("proposals") or []:
        path = run_dir / relative
        if not path.is_file():
            raise ValueError(f"proposta ausente: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["_proposal_relative_path"] = str(relative)
        proposals.append(payload)
    codes = {proposal.get("supplier_code") for proposal in proposals}
    expected = set(PRODUCT_NAMES) | set(BLOCKED_CODES)
    if codes != expected:
        raise ValueError(f"codigos do run nao correspondem ao piloto validado: {sorted(codes)}")
    return proposals


def normalized_brand_key(value: str) -> str:
    return make_slug(value).replace("-", "")


def find_brand(db: Session, name: str) -> Brand | None:
    slug = make_slug(name)
    direct = db.query(Brand).filter(or_(func.lower(Brand.name) == name.casefold(), Brand.slug == slug)).first()
    if direct:
        return direct
    wanted = normalized_brand_key(name)
    return next((brand for brand in db.query(Brand).all() if normalized_brand_key(brand.name) == wanted or normalized_brand_key(brand.slug) == wanted), None)


def get_or_create_allowed_brand(db: Session, name: str, result: ApplyPilotResult) -> Brand:
    if name in AMBIGUOUS_BRANDS:
        raise ValueError(f"marca ambigua bloqueada: {name}")
    brand = find_brand(db, name)
    if brand:
        result.brands_existing.append({"name": brand.name, "id": brand.id})
        return brand
    if name not in CREATABLE_BRANDS:
        raise ValueError(f"marca ausente nao permitida neste piloto: {name}")
    brand = Brand(name=name, slug=unique_slug(db, Brand, name), is_active=True)
    db.add(brand)
    db.flush()
    result.brands_created.append({"name": brand.name, "id": brand.id, "slug": brand.slug})
    return brand


def get_category(db: Session, slug: str) -> Category:
    category = db.query(Category).filter(Category.slug == slug).first()
    if not category:
        raise ValueError(f"categoria ausente: {slug}")
    return category


def get_or_create_record(db: Session, run_dir: Path, manifest: dict) -> ImportRecord:
    record = db.query(ImportRecord).filter(ImportRecord.source == SPREADSHEET_SOURCE, ImportRecord.external_reference == EXPECTED_RUN_ID).first()
    if record:
        return record
    record = ImportRecord(
        source=SPREADSHEET_SOURCE,
        external_reference=EXPECTED_RUN_ID,
        status="preview_ready",
        source_type="spreadsheet",
        folder_name=SHEET_NAME,
        started_at=utc_now(),
        finished_at=utc_now(),
        import_metadata={
            "run_id": EXPECTED_RUN_ID,
            "run_dir": str(run_dir),
            "spreadsheet_id": SPREADSHEET_ID,
            "sheet_name": SHEET_NAME,
            "workbook_sha256": manifest.get("workbook_sha256"),
            "pilot_manifest": manifest,
        },
    )
    db.add(record)
    db.flush()
    return record


def find_import_item(db: Session, record: ImportRecord, code: str, normalized_url: str) -> ImportItem | None:
    return (
        db.query(ImportItem)
        .filter(ImportItem.import_record_id == record.id)
        .filter(or_(ImportItem.external_id == code, ImportItem.normalized_source_url == normalized_url))
        .first()
    )


def existing_product(db: Session, code: str, item: ImportItem | None = None) -> Product | None:
    if item and item.published_product_id:
        product = db.get(Product, item.published_product_id)
        if product:
            return product
    return db.query(Product).filter(Product.sku == code).first()


def proposal_image(proposal: dict, run_dir: Path) -> tuple[dict, Path]:
    stored = [image for image in proposal.get("supplier_images") or [] if image.get("status") == "stored" and image.get("filename")]
    if not stored:
        raise ValueError("produto sem imagem valida no piloto")
    image = sorted(stored, key=lambda item: int(item.get("position") or 0))[0]
    source_path = run_dir / "images" / image["filename"]
    if not source_path.is_file():
        raise ValueError(f"imagem do run ausente: {image['filename']}")
    digest = file_sha256(source_path)
    if image.get("sha256") and digest != image["sha256"]:
        raise ValueError(f"hash da imagem divergente: {image['filename']}")
    return image, source_path


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def managed_image_filename(image: dict, source_path: Path) -> str:
    suffix = source_path.suffix.lower() or ".jpg"
    return f"01-{str(image.get('sha256') or file_sha256(source_path))[:16]}{suffix}"


def create_product(db: Session, proposal: dict, brand: Brand, category: Category) -> Product:
    code = str(proposal["supplier_code"])
    name = PRODUCT_NAMES[code]
    product = Product(
        public_id=uuid4().hex,
        name=name,
        slug=unique_slug(db, Product, name),
        sku=code,
        short_description="Produto em rascunho para revisão editorial antes da publicação.",
        description="Produto importado da planilha de fornecedores da DripZone. Informações comerciais, estoque e descrição final aguardam revisão.",
        brand_id=brand.id,
        category_id=category.id,
        price=TECHNICAL_PRICE,
        compare_at_price=None,
        cost_price=None,
        promotional_price=None,
        track_inventory=False,
        stock_quantity=0,
        minimum_stock=0,
        allow_backorder=False,
        availability="unavailable",
        ready_to_ship=False,
        status="draft",
        visibility="hidden",
        is_featured=False,
        is_new=False,
        is_best_seller=False,
        main_image_alt=name,
    )
    sync_publication_state(product)
    db.add(product)
    db.flush()
    return product


def align_existing_product(product: Product, proposal: dict, brand: Brand, category: Category) -> None:
    code = str(proposal["supplier_code"])
    product.name = PRODUCT_NAMES[code]
    product.brand_id = brand.id
    product.category_id = category.id
    product.price = TECHNICAL_PRICE
    product.compare_at_price = None
    product.cost_price = None
    product.promotional_price = None
    product.track_inventory = False
    product.stock_quantity = 0
    product.minimum_stock = 0
    product.allow_backorder = False
    product.availability = "unavailable"
    product.ready_to_ship = False
    product.status = "draft"
    product.visibility = "hidden"
    product.main_image_alt = product.name
    sync_publication_state(product)


def upsert_import_item(db: Session, record: ImportRecord, proposal: dict, product: Product | None, brand: Brand | None, category: Category | None, *, status: str, reason: str | None = None) -> tuple[ImportItem, bool]:
    code = str(proposal["supplier_code"])
    normalized = normalize_url(proposal["supplier_url"])
    item = find_import_item(db, record, code, normalized)
    created = False
    if not item:
        item = ImportItem(import_record_id=record.id, external_id=code)
        db.add(item)
        created = True
    item.source_url = proposal["supplier_url"]
    item.normalized_source_url = normalized
    item.source_title = proposal.get("supplier_name")
    item.suggested_name = PRODUCT_NAMES.get(code) or proposal.get("suggested_name")
    item.brand_id = brand.id if brand else None
    item.suggested_category = proposal.get("category_name")
    item.suggested_category_id = category.id if category else None
    item.status = status
    item.image_urls = [image.get("source_url") or image.get("filename") for image in proposal.get("supplier_images") or []]
    item.cover_image_url = item.image_urls[0] if item.image_urls else None
    item.image_count = len(item.image_urls or [])
    item.position = int(proposal.get("spreadsheet_row") or 0)
    item.duplicate_reason = reason
    item.warnings = list(proposal.get("warnings") or [])
    item.classification_evidence = {"category_slug": proposal.get("category_slug"), "category_id": proposal.get("category_id")}
    item.raw_metadata = raw_metadata(proposal)
    if product:
        item.published_product_id = product.id
        item.published_at = item.published_at or utc_now()
        item.publish_metadata = {"created_product_status": product.status, "created_product_visibility": product.visibility, "spreadsheet_pilot_apply": True}
    db.flush()
    return item, created


def raw_metadata(proposal: dict) -> dict:
    code = str(proposal["supplier_code"])
    return {
        "source": SPREADSHEET_SOURCE,
        "spreadsheet": {"id": SPREADSHEET_ID, "sheet_name": SHEET_NAME, "row": proposal.get("spreadsheet_row")},
        "supplier": {
            "code": code,
            "url": proposal.get("supplier_url"),
            "normalized_url": normalize_url(proposal.get("supplier_url") or ""),
            "name_original": proposal.get("supplier_name"),
            "category_original": proposal.get("spreadsheet_category"),
            "price_usd_reference": proposal.get("price_usd_reference"),
            "price_brl_reference": proposal.get("price_brl_reference"),
        },
        "names": {"original": proposal.get("supplier_name"), "pilot_suggested": proposal.get("suggested_name"), "final": PRODUCT_NAMES.get(code)},
        "brand": {"detected": proposal.get("detected_brand"), "status": proposal.get("brand_status"), "id": proposal.get("brand_id")},
        "category": {"slug": proposal.get("category_slug"), "name": proposal.get("category_name"), "id": proposal.get("category_id")},
        "images": proposal.get("supplier_images") or [],
        "run": {"id": EXPECTED_RUN_ID, "proposal": proposal.get("_proposal_relative_path")},
        "pilot": proposal,
    }


def sync_product_image(
    db: Session,
    item: ImportItem,
    product: Product,
    proposal: dict,
    run_dir: Path,
    result: ApplyPilotResult,
    *,
    dry_run: bool = False,
    created_upload_paths: list[Path] | None = None,
) -> ProductImage:
    image, source_path = proposal_image(proposal, run_dir)
    upload_dir = Path(settings.upload_directory) / "products" / product.public_id
    if not dry_run:
        ensure_canonical_upload_write_allowed()
        upload_dir.mkdir(parents=True, exist_ok=True)
    filename = managed_image_filename(image, source_path)
    target_path = upload_dir / filename
    public_url = f"/uploads/products/{product.public_id}/{filename}"
    record = next((candidate for candidate in product.images if candidate.filename == filename), None)
    if target_path.exists():
        result.images_reused += 1
    else:
        if not dry_run:
            shutil.copy2(source_path, target_path)
            if created_upload_paths is not None:
                created_upload_paths.append(target_path)
        result.images_created += 1
    if not record:
        record = ProductImage(
            product_id=product.id,
            filename=filename,
            storage_path=str(target_path),
            public_url=public_url,
            mime_type=image.get("mime") or "application/octet-stream",
            size_bytes=int(source_path.stat().st_size),
            width=int(image.get("width") or 0),
            height=int(image.get("height") or 0),
            alt_text=product.name,
            is_primary=True,
            position=1,
        )
        db.add(record)
    else:
        record.storage_path = str(target_path)
        record.public_url = public_url
        record.is_primary = True
        record.position = 1
    db.flush()
    upsert_import_image(db, item, image, record, public_url)
    return record


def upsert_import_image(db: Session, item: ImportItem, image: dict, record: ProductImage, public_url: str) -> None:
    normalized = str(image.get("source_url") or image.get("sha256") or public_url)
    import_image = next((candidate for candidate in item.images if candidate.normalized_source_url == normalized), None)
    if not import_image:
        import_image = ImportImage(import_item_id=item.id, source_url=str(image.get("source_url") or public_url), normalized_source_url=normalized)
        db.add(import_image)
    import_image.position = 1
    import_image.is_cover = True
    import_image.is_selected = True
    import_image.status = "active"
    import_image.width = record.width
    import_image.height = record.height
    import_image.alt_text = record.alt_text
    import_image.source_type = image.get("source_type") or "spreadsheet_pilot"
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


def apply_spreadsheet_pilot(db: Session, run_dir: Path, *, dry_run: bool = False) -> ApplyPilotResult:
    manifest = load_manifest(run_dir)
    proposals = load_proposals(run_dir)
    result = ApplyPilotResult(run_id=EXPECTED_RUN_ID, dry_run=dry_run)
    record = get_or_create_record(db, run_dir, manifest)
    db.flush()
    for proposal in sorted(proposals, key=lambda item: int(item.get("spreadsheet_row") or 0)):
        code = str(proposal["supplier_code"])
        nested = db.begin_nested()
        created_upload_paths: list[Path] = []
        try:
            if code in BLOCKED_CODES:
                brand = find_brand(db, proposal.get("detected_brand") or "")
                category = get_category(db, proposal["category_slug"])
                item, created_item = upsert_import_item(db, record, proposal, None, brand, category, status="needs_review", reason=BLOCKED_CODES[code])
                result.blocked.append({"supplier_code": code, "reason": BLOCKED_CODES[code], "import_item_id": item.id})
                result.import_items_created += int(created_item)
                result.import_items_existing += int(not created_item)
                nested.commit()
                continue
            if code not in PRODUCT_NAMES:
                raise ValueError(f"codigo nao permitido neste piloto: {code}")
            category = get_category(db, proposal["category_slug"])
            brand = get_or_create_allowed_brand(db, proposal["detected_brand"], result)
            normalized = normalize_url(proposal["supplier_url"])
            item = find_import_item(db, record, code, normalized)
            product = existing_product(db, code, item)
            created_product = False
            if not product:
                identity = resolve_import_identity(
                    source=record.source,
                    source_type=record.source_type,
                    external_id=code,
                    source_url=proposal["supplier_url"],
                    normalized_source_url=normalized,
                )
                identity_check = find_existing_identity_item(db, identity, current_record_id=record.id)
                if identity_check.status in {"exact_duplicate", "same_source_existing"}:
                    raise ValueError(f"supplier_code ja existe em importacao equivalente: {code}")
                if identity_check.status in {"conflicting_identity", "manual_review"}:
                    raise ValueError(f"identidade de importacao ambigua para supplier_code: {code}")
                product = create_product(db, proposal, brand, category)
                created_product = True
            else:
                align_existing_product(product, proposal, brand, category)
            item, created_item = upsert_import_item(db, record, proposal, product, brand, category, status="created_draft")
            image_record = sync_product_image(db, item, product, proposal, run_dir, result, dry_run=dry_run, created_upload_paths=created_upload_paths)
            if not image_record.id:
                raise ValueError(f"produto sem imagem principal: {code}")
            sync_publication_state(product)
            result.products_created += int(created_product)
            result.products_existing += int(not created_product)
            result.import_items_created += int(created_item)
            result.import_items_existing += int(not created_item)
            result.items.append(
                {
                    "supplier_code": code,
                    "product_id": product.id,
                    "brand_id": brand.id,
                    "category_id": category.id,
                    "image_id": image_record.id,
                    "created": created_product,
                    "status": product.status,
                    "visibility": product.visibility,
                }
            )
            nested.commit()
        except Exception as exc:
            nested.rollback()
            for storage_path in created_upload_paths:
                remove_upload_storage_file(storage_path, context={"operation": "spreadsheet_pilot_apply", "supplier_code": code})
            result.failed.append({"supplier_code": code, "error": str(exc)})
    record.items_found = len(proposals)
    record.items_needs_review = len(result.blocked)
    record.items_published = 0
    record.items_pending = 0
    record.status = "partial" if result.failed else "preview_ready"
    record.error_count = len(result.failed)
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return result
