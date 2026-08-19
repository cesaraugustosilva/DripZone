from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Brand, Category, ImportItem, ImportRecord, Product, utc_now
from app.services.import_identity import find_existing_import_item as find_existing_identity_item
from app.services.import_identity import resolve_import_identity
from app.services.products import (
    evaluate_showcase_readiness,
    export_public_products,
    cleanup_public_catalog_stage,
    publish_public_catalog_stage,
    stage_public_catalog,
    sync_publication_state,
    write_bytes_atomically,
)
from app.services.spreadsheet_pilot import (
    PROJECT_ROOT,
    SpreadsheetProduct,
    atomic_write_json,
    build_proposal,
    canonical_brand_name,
    duplicate_check,
    load_spreadsheet_products,
    normalize_url,
    workbook_sha,
)
from app.services.spreadsheet_pilot_apply import file_sha256, proposal_image, sync_product_image
from app.services.product_name_curation import source_has_multiple_variants
from app.utils.slug import make_slug, unique_slug


ENRICHMENT_SOURCE = "spreadsheet/fansbuy/enriched"
SPREADSHEET_ID = "dripzone-piloto-mais-vendidos.xlsx"
SHEET_NAME = "Mais Vendidos"
TECHNICAL_PRICE = Decimal("0.00")
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "imports" / "enriched"
BLOCKED_CATEGORY_PREFIXES = {"09", "10", "11", "99"}
DEFAULT_CATEGORY_TARGETS = {
    "sneakers": 5,
    "camisetas": 4,
    "moletons": 5,
    "calcas": 4,
    "conjuntos": 3,
    "jaquetas": 3,
    "acessorios": 1,
}
AMBIGUOUS_BRAND_NAMES = {"ami", "boss", "stanley"}


@dataclass
class EnrichmentDecision:
    supplier_code: str
    supplier_name: str
    detected_brand: str
    official_name: str | None
    official_model: str | None
    style_code: str | None
    variant: str | None
    category_id: int | None
    name_confidence: float
    brand_confidence: float
    category_confidence: float
    image_match_confidence: float
    warnings: list[str] = field(default_factory=list)
    decision: str = "manual_review"
    research: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "supplier_code": self.supplier_code,
            "supplier_name": self.supplier_name,
            "detected_brand": self.detected_brand,
            "official_name": self.official_name,
            "official_model": self.official_model,
            "style_code": self.style_code,
            "variant": self.variant,
            "category_id": self.category_id,
            "name_confidence": self.name_confidence,
            "brand_confidence": self.brand_confidence,
            "category_confidence": self.category_confidence,
            "image_match_confidence": self.image_match_confidence,
            "warnings": self.warnings,
            "decision": self.decision,
            "research": self.research,
        }


@dataclass
class EnrichedBatchResult:
    run_id: str
    dry_run: bool
    selected: int = 0
    auto_apply: int = 0
    manual_review: int = 0
    blocked: int = 0
    products_created: int = 0
    products_existing: int = 0
    products_published_showcase: int = 0
    products_draft_hidden: int = 0
    brands_created: list[dict] = field(default_factory=list)
    brands_existing: list[dict] = field(default_factory=list)
    images_created: int = 0
    images_reused: int = 0
    import_items_created: int = 0
    import_items_existing: int = 0
    failed: list[dict] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)
    exported_products: int = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def clean_supplier_title(name: str) -> str:
    first = (name or "").splitlines()[0].strip()
    first = first.replace("[PK BATCH]", "").replace("[OG BATCH]", "").replace("[M BATCH]", "")
    first = first.replace("[Premium Quality]", "").replace("[Top Quality]", "").replace("[OG Quality]", "")
    first = first.replace("  ", " ").strip(" -")
    return first


def squash_spaces(value: str) -> str:
    return " ".join(value.split())


def has_multiple_variants(name: str) -> bool:
    return source_has_multiple_variants(name)


def commercial_name(product: SpreadsheetProduct, brand_name: str) -> tuple[str, str | None, float, list[str]]:
    title = clean_supplier_title(product.supplier_name)
    folded = title.casefold()
    warnings: list[str] = []
    model = title
    if brand_name and folded.startswith(brand_name.casefold()):
        model = title[len(brand_name) :].strip(" -")
    elif brand_name == "Jordan" and folded.startswith("air jordan"):
        model = title
    elif brand_name == "Nike" and folded.startswith("air force"):
        model = title
    name_confidence = 0.9

    if not title:
        return product.supplier_name, None, 0.0, ["missing_name"]
    if any(term in folded for term in ("perfume", "watch", "electronic", "phone", "speaker")):
        warnings.append("out_of_scope_product_type")
        name_confidence = 0.4
    if "hoodie" in folded and "shirt" in folded:
        warnings.append("ambiguous_product_type")
        name_confidence = min(name_confidence, 0.7)

    if product.category_slug == "camisetas":
        if "tee" in folded:
            model = model.replace("Tee", "").replace("tee", "").strip()
            return squash_spaces(f"Camiseta {brand_name} {model}"), model or None, name_confidence, warnings
        if "shirt" in folded:
            model = model.replace("Shirt", "").replace("shirt", "").strip()
            return squash_spaces(f"Camiseta {brand_name} {model}"), model or None, name_confidence, warnings
    if product.category_slug == "moletons":
        if "zipper hoodie" in folded or "zip hoodie" in folded:
            model = model.replace("Zipper Hoodie", "").replace("zipper hoodie", "").strip()
            return squash_spaces(f"Moletom {brand_name} {model} com Ziper"), model or None, name_confidence, warnings
        if "hoodie" in folded:
            model = model.replace("Hoodie", "").replace("hoodie", "").strip()
            return squash_spaces(f"Moletom {brand_name} {model}"), model or None, name_confidence, warnings
        if "sweater" in folded:
            model = model.replace("Sweater", "").replace("sweater", "").strip()
            return squash_spaces(f"Moletom {brand_name} {model}"), model or None, name_confidence, warnings
    if product.category_slug == "calcas":
        if "jeans" in folded:
            model = model.replace("Jeans", "").replace("jeans", "").strip()
            return squash_spaces(f"Calca Jeans {brand_name} {model}"), model or None, name_confidence, warnings
        if "pants" in folded or "trousers" in folded:
            model = model.replace("Pants", "").replace("pants", "").replace("Trousers", "").replace("trousers", "").strip()
            return squash_spaces(f"Calca {brand_name} {model}"), model or None, name_confidence, warnings
    if product.category_slug == "conjuntos":
        model = model.replace("Set", "").replace("set", "").strip()
        return squash_spaces(f"Conjunto {brand_name} {model}"), model or None, name_confidence, warnings
    if product.category_slug == "jaquetas":
        suffix = ""
        for source, target in (
            ("Quilted Jacket", "Matelasse"),
            ("Down Jacket", "Puffer"),
            ("Puffer Jacket", "Puffer"),
            ("Jacket", ""),
        ):
            if source.casefold() in folded:
                model = model.replace(source, "").strip()
                suffix = target
                break
        return squash_spaces(f"Jaqueta {brand_name} {model} {suffix}"), model or None, name_confidence, warnings
    if product.category_slug == "acessorios":
        if "backpack" in folded:
            model = model.replace("Backpack", "").strip()
            return squash_spaces(f"Mochila {brand_name} {model}"), model or None, name_confidence, warnings
        if "hat" in folded:
            model = model.replace("Knitted Hat", "").replace("Hat", "").strip()
            return squash_spaces(f"Gorro {brand_name} {model}"), model or None, name_confidence, warnings
        if "bag" in folded:
            model = model.replace("Bag", "").strip()
            return squash_spaces(f"Bolsa {brand_name} {model}"), model or None, name_confidence, warnings
    return title, model or None, name_confidence, warnings


def normalize_brand_key(value: str) -> str:
    return make_slug(value).replace("-", "")


def find_brand(db: Session, name: str) -> Brand | None:
    slug = make_slug(name)
    direct = db.query(Brand).filter(or_(func.lower(Brand.name) == name.casefold(), Brand.slug == slug)).first()
    if direct:
        return direct
    wanted = normalize_brand_key(name)
    return next((brand for brand in db.query(Brand).all() if normalize_brand_key(brand.name) == wanted or normalize_brand_key(brand.slug) == wanted), None)


def category_by_slug(db: Session, slug: str) -> Category | None:
    return db.query(Category).filter(Category.slug == slug).first()


def existing_codes(db: Session) -> set[str]:
    codes = {str(code) for (code,) in db.query(Product.sku).filter(Product.sku.isnot(None)).all()}
    codes.update(str(code) for (code,) in db.query(ImportItem.external_id).filter(ImportItem.external_id.isnot(None)).all())
    return codes


def select_batch_products(products: list[SpreadsheetProduct], *, existing: set[str], limit: int = 25) -> list[SpreadsheetProduct]:
    selected: list[SpreadsheetProduct] = []
    seen: set[str] = set()
    by_slug = {slug: 0 for slug in DEFAULT_CATEGORY_TARGETS}

    def eligible(product: SpreadsheetProduct) -> bool:
        if product.supplier_code in existing:
            return False
        if not product.supplier_code or not product.supplier_url:
            return False
        if product.category_raw[:2] in BLOCKED_CATEGORY_PREFIXES or product.category_raw == "99 REMOVER":
            return False
        key = product.supplier_code or normalize_url(product.supplier_url)
        return key not in seen

    def add(product: SpreadsheetProduct) -> None:
        key = product.supplier_code or normalize_url(product.supplier_url)
        if len(selected) < limit and eligible(product):
            selected.append(product)
            seen.add(key)
            by_slug[product.category_slug] = by_slug.get(product.category_slug, 0) + 1

    for prefer_single_variant in (True, False):
        for slug, target in DEFAULT_CATEGORY_TARGETS.items():
            for product in products:
                if len(selected) >= limit or by_slug.get(slug, 0) >= target:
                    break
                if product.category_slug != slug:
                    continue
                if prefer_single_variant and has_multiple_variants(product.supplier_name):
                    continue
                add(product)
    for product in products:
        if len(selected) >= limit:
            break
        add(product)
    return selected


def enrich_proposal(db: Session, proposal: dict, selected: list[SpreadsheetProduct]) -> EnrichmentDecision:
    warnings = list(proposal.get("warnings") or [])
    brand_name = proposal.get("detected_brand") or canonical_brand_name(proposal.get("supplier_name") or "")
    brand = find_brand(db, brand_name) if brand_name else None
    category = category_by_slug(db, proposal.get("category_slug") or "")
    product_shell = next(item for item in selected if item.supplier_code == proposal["supplier_code"])
    final_name, model, name_confidence, name_warnings = commercial_name(product_shell, brand_name)
    warnings.extend(name_warnings)
    if has_multiple_variants(product_shell.supplier_name):
        warnings.append("multiple_variants_source")
    if not any(image.get("status") == "stored" for image in proposal.get("supplier_images") or []):
        warnings.append("missing_valid_image")
    duplicate = proposal.get("duplicate_check") or duplicate_check(db, product_shell, selected)
    if duplicate.get("is_duplicate"):
        warnings.append("duplicate")
    brand_confidence = 0.98 if brand else 0.95
    if not brand_name or brand_name.casefold() in AMBIGUOUS_BRAND_NAMES:
        warnings.append("brand_requires_manual_review")
        brand_confidence = 0.5
    category_confidence = 0.95 if category else 0.0
    image_match_confidence = 0.9 if any(image.get("status") == "stored" for image in proposal.get("supplier_images") or []) else 0.0

    decision = "auto_apply"
    critical = {"duplicate", "missing_valid_image", "out_of_scope_product_type", "brand_requires_manual_review"}
    if duplicate.get("is_duplicate") or any(item in warnings for item in critical) or category is None:
        decision = "blocked"
    elif (
        has_multiple_variants(product_shell.supplier_name)
        or name_confidence < 0.85
        or brand_confidence < 0.95
        or category_confidence < 0.9
        or image_match_confidence < 0.9
    ):
        decision = "manual_review"

    return EnrichmentDecision(
        supplier_code=proposal["supplier_code"],
        supplier_name=proposal.get("supplier_name") or "",
        detected_brand=brand_name,
        official_name=final_name,
        official_model=model,
        style_code=None,
        variant=None,
        category_id=category.id if category else None,
        name_confidence=round(name_confidence, 2),
        brand_confidence=round(brand_confidence, 2),
        category_confidence=round(category_confidence, 2),
        image_match_confidence=round(image_match_confidence, 2),
        warnings=list(dict.fromkeys(warnings)),
        decision=decision,
        research=[{"status": "skipped", "reason": "deterministic_name_brand_category_sufficient"}],
    )


def unique_run_dir(output_root: Path, base_run_id: str) -> tuple[str, Path]:
    run_dir = output_root / base_run_id
    if not run_dir.exists():
        return base_run_id, run_dir
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    candidate = output_root / f"{base_run_id}-{suffix}"
    counter = 2
    while candidate.exists():
        candidate = output_root / f"{base_run_id}-{suffix}-{counter}"
        counter += 1
    return candidate.name, candidate


def generate_enriched_batch(
    db: Session,
    *,
    xlsx: Path,
    limit: int = 25,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    client_factory=None,
) -> dict:
    if limit != 25:
        raise ValueError("Esta execucao operacional deve selecionar exatamente 25 produtos.")
    digest = workbook_sha(xlsx)
    base_run_id = f"enriched-{digest[:8]}-limit{limit}"
    run_id, run_dir = unique_run_dir(output_root, base_run_id)
    run_dirs = {"root": run_dir, "products": run_dir / "products", "images": run_dir / "images", "logs": run_dir / "logs"}
    for directory in run_dirs.values():
        directory.mkdir(parents=True, exist_ok=True)

    inspection, products = load_spreadsheet_products(xlsx)
    selected = select_batch_products(products, existing=existing_codes(db), limit=limit)
    if len(selected) != limit:
        raise ValueError(f"Nao foi possivel selecionar 25 produtos novos; selecionados={len(selected)}")

    proposals = []
    for product in selected:
        proposal = build_proposal(db, product, selected, run_dirs, dry_run=True, client_factory=client_factory)
        enrichment = enrich_proposal(db, proposal, selected)
        proposal["enrichment"] = enrichment.as_dict()
        proposal["suggested_name"] = enrichment.official_name or proposal.get("suggested_name")
        proposal["review_required"] = enrichment.decision != "auto_apply"
        atomic_write_json(run_dirs["products"] / f"{proposal['spreadsheet_row']}-{proposal['supplier_code']}.json", proposal)
        proposals.append(proposal)

    manifest = {
        "run_id": run_id,
        "base_run_id": base_run_id,
        "dry_run": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "xlsx": str(xlsx),
        "workbook_sha256": digest,
        "inspection": inspection.__dict__,
        "limit": limit,
        "selected_rows": [item.row for item in selected],
        "selected_supplier_codes": [item.supplier_code for item in selected],
        "products_count": len(proposals),
        "auto_apply": sum(1 for item in proposals if item["enrichment"]["decision"] == "auto_apply"),
        "manual_review": sum(1 for item in proposals if item["enrichment"]["decision"] == "manual_review"),
        "blocked": sum(1 for item in proposals if item["enrichment"]["decision"] == "blocked"),
        "images_downloaded": sum(1 for item in proposals for image in item.get("supplier_images") or [] if image.get("status") == "stored"),
        "warnings": sorted({warning for item in proposals for warning in item["enrichment"]["warnings"]}),
        "proposals": [f"products/{proposal['spreadsheet_row']}-{proposal['supplier_code']}.json" for proposal in proposals],
    }
    atomic_write_json(run_dirs["root"] / "manifest.json", manifest)
    return manifest


def load_enriched_manifest(run_dir: Path) -> dict:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"manifest.json ausente: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if int(manifest.get("products_count") or 0) != 25:
        raise ValueError("run enriquecido deve conter exatamente 25 produtos")
    return manifest


def load_enriched_proposals(run_dir: Path) -> list[dict]:
    manifest = load_enriched_manifest(run_dir)
    proposals = []
    for relative in manifest.get("proposals") or []:
        path = run_dir / relative
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["_proposal_relative_path"] = relative
        proposals.append(payload)
    return proposals


def get_or_create_record(db: Session, run_dir: Path, manifest: dict) -> ImportRecord:
    record = db.query(ImportRecord).filter(ImportRecord.source == ENRICHMENT_SOURCE, ImportRecord.external_reference == manifest["run_id"]).first()
    if record:
        return record
    record = ImportRecord(
        source=ENRICHMENT_SOURCE,
        external_reference=manifest["run_id"],
        status="preview_ready",
        source_type="spreadsheet",
        folder_name=SHEET_NAME,
        started_at=utc_now(),
        finished_at=utc_now(),
        import_metadata={
            "run_id": manifest["run_id"],
            "run_dir": str(run_dir),
            "spreadsheet_id": SPREADSHEET_ID,
            "sheet_name": SHEET_NAME,
            "workbook_sha256": manifest.get("workbook_sha256"),
            "manifest": manifest,
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


def find_existing_product(db: Session, code: str, item: ImportItem | None) -> Product | None:
    if item and item.published_product_id:
        product = db.get(Product, item.published_product_id)
        if product:
            return product
    return db.query(Product).filter(Product.sku == code).first()


def get_or_create_brand(db: Session, name: str, result: EnrichedBatchResult) -> Brand:
    brand = find_brand(db, name)
    if brand:
        result.brands_existing.append({"id": brand.id, "name": brand.name})
        return brand
    brand = Brand(name=name, slug=unique_slug(db, Brand, name), is_active=True)
    db.add(brand)
    db.flush()
    result.brands_created.append({"id": brand.id, "name": brand.name, "slug": brand.slug})
    return brand


def raw_metadata(proposal: dict) -> dict:
    enrichment = proposal["enrichment"]
    return {
        "source": ENRICHMENT_SOURCE,
        "spreadsheet": {"id": SPREADSHEET_ID, "sheet_name": SHEET_NAME, "row": proposal.get("spreadsheet_row")},
        "supplier": {
            "code": proposal.get("supplier_code"),
            "url": proposal.get("supplier_url"),
            "normalized_url": normalize_url(proposal.get("supplier_url") or ""),
            "name_original": proposal.get("supplier_name"),
            "category_original": proposal.get("spreadsheet_category"),
            "price_usd_reference": proposal.get("price_usd_reference"),
            "price_brl_reference": proposal.get("price_brl_reference"),
        },
        "names": {
            "original": proposal.get("supplier_name"),
            "pilot_suggested": proposal.get("suggested_name"),
            "final": enrichment.get("official_name"),
        },
        "brand": {"detected": enrichment.get("detected_brand"), "confidence": enrichment.get("brand_confidence")},
        "category": {
            "slug": proposal.get("category_slug"),
            "name": proposal.get("category_name"),
            "id": enrichment.get("category_id"),
            "confidence": enrichment.get("category_confidence"),
        },
        "images": proposal.get("supplier_images") or [],
        "enrichment": enrichment,
        "review": {
            "status": "review_required" if enrichment.get("decision") == "manual_review" else "auto_applied",
            "needs_name_review": enrichment.get("decision") == "manual_review",
            "brand_conflict": "brand_conflict" in (enrichment.get("warnings") or []),
        },
        "commercial": {"spreadsheet_price_not_imported": True, "price": None},
        "run": {"id": proposal.get("_run_id"), "proposal": proposal.get("_proposal_relative_path")},
    }


def upsert_import_item(
    db: Session,
    record: ImportRecord,
    proposal: dict,
    product: Product | None,
    brand: Brand | None,
    category: Category | None,
    *,
    status: str,
    reason: str | None = None,
) -> tuple[ImportItem, bool]:
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
    item.suggested_name = proposal["enrichment"].get("official_name") or proposal.get("suggested_name")
    item.brand_id = brand.id if brand else None
    item.suggested_category = proposal.get("category_name")
    item.suggested_category_id = category.id if category else None
    item.suggested_model = proposal["enrichment"].get("official_model")
    item.confidence = proposal["enrichment"].get("name_confidence")
    item.classification_confidence = proposal["enrichment"].get("category_confidence")
    item.overall_confidence = min(
        Decimal(str(proposal["enrichment"].get("name_confidence") or 0)),
        Decimal(str(proposal["enrichment"].get("brand_confidence") or 0)),
        Decimal(str(proposal["enrichment"].get("category_confidence") or 0)),
        Decimal(str(proposal["enrichment"].get("image_match_confidence") or 0)),
    )
    item.status = status
    item.image_urls = [image.get("source_url") or image.get("filename") for image in proposal.get("supplier_images") or []]
    item.cover_image_url = item.image_urls[0] if item.image_urls else None
    item.image_count = len(item.image_urls or [])
    item.position = int(proposal.get("spreadsheet_row") or 0)
    item.duplicate_reason = reason
    item.warnings = list(proposal["enrichment"].get("warnings") or [])
    item.classification_evidence = {"category_slug": proposal.get("category_slug"), "category_id": proposal["enrichment"].get("category_id")}
    item.raw_metadata = raw_metadata(proposal)
    if product:
        item.published_product_id = product.id
        item.published_at = item.published_at or utc_now()
        item.publish_metadata = {
            "enriched_spreadsheet_batch": True,
            "created_product_status": product.status,
            "created_product_visibility": product.visibility,
        }
    db.flush()
    return item, created


def create_or_align_product(db: Session, proposal: dict, brand: Brand, category: Category, product: Product | None) -> tuple[Product, bool]:
    name = proposal["enrichment"].get("official_name") or proposal.get("suggested_name") or clean_supplier_title(proposal.get("supplier_name") or "")
    if product is None:
        product = Product(
            public_id=uuid4().hex,
            name=name,
            slug=unique_slug(db, Product, name),
            sku=str(proposal["supplier_code"]),
            short_description="Produto em vitrine temporaria, com detalhes comerciais em revisao.",
            description="Produto selecionado da planilha de fornecedores da DripZone. Preco comercial, estoque e descricao final aguardam curadoria.",
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
            availability="coming_soon",
            ready_to_ship=False,
            status="draft",
            visibility="hidden",
            is_featured=False,
            is_new=True,
            is_best_seller=False,
            main_image_alt=name,
        )
        db.add(product)
        db.flush()
        return product, True
    product.name = name
    product.brand_id = brand.id
    product.category_id = category.id
    product.price = TECHNICAL_PRICE
    product.availability = "coming_soon"
    product.track_inventory = False
    product.stock_quantity = 0
    product.allow_backorder = False
    product.ready_to_ship = False
    product.main_image_alt = name
    if product.status != "published":
        product.status = "draft"
    sync_publication_state(product)
    db.flush()
    return product, False


def validate_public_catalog(data: dict) -> None:
    slugs = [item["slug"] for item in data.get("products") or []]
    if len(slugs) != len(set(slugs)):
        raise RuntimeError("Public catalog has duplicate slugs.")
    for item in data.get("products") or []:
        if item.get("purchasable") and item.get("price") is None:
            raise RuntimeError("Public catalog contains purchasable product without price.")


def apply_enriched_batch(db: Session, run_dir: Path, *, dry_run: bool = False, output_path: Path | None = None) -> EnrichedBatchResult:
    manifest = load_enriched_manifest(run_dir)
    proposals = load_enriched_proposals(run_dir)
    for proposal in proposals:
        proposal["_run_id"] = manifest["run_id"]
    result = EnrichedBatchResult(run_id=manifest["run_id"], dry_run=dry_run, selected=len(proposals))
    result.auto_apply = sum(1 for item in proposals if item["enrichment"]["decision"] == "auto_apply")
    result.manual_review = sum(1 for item in proposals if item["enrichment"]["decision"] == "manual_review")
    result.blocked = sum(1 for item in proposals if item["enrichment"]["decision"] == "blocked")
    output_path = output_path or settings.public_products_file or (PROJECT_ROOT / "frontend" / "data" / "products.json")
    previous_content = output_path.read_bytes() if output_path.exists() else None
    previous_existed = output_path.exists()
    try:
        record = get_or_create_record(db, run_dir, manifest)
        for proposal in sorted(proposals, key=lambda item: int(item.get("spreadsheet_row") or 0)):
            code = str(proposal["supplier_code"])
            decision = proposal["enrichment"]["decision"]
            nested = db.begin_nested()
            try:
                brand = find_brand(db, proposal["enrichment"].get("detected_brand") or "")
                category = category_by_slug(db, proposal.get("category_slug") or "")
                if decision == "blocked":
                    item, created_item = upsert_import_item(db, record, proposal, None, brand, category, status="needs_review", reason="enrichment_blocked")
                    result.import_items_created += int(created_item)
                    result.import_items_existing += int(not created_item)
                    result.items.append({"supplier_code": code, "decision": decision, "import_item_id": item.id, "created": False})
                    nested.commit()
                    continue
                if not category:
                    raise ValueError(f"categoria ausente: {proposal.get('category_slug')}")
                brand = get_or_create_brand(db, proposal["enrichment"]["detected_brand"], result)
                normalized = normalize_url(proposal["supplier_url"])
                item = find_import_item(db, record, code, normalized)
                if not item:
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
                product = find_existing_product(db, code, item)
                product, created_product = create_or_align_product(db, proposal, brand, category, product)
                status = "published" if decision == "auto_apply" else "needs_review"
                item, created_item = upsert_import_item(db, record, proposal, product, brand, category, status=status)
                image_record = sync_product_image(db, item, product, proposal, run_dir, result, dry_run=dry_run)
                if not image_record.id:
                    raise ValueError(f"produto sem imagem principal: {code}")
                if decision == "auto_apply":
                    if not dry_run:
                        db.flush()
                        db.expire(product, ["images"])
                        readiness = evaluate_showcase_readiness(db, product)
                        if readiness["blockers"]:
                            raise ValueError(f"showcase_readiness_failed:{readiness['blockers']}")
                    product.status = "published"
                    product.visibility = "public"
                    product.availability = "coming_soon"
                    product.published_at = product.published_at or utc_now()
                    result.products_published_showcase += 1
                else:
                    product.status = "draft"
                    product.visibility = "hidden"
                    product.availability = "coming_soon"
                    sync_publication_state(product)
                    result.products_draft_hidden += 1
                result.products_created += int(created_product)
                result.products_existing += int(not created_product)
                result.import_items_created += int(created_item)
                result.import_items_existing += int(not created_item)
                result.items.append(
                    {
                        "supplier_code": code,
                        "product_id": product.id,
                        "brand": brand.name,
                        "category": category.slug,
                        "name": product.name,
                        "decision": decision,
                        "created": created_product,
                        "status": product.status,
                        "visibility": product.visibility,
                    }
                )
                nested.commit()
            except Exception as exc:
                nested.rollback()
                result.failed.append({"supplier_code": code, "error": str(exc)})
        record.items_found = len(proposals)
        record.items_needs_review = result.manual_review + result.blocked
        record.items_published = result.products_published_showcase
        record.error_count = len(result.failed)
        record.status = "partial" if result.failed else "published"
        record.finished_at = utc_now()
        if dry_run:
            db.rollback()
            if previous_existed and previous_content is not None:
                write_bytes_atomically(output_path, previous_content)
            elif output_path.exists():
                output_path.unlink()
        else:
            db.flush()
            stage = stage_public_catalog(db, output_path)
            validate_public_catalog(stage.data)
            result.exported_products = len(stage.data.get("products") or [])
            db.commit()
            try:
                publish_public_catalog_stage(stage)
            except Exception:
                cleanup_public_catalog_stage(stage)
                raise
        return result
    except Exception:
        db.rollback()
        if previous_existed and previous_content is not None:
            write_bytes_atomically(output_path, previous_content)
        elif output_path.exists():
            output_path.unlink()
        raise


def manifest_summary(run_dir: Path) -> dict:
    manifest = load_enriched_manifest(run_dir)
    proposals = load_enriched_proposals(run_dir)
    return {
        "manifest": manifest,
        "products": [
            {
                "row": item.get("spreadsheet_row"),
                "supplier_code": item.get("supplier_code"),
                "supplier_name": item.get("supplier_name"),
                "final_name": item.get("enrichment", {}).get("official_name"),
                "brand": item.get("enrichment", {}).get("detected_brand"),
                "category": item.get("category_slug"),
                "decision": item.get("enrichment", {}).get("decision"),
                "warnings": item.get("enrichment", {}).get("warnings") or [],
                "images": [image.get("filename") for image in item.get("supplier_images") or [] if image.get("status") == "stored"],
            }
            for item in proposals
        ],
    }
