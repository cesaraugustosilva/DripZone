from __future__ import annotations

import json
import logging
import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.exceptions import ApiError
from app.services import import_image_ingestion
from app.services.http_security import build_verified_ssl_context
from app.services.import_rules import CATEGORY_RULES, COLOR_RULES, MAX_IMAGES_PER_ITEM, NAME_NOISE_TERMS
from app.services.imports import (
    CandidateItem,
    Fetcher,
    SafeHTTPFetcher,
    category_page_url,
    candidates_from_page,
    detect_yupoo_page_type,
    external_id_from_url,
    extract_yupoo_album_product,
    folder_name_from_url,
    import_scan_metadata,
    item_dedupe_key_for_import,
    new_import_scan_state,
    normalize_product_text,
    normalize_url,
    parse_page,
    queue_discovered_pages,
    unique_scan_candidates,
    validate_source_url,
)
from app.utils.slug import make_slug

logger = logging.getLogger(__name__)

CATALOG_IMPORTER_VERSION = "catalog-importer/1.0"
CATEGORY_CONFIDENCE_THRESHOLD = 0.75
DEFAULT_CATEGORY_SLUG = "desconhecidos"
CATALOG_CATEGORY_NAMES = {
    "camisetas": "Camisetas",
    "calcas": "Calcas",
    "moletons": "Moletons",
    "jaquetas": "Jaquetas",
    "shorts": "Shorts",
    "conjuntos": "Conjuntos",
    "acessorios": "Acessorios",
    "calcados": "Calcados",
    "desconhecidos": "Desconhecidos",
}
CATEGORY_ALIASES = {
    "tenis": "calcados",
    "sneakers": "calcados",
    "shoes": "calcados",
    "bones": "acessorios",
    "bolsas": "acessorios",
}
BAD_NAME_PATTERNS = (
    re.compile(r"^\s*$"),
    re.compile(r"^[a-z]{0,3}\d{3,}[a-z0-9-]*$", re.I),
    re.compile(r"^(new\s+item|item|product|photo|image|img\s*\d*|untitled)$", re.I),
    re.compile(r"^\d+$"),
)
CURRENCY_PREFIX_CHARS = "\uFFE5\u00A5$€£"
LEGACY_MOJIBAKE_CURRENCY_CHARS = (
    "\u00ef\u00bf\u00a5"
    "\u00c2\u00a5"
    "\u00c3\u201a"
    "\u00e2\u201a\u00ac"
    "\u00c2\u00a3"
    "\u00c3\u00af\u00c2\u00bf\u00c2\u00a5"
    "\u00c3\u201a\u00c2\u00a5"
    "\u00c3\u0192\u00e2\u20ac\u0161"
    "\u00c3\u00a2\u00e2\u20ac\u0161\u00c2\u00ac"
    "\u00c3\u201a\u00c2\u00a3"
)
SUPPLIER_PRICE_PREFIX_RE = re.compile(
    rf"^[\s{re.escape(CURRENCY_PREFIX_CHARS + LEGACY_MOJIBAKE_CURRENCY_CHARS)}~.-]*\d+(?:[.,]\d+)?\s*"
)


@dataclass
class CatalogBrand:
    name: str
    slug: str


@dataclass
class CatalogSourceProduct:
    source_url: str
    normalized_source_url: str
    source_id: str
    supplier_name: str
    description: str
    image_urls: list[str]
    page_number: int = 1
    position: int = 1
    raw_metadata: dict = field(default_factory=dict)


@dataclass
class NameAssessment:
    supplier_name: str
    generated_name: str
    final_name: str
    needs_review: bool
    reason: str
    supplier_code: str | None = None
    supplier_metadata: dict = field(default_factory=dict)
    brand_conflict: bool = False
    detected_brands: list[str] = field(default_factory=list)
    unrecognized_brand_tokens: list[str] = field(default_factory=list)
    review_notes: list[str] = field(default_factory=list)


@dataclass
class CategoryAssessment:
    name: str
    slug: str
    confidence: float
    source: str
    reason: str
    needs_review: bool


@dataclass
class ImageAsset:
    filename: str
    position: int
    sha256: str
    mime_type: str
    width: int
    height: int
    source_url: str
    size_bytes: int
    created: bool = True


@dataclass
class ProductImportResult:
    product: CatalogSourceProduct
    destination: Path
    result: str
    product_json: dict | None = None
    images: list[ImageAsset] = field(default_factory=list)
    failed_images: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class DownloadFailure:
    image_url: str
    album_url: str | None
    host: str | None
    attempt: int
    error_type: str
    status_code: int | None
    message: str


class ProductEnrichmentProvider(Protocol):
    def assess_name(self, product: CatalogSourceProduct, brand: CatalogBrand) -> NameAssessment:
        ...

    def classify_category(self, product: CatalogSourceProduct, brand: CatalogBrand) -> CategoryAssessment:
        ...

    def suggest_attributes(self, product: CatalogSourceProduct, brand: CatalogBrand) -> dict:
        ...


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


def normalize_category_slug(value: str | None) -> str:
    slug = make_slug(value or DEFAULT_CATEGORY_SLUG, DEFAULT_CATEGORY_SLUG)
    return CATEGORY_ALIASES.get(slug, slug if slug in CATALOG_CATEGORY_NAMES else DEFAULT_CATEGORY_SLUG)


def catalog_category_name(slug: str) -> str:
    return CATALOG_CATEGORY_NAMES.get(slug, CATALOG_CATEGORY_NAMES[DEFAULT_CATEGORY_SLUG])


def stable_product_id(source_url: str) -> str:
    return external_id_from_url(normalize_url(source_url))


def product_folder_name(final_name: str, source_id: str) -> str:
    return f"{make_slug(final_name, 'produto')}-{source_id[:6]}"


def is_bad_supplier_name(value: str | None) -> bool:
    text = (value or "").strip()
    if any(pattern.match(text) for pattern in BAD_NAME_PATTERNS):
        return True
    normalized = normalize_product_text(text)
    tokens = normalized.split()
    if len(tokens) == 1 and (len(tokens[0]) <= 3 or any(char.isdigit() for char in tokens[0])):
        return True
    if tokens and all(token in {normalize_product_text(item) for item in NAME_NOISE_TERMS} for token in tokens):
        return True
    return False


def display_case(value: str) -> str:
    keep_upper = {"ch", "bk", "ss", "fw", "sp5der"}
    words = []
    for word in re.split(r"\s+", value.strip()):
        clean = word.strip()
        if not clean:
            continue
        if clean.casefold() == "e":
            words.append("e")
            continue
        if clean.casefold() in keep_upper or clean.isupper():
            words.append(clean.upper())
        else:
            words.append(clean[0].upper() + clean[1:])
    return " ".join(words)


BRAND_PATTERNS = {
    "Adidas": {"adidas", "adi das", "dias", "di as", "adi", "a didas"},
    "Gucci": {"gucci", "guci", "gci", "g ci", "g c i"},
}
PRODUCT_TYPE_LABELS = {
    "jacket trousers": "Jacket and Trousers Set",
    "jacket pants": "Jacket and Pants Set",
    "jacket and trousers": "Jacket and Trousers Set",
    "jacket and pants": "Jacket and Pants Set",
    "hoodie": "Hoodie",
    "sweater": "Sweater",
    "sweatshirt": "Sweatshirt",
    "pullover": "Pullover",
    "crewneck": "Crewneck",
    "t-shirt": "T-Shirt",
    "t shirt": "T-Shirt",
    "tee": "T-Shirt",
    "trousers": "Trousers",
    "pants": "Pants",
    "shorts": "Shorts",
    "jacket": "Jacket",
    "jewelry": "Jewelry",
    "jewellery": "Jewelry",
    "necklace": "Necklace",
    "bracelet": "Bracelet",
    "ring": "Ring",
    "belt": "Belt",
    "bag": "Bag",
    "cap": "Cap",
    "hat": "Hat",
    "beanie": "Beanie",
}

AUDIENCE_TERMS = {
    "woman": "female",
    "women": "female",
    "womens": "female",
    "women's": "female",
    "female": "female",
    "ladies": "female",
}

UNRECOGNIZED_BRAND_EXCLUDED_TOKENS = {
    *{normalize_product_text(term) for term in PRODUCT_TYPE_LABELS},
    *{normalize_product_text(term) for term in AUDIENCE_TERMS},
    "and",
    "set",
    "piece",
    "pieces",
    "the",
    "with",
    "for",
    "new",
}


def normalize_censored_text(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", " ", value or "")
    text = re.sub(r"([A-Za-z])(?=\d)", r"\1 ", text)
    text = re.sub(r"(?<=\d)([A-Za-z])", r" \1", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def extract_supplier_metadata(value: str) -> dict:
    metadata: dict = {}
    normalized = normalize_censored_text(value or "")
    height = re.search(r"\b(?:im\s*)?(\d{2,3})\s*cm\b", value or "", flags=re.I)
    weight = re.search(r"\b(\d{2,3})\s*kg\b", value or "", flags=re.I)
    size = re.search(r"\b(?:iwear|i\s*wear|model\s*wears?|wearing)\s+size\s+([A-Za-z0-9]+)\b", value or "", flags=re.I)
    if height:
        metadata["model_height_cm"] = int(height.group(1))
    if weight:
        metadata["model_weight_kg"] = int(weight.group(1))
    if size:
        metadata["model_wearing_size"] = size.group(1).upper()
    if any(f" {normalize_censored_text(term)} " in f" {normalized} " for term in AUDIENCE_TERMS):
        metadata["audience"] = "female"
    return metadata


def extract_supplier_code(value: str) -> str | None:
    matches = re.findall(r"(?<!\d)(\d{6,})(?!\d)", value or "")
    return matches[-1] if matches else None


def remove_supplier_noise(value: str) -> str:
    text = value or ""
    text = SUPPLIER_PRICE_PREFIX_RE.sub(" ", text)
    text = re.sub(r"\([^)]*(?:cm|kg|iwear|i\s*wear|model wears|size reference|in the photo)[^)]*\)", " ", text, flags=re.I)
    text = re.sub(r"\b(?:im\s*)?\d{2,3}\s*cm\b", " ", text, flags=re.I)
    text = re.sub(r"\b\d{2,3}\s*kg\b", " ", text, flags=re.I)
    text = re.sub(r"\b(?:iwear|i\s*wear|model\s*wears?|wearing)\s+size\s+[A-Za-z0-9]+\b", " ", text, flags=re.I)
    text = re.sub(r"\b(?:woman|women|women's|female|ladies)\b", " ", text, flags=re.I)
    text = re.sub(r"\bin the photo\b|\bsize reference\b", " ", text, flags=re.I)
    text = re.sub(r"(?<=[A-Za-z])(?=\d{6,}\b)", " ", text)
    text = re.sub(r"\b\d{6,}\b", " ", text)
    text = re.sub(r"[^\w\s&+-]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip(" -_&+")


def detect_censored_brands(value: str, selected_brand: CatalogBrand | None = None) -> list[str]:
    normalized = normalize_censored_text(value)
    detected_with_positions: list[tuple[int, str]] = []
    for brand, patterns in BRAND_PATTERNS.items():
        positions = []
        for pattern in patterns:
            match = re.search(rf"(?<!\w){re.escape(pattern)}(?!\w)", normalized)
            if match:
                positions.append(match.start())
        if positions:
            detected_with_positions.append((min(positions), brand))
    detected = [brand for _, brand in sorted(detected_with_positions)]
    if selected_brand and normalize_product_text(selected_brand.name) in {normalize_product_text(item) for item in detected}:
        detected = [selected_brand.name if normalize_product_text(item) == normalize_product_text(selected_brand.name) else item for item in detected]
    return list(dict.fromkeys(detected))


def has_term(value: str, term: str) -> bool:
    return f" {normalize_product_text(term)} " in f" {normalize_product_text(value)} "


def has_jacket_trousers_set(value: str) -> bool:
    normalized = normalize_product_text(re.sub(r"(?<=[A-Za-z])(?=\d{6,}\b)", " ", value or ""))
    has_jacket = has_term(normalized, "jacket")
    has_bottom = any(has_term(normalized, term) for term in ["trousers", "pants"])
    return has_jacket and has_bottom


def extract_unrecognized_brand_tokens(value: str, detected_brands: list[str]) -> list[str]:
    text = value or ""
    if "&" not in text:
        return []
    known = {normalize_product_text(brand) for brand in detected_brands}
    unknown: list[str] = []
    segments = re.split(r"&", text)
    for segment in segments:
        if detect_censored_brands(segment):
            continue
        segment = SUPPLIER_PRICE_PREFIX_RE.sub(" ", segment)
        segment = re.sub(r"\b\d{6,}\b", " ", segment)
        for raw_token in re.findall(r"\S+", segment):
            token = raw_token.strip(" -_.,:;()[]{}")
            if not re.search(r"[A-Za-z]", token):
                continue
            normalized = normalize_censored_text(token)
            if not normalized or normalized in known:
                continue
            if normalized in UNRECOGNIZED_BRAND_EXCLUDED_TOKENS:
                continue
            looks_censored = bool(re.search(r"[^A-Za-z0-9'’.-]", token))
            looks_brand_like = token.isupper() and 1 <= len(re.sub(r"[^A-Za-z0-9]", "", token)) <= 6
            if looks_censored or looks_brand_like:
                unknown.append(token)
                break
    return list(dict.fromkeys(unknown))


def extract_product_terms(value: str) -> list[str]:
    normalized = normalize_censored_text(value)
    if has_jacket_trousers_set(value):
        if has_term(normalized, "trousers"):
            return ["Jacket and Trousers Set"]
        return ["Jacket and Pants Set"]
    terms: list[str] = []
    for term, label in PRODUCT_TYPE_LABELS.items():
        if f" {term} " in f" {normalized} ":
            terms.append(label)
    return list(dict.fromkeys(terms))


def improve_name(supplier_name: str, brand: CatalogBrand) -> str:
    text = remove_supplier_noise(supplier_name)
    color = detect_color(text)
    detected_brands = detect_censored_brands(text, brand)
    product_terms = extract_product_terms(text)
    if detected_brands:
        brand_part = " e ".join(detected_brands or [brand.name])
        name = " ".join([brand_part, *product_terms]).strip()
        if color:
            name = f"{name} {color}"
        return display_case(name)[:300] or brand.name
    text = re.sub(r"[_/|]+", " ", text or "")
    text = re.sub(r"\b(24ss|25ss|fw\d{2}|ss\d{2}|a\d{3,}|nk[- ]?\w+|bk)\b", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" -_.")
    if brand.name.casefold() == "chrome hearts" and normalize_product_text(text).startswith("ch "):
        text = f"Chrome Hearts {text[3:]}"
    if normalize_product_text(brand.name) not in normalize_product_text(text):
        text = f"{brand.name} {text}".strip()
    if color and color not in text:
        text = f"{text} {color}"
    return display_case(text)[:300] or brand.name


def detect_color(text: str) -> str | None:
    normalized = normalize_product_text(text)
    color_labels = {
        "Black": "Preta",
        "White": "Branca",
        "Grey": "Cinza",
        "Blue": "Azul",
        "Red": "Vermelha",
        "Green": "Verde",
        "Brown": "Marrom",
        "Beige": "Bege",
    }
    for color, terms in COLOR_RULES.items():
        if any(f" {normalize_product_text(term)} " in f" {normalized} " for term in terms):
            return color_labels.get(color, color)
    if " bk " in f" {normalized} ":
        return "Preta"
    return None


class DeterministicProductEnrichmentProvider:
    def assess_name(self, product: CatalogSourceProduct, brand: CatalogBrand) -> NameAssessment:
        bad = is_bad_supplier_name(product.supplier_name)
        supplier_code = extract_supplier_code(product.supplier_name)
        supplier_metadata = extract_supplier_metadata(product.supplier_name)
        detected_brands = detect_censored_brands(product.supplier_name, brand)
        unrecognized_brand_tokens = extract_unrecognized_brand_tokens(product.supplier_name, detected_brands)
        brand_conflict = len(detected_brands) > 1 or bool(unrecognized_brand_tokens)
        generated = improve_name(product.supplier_name or folder_name_from_url(product.source_url), brand)
        final = generated if bad else improve_name(product.supplier_name, brand)
        review_notes = []
        if brand_conflict:
            review_notes.append("O titulo contem mais de uma marca.")
        if unrecognized_brand_tokens:
            review_notes.append("O titulo pode conter outra marca nao reconhecida: " + ", ".join(unrecognized_brand_tokens) + ".")
        return NameAssessment(
            supplier_name=product.supplier_name,
            generated_name=generated,
            final_name=final,
            needs_review=bad or brand_conflict,
            reason="supplier_name_bad" if bad else "supplier_title_cleaned",
            supplier_code=supplier_code,
            supplier_metadata=supplier_metadata,
            brand_conflict=brand_conflict,
            detected_brands=detected_brands,
            unrecognized_brand_tokens=unrecognized_brand_tokens,
            review_notes=review_notes,
        )

    def classify_category(self, product: CatalogSourceProduct, brand: CatalogBrand) -> CategoryAssessment:
        text_by_source = {
            "title": product.supplier_name,
            "description": product.description,
            "folder_name": str(product.raw_metadata.get("folder_name", "")),
            "item_slug": folder_name_from_url(product.normalized_source_url),
            "image_alt": " ".join(product.raw_metadata.get("image_alts", [])),
        }
        combined_raw = " ".join(text_by_source.values())
        if has_jacket_trousers_set(product.supplier_name):
            return CategoryAssessment("Conjuntos", "conjuntos", 0.95, "deterministic_rules", "O titulo contem termos explicitos de duas pecas complementares: jacket e trousers.", False)
        combined = normalize_product_text(combined_raw)
        separated = normalize_product_text(re.sub(r"(?<=[A-Za-z])(?=\d{6,}\b)", " ", combined_raw))
        matches: list[tuple[str, list[str], list[str]]] = []
        for category, terms in CATEGORY_RULES.items():
            found = []
            sources = []
            for term in terms:
                normalized_term = normalize_product_text(term)
                if f" {normalized_term} " in f" {combined} " or f" {normalized_term} " in f" {separated} ":
                    found.append(term)
                    for source, value in text_by_source.items():
                        if f" {normalized_term} " in f" {normalize_product_text(value)} ":
                            sources.append(source)
            if found:
                matches.append((category, found, list(dict.fromkeys(sources))))
        if not matches:
            return CategoryAssessment(catalog_category_name(DEFAULT_CATEGORY_SLUG), DEFAULT_CATEGORY_SLUG, 0.0, "rules", "Nenhuma regra deterministica encontrou categoria.", True)
        matches.sort(key=lambda item: (len(item[1]), max(len(term) for term in item[1])), reverse=True)
        category, found_terms, sources = matches[0]
        explicit_terms = {"hoodie", "sweater", "sweatshirt", "pullover", "crewneck", "jewelry", "jewellery", "necklace", "bracelet", "ring", "jacket", "shorts", "trousers", "pants", "t-shirt"}
        has_explicit = any(normalize_product_text(term) in explicit_terms for term in found_terms)
        confidence = 0.95 if has_explicit else min(0.97, 0.58 + 0.13 * len(found_terms) + 0.08 * int("title" in sources))
        conflicts = [item[0] for item in matches[1:] if len(item[1]) == len(found_terms)]
        if conflicts:
            confidence = min(confidence, 0.68)
        slug = normalize_category_slug(category)
        if confidence < CATEGORY_CONFIDENCE_THRESHOLD:
            return CategoryAssessment(catalog_category_name(DEFAULT_CATEGORY_SLUG), DEFAULT_CATEGORY_SLUG, round(confidence, 2), "rules", f"Baixa confianca para {category}: {', '.join(found_terms)}.", True)
        reason = f"O titulo contem o termo explicito '{found_terms[0]}'." if has_explicit else f"Texto contem {', '.join(found_terms[:4])}."
        return CategoryAssessment(catalog_category_name(slug), slug, round(confidence, 2), "deterministic_rules", reason, False)

    def suggest_attributes(self, product: CatalogSourceProduct, brand: CatalogBrand) -> dict:
        return {"color": detect_color(product.supplier_name), "style": None, "fit": None, "gender": None, "material": None}


class CatalogYupooScanner:
    def __init__(self, fetcher: Fetcher | None = None, *, max_pages: int | None = None, max_products: int | None = None, start_page: int = 1):
        self.fetcher = fetcher or SafeHTTPFetcher()
        self.max_pages = max_pages or settings.import_max_pages
        self.max_products = max_products or settings.import_max_items
        self.start_page = max(1, start_page)
        self.last_scan_stats = {"albums_found_before_dedupe": 0, "albums_valid": 0, "albums_duplicates_removed": 0, "products_to_process": 0, "truncated": False, "pagination_truncated": False}

    def scan(self, folder_url: str) -> list[CatalogSourceProduct]:
        root_url = validate_source_url(folder_url)
        start_url = category_page_url(root_url, self.start_page)
        scan_state = new_import_scan_state(start_url)
        products: list[CatalogSourceProduct] = []
        while scan_state.pages_to_visit and len(scan_state.visited_pages) < self.max_pages and len(products) < self.max_products:
            page_url = scan_state.pages_to_visit.pop(0)
            if page_url in scan_state.visited_pages:
                continue
            scan_state.visited_pages.add(page_url)
            scan_state.pages_read = len(scan_state.visited_pages)
            scan_state.last_page_processed = page_url
            page = self.fetcher.get(page_url)
            candidates, counters, next_pages = candidates_from_page(root_url, page.url, page.body, len(scan_state.visited_pages))
            unique_candidates = unique_scan_candidates(scan_state, candidates, source="folder_preview", source_type="yupoo" if candidates and candidates[0].raw_metadata.get("page_type") == "category_page" else "folder")
            for key in ["albums_found_before_dedupe", "albums_valid", "albums_duplicates_removed"]:
                self.last_scan_stats[key] += int(counters.get(key, 0) or 0)
            is_yupoo_category = bool(candidates) and candidates[0].raw_metadata.get("page_type") == "category_page"
            queue_discovered_pages(scan_state, root_url, page.url, next_pages, saw_candidates=bool(candidates), max_pages=self.max_pages, auto_increment=is_yupoo_category)
            for candidate in unique_candidates:
                if len(products) >= self.max_products:
                    scan_state.truncated = True
                    scan_state.limit_reason = scan_state.limit_reason or "max_items"
                    break
                normalized = normalize_url(candidate.source_url)
                products.append(self._open_product(candidate, root_url))
                scan_state.processed_items += 1
        if scan_state.pages_to_visit and len(scan_state.visited_pages) >= self.max_pages:
            scan_state.pagination_truncated = True
            scan_state.limit_reason = scan_state.limit_reason or "max_pages"
        if len(products) >= self.max_products and (scan_state.unique_items_found > scan_state.processed_items or scan_state.pages_to_visit):
            scan_state.truncated = True
            scan_state.limit_reason = scan_state.limit_reason or "max_items"
        self.last_scan_stats["products_to_process"] = len(products)
        self.last_scan_stats["scan"] = import_scan_metadata(scan_state, max_pages=self.max_pages, max_items=self.max_products)
        self.last_scan_stats["truncated"] = scan_state.truncated
        self.last_scan_stats["pagination_truncated"] = scan_state.pagination_truncated
        return products

    def _open_product(self, candidate: CandidateItem, root_url: str) -> CatalogSourceProduct:
        normalized = normalize_url(candidate.source_url)
        title = candidate.title
        image_urls = list(candidate.image_urls)
        description = ""
        image_alts = candidate.raw_metadata.get("image_alts", [])
        if normalized != root_url:
            try:
                page = self.fetcher.get(normalized)
                if detect_yupoo_page_type(page.url, page.body) == "album_page":
                    album = extract_yupoo_album_product(
                        page.url,
                        page.body,
                        fallback_title=candidate.title,
                        category_title=str(candidate.raw_metadata.get("page_title", "")),
                    )
                    title = album.title
                    description = album.description
                    image_urls = album.image_urls or image_urls
                    image_alts = album.image_alts
                else:
                    page_title, _, images = parse_page(page.url, page.body)
                    if page_title:
                        title = page_title
                    image_urls = [image["src"] for image in images if image.get("src")][:MAX_IMAGES_PER_ITEM] or image_urls
                    image_alts = [image.get("alt", "") for image in images]
            except ApiError:
                logger.info("catalog_product_page_unavailable", extra={"source_id": stable_product_id(normalized)})
        return CatalogSourceProduct(
            source_url=candidate.source_url,
            normalized_source_url=normalized,
            source_id=stable_product_id(normalized),
            supplier_name=title or folder_name_from_url(normalized),
            description=description,
            image_urls=list(dict.fromkeys(image_urls))[:MAX_IMAGES_PER_ITEM],
            page_number=candidate.page_number,
            position=candidate.position,
            raw_metadata={**candidate.raw_metadata, "folder_name": folder_name_from_url(root_url), "image_alts": image_alts},
        )


def validate_existing_image(path: Path, expected_sha256: str | None = None) -> ImageAsset | None:
    if not path.is_file():
        return None
    try:
        mime, width, height, _ = import_image_ingestion.validate_downloaded_image(path, None)
    except ApiError:
        return None
    hasher = import_image_ingestion.hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(import_image_ingestion.READ_CHUNK_SIZE), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    if expected_sha256 and digest != expected_sha256:
        return None
    return ImageAsset(path.name, 0, digest, mime, width, height, "", path.stat().st_size, created=False)


class CatalogImageDownloader:
    def __init__(self, client_factory=None):
        self.client_factory = client_factory

    def download_images(self, image_urls: list[str], product_dir: Path, existing_product: dict | None, *, force: bool = False, album_url: str | None = None) -> tuple[list[ImageAsset], list[dict]]:
        assets: list[ImageAsset] = []
        failures: list[dict] = []
        previous_by_url = {item.get("source_url"): item for item in (existing_product or {}).get("images", {}).get("items", [])}
        product_dir.mkdir(parents=True, exist_ok=True)
        timeout = httpx.Timeout(connect=settings.import_image_connect_timeout, read=settings.import_image_read_timeout, write=settings.import_image_read_timeout, pool=settings.import_image_connect_timeout)
        factory = self.client_factory or (lambda: httpx.Client(timeout=timeout, follow_redirects=False, verify=build_verified_ssl_context()))
        with factory() as client:
            for position, source_url in enumerate(image_urls):
                previous = previous_by_url.get(source_url)
                if previous and not force:
                    path = product_dir / previous.get("filename", "")
                    existing = validate_existing_image(path, previous.get("sha256"))
                    if existing:
                        existing.position = position
                        existing.source_url = source_url
                        assets.append(existing)
                        continue
                try:
                    temp_path, content_hash, header_mime, size_bytes = import_image_ingestion.download_with_retries(client, source_url, product_dir, referer=album_url, yupoo_media_only=True)
                    mime, width, height, _ = import_image_ingestion.validate_downloaded_image(temp_path, header_mime)
                    extension = import_image_ingestion.ALLOWED_EXTENSIONS[mime]
                    filename = f"cover.{extension}" if position == 0 else f"{position:02d}.{extension}"
                    final_path = product_dir / filename
                    if final_path.exists():
                        final_path.unlink()
                    shutil.move(str(temp_path), final_path)
                    assets.append(ImageAsset(filename, position, content_hash, mime, width, height, source_url, size_bytes, created=True))
                except ApiError as exc:
                    failures.append(download_failure(source_url, album_url, exc, position + 1))
                except (httpx.HTTPError, OSError) as exc:
                    failures.append(download_failure(source_url, album_url, exc, position + 1))
        return assets, failures


class CatalogImporter:
    def __init__(
        self,
        *,
        catalog_path: Path,
        scanner: CatalogYupooScanner | None = None,
        enrichment_provider: ProductEnrichmentProvider | None = None,
        downloader: CatalogImageDownloader | None = None,
    ):
        self.catalog_path = Path(catalog_path)
        self.scanner = scanner or CatalogYupooScanner()
        self.enrichment_provider = enrichment_provider or DeterministicProductEnrichmentProvider()
        self.downloader = downloader or CatalogImageDownloader()

    def run(self, *, brand: CatalogBrand, folder_url: str, dry_run: bool = False, force: bool = False, max_products: int | None = None, max_pages: int | None = None, start_page: int | None = None) -> dict:
        started_at = utc_iso()
        start = time.monotonic()
        run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{brand.slug}-{external_id_from_url(folder_url)[:8]}"
        if max_products:
            self.scanner.max_products = max_products
        if max_pages:
            self.scanner.max_pages = max_pages
        if start_page:
            self.scanner.start_page = max(1, start_page)
        products = self.scanner.scan(folder_url)
        results: list[ProductImportResult] = []
        for product in products:
            try:
                results.append(self._process_product(brand, folder_url, product, dry_run=dry_run, force=force))
            except Exception as exc:
                results.append(ProductImportResult(product, self.catalog_path / brand.slug, "error", error=str(exc)))
        self._mark_duplicate_commercial_names(results, dry_run=dry_run)
        finished_at = utc_iso()
        manifest = self._build_manifest(run_id, brand, folder_url, started_at, finished_at, time.monotonic() - start, results, dry_run)
        if not dry_run:
            runs_dir = self.catalog_path / "_runs"
            atomic_write_json(runs_dir / f"{run_id}.json", manifest)
            (runs_dir / f"{run_id}.log").write_text(self._build_log(manifest, results), encoding="utf-8")
            self._write_brand_metadata(brand, folder_url, started_at, finished_at, results)
        return manifest

    def _process_product(self, brand: CatalogBrand, folder_url: str, product: CatalogSourceProduct, *, dry_run: bool, force: bool) -> ProductImportResult:
        name = self.enrichment_provider.assess_name(product, brand)
        category = self.enrichment_provider.classify_category(product, brand)
        attributes = self.enrichment_provider.suggest_attributes(product, brand)
        destination = self.catalog_path / brand.slug / category.slug / product_folder_name(name.final_name, product.source_id)
        if dry_run:
            product_json = self._build_product_json(brand, folder_url, product, name, category, attributes, [], [])
            return ProductImportResult(product, destination, "dry_run", product_json=product_json, warnings=[name.reason, category.reason])
        existing = self._find_existing_product(brand.slug, product.source_id)
        if existing:
            destination = existing[0]
        existing_json = existing[1] if existing else None
        destination.mkdir(parents=True, exist_ok=True)
        images, failed_images = self.downloader.download_images(product.image_urls, destination, existing_json, force=force, album_url=product.normalized_source_url)
        result = self._result_for_product(existing_json, product, images, failed_images, force, name, category)
        product_json = self._build_product_json(brand, folder_url, product, name, category, attributes, images, failed_images)
        if result != "skipped" or force:
            atomic_write_json(destination / "product.json", product_json)
        return ProductImportResult(product, destination, result, product_json, images, failed_images, warnings=[name.reason] if name.needs_review else [])

    def _result_for_product(self, existing_json: dict | None, product: CatalogSourceProduct, images: list[ImageAsset], failed_images: list[dict], force: bool, name: NameAssessment, category: CategoryAssessment) -> str:
        if product.image_urls and not images:
            return "failed"
        if failed_images:
            return "partial"
        if not existing_json:
            return "created"
        if force or self._product_changed(existing_json, name, category, product, images):
            return "updated"
        return "skipped"

    def _mark_duplicate_commercial_names(self, results: list[ProductImportResult], *, dry_run: bool) -> None:
        by_key: dict[str, list[ProductImportResult]] = {}
        for result in results:
            if result.product_json:
                by_key.setdefault(normalize_product_text(result.product_json.get("final_name")), []).append(result)
        note = "Nome comercial coincide com outro produto da mesma origem e requer diferenciacao manual."
        for items in by_key.values():
            if len(items) < 2:
                continue
            for result in items:
                review = result.product_json.setdefault("review", {})
                review["needs_name_review"] = True
                review["notes"] = list(dict.fromkeys([*(review.get("notes") or []), note]))
                if "duplicate_commercial_name" not in result.warnings:
                    result.warnings.append("duplicate_commercial_name")
                if not dry_run and result.destination.exists() and result.result in {"created", "updated"}:
                    atomic_write_json(result.destination / "product.json", result.product_json)

    def _find_existing_product(self, brand_slug: str, source_id: str) -> tuple[Path, dict] | None:
        brand_dir = self.catalog_path / brand_slug
        if not brand_dir.exists():
            return None
        for path in brand_dir.glob("*/*/product.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("id") == source_id or payload.get("source", {}).get("source_id") == source_id:
                return path.parent, payload
        return None

    def _product_changed(self, existing: dict, name: NameAssessment, category: CategoryAssessment, product: CatalogSourceProduct, images: list[ImageAsset]) -> bool:
        return (
            existing.get("final_name") != name.final_name
            or existing.get("category", {}).get("slug") != category.slug
            or len(existing.get("images", {}).get("items", [])) != len(images)
            or existing.get("source", {}).get("product_url") != product.normalized_source_url
        )

    def _build_product_json(
        self,
        brand: CatalogBrand,
        folder_url: str,
        product: CatalogSourceProduct,
        name: NameAssessment,
        category: CategoryAssessment,
        attributes: dict,
        images: list[ImageAsset],
        failed_images: list[dict],
    ) -> dict:
        image_items = [
            {
                "filename": asset.filename,
                "position": asset.position,
                "sha256": asset.sha256,
                "mime_type": asset.mime_type,
                "width": asset.width,
                "height": asset.height,
                "source_url": asset.source_url,
            }
            for asset in images
        ]
        notes = [failure["error"] for failure in failed_images]
        import_status = "created"
        if product.image_urls and not images:
            import_status = "failed"
        elif failed_images:
            import_status = "partial"
        return {
            "schema_version": 1,
            "id": product.source_id,
            "supplier_name": name.supplier_name,
            "supplier_code": name.supplier_code,
            "generated_name": name.generated_name,
            "final_name": name.final_name,
            "slug": make_slug(name.final_name, "produto"),
            "brand": {"name": brand.name, "slug": brand.slug},
            "category": {
                "name": category.name,
                "slug": category.slug,
                "confidence": category.confidence,
                "source": category.source,
                "reason": category.reason,
            },
            "description": {"supplier": product.description, "generated": "", "final": product.description},
            "attributes": attributes,
            "supplier_metadata": name.supplier_metadata,
            "sizes": [],
            "tags": [],
            "images": {"cover": images[0].filename if images else None, "items": image_items},
            "import": {
                "status": import_status,
                "errors": failed_images,
                "images_found": len(product.image_urls),
                "images_downloaded": len(images),
                "images_failed": len(failed_images),
            },
            "source": {
                "provider": "yupoo",
                "folder_url": normalize_url(folder_url),
                "product_url": product.normalized_source_url,
                "source_id": product.source_id,
                "imported_at": utc_iso(),
            },
            "review": {
                "status": "pending",
                "needs_name_review": name.needs_review,
                "needs_category_review": category.needs_review,
                "brand_conflict": name.brand_conflict,
                "detected_brands": name.detected_brands,
                "unrecognized_brand_tokens": name.unrecognized_brand_tokens,
                "notes": list(dict.fromkeys(name.review_notes)),
            },
        }

    def _build_manifest(self, run_id: str, brand: CatalogBrand, folder_url: str, started_at: str, finished_at: str, duration: float, results: list[ProductImportResult], dry_run: bool) -> dict:
        return {
            "schema_version": 1,
            "run_id": run_id,
            "importer_version": CATALOG_IMPORTER_VERSION,
            "dry_run": dry_run,
            "brand": {"name": brand.name, "slug": brand.slug},
            "source": {"provider": "yupoo", "folder_url": normalize_url(folder_url)},
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_seconds": round(duration, 3),
            "scan": getattr(self.scanner, "last_scan_stats", {}),
            "products_found": len(results),
            "products_created": sum(item.result == "created" for item in results),
            "products_updated": sum(item.result == "updated" for item in results),
            "products_skipped": sum(item.result in {"skipped", "dry_run"} for item in results),
            "products_partial": sum(item.result == "partial" for item in results),
            "products_failed": sum(item.result == "error" for item in results),
            "products_with_error": sum(item.result in {"failed", "error"} for item in results),
            "images_found": sum(len(item.product.image_urls) for item in results),
            "downloaded_images": sum(asset.created for item in results for asset in item.images),
            "failed_images": sum(len(item.failed_images) for item in results),
            "unknown_products": sum(1 for item in results if item.product_json and item.product_json["category"]["slug"] == DEFAULT_CATEGORY_SLUG),
            "name_review_products": sum(1 for item in results if item.product_json and item.product_json["review"]["needs_name_review"]),
            "warnings": list(
                dict.fromkeys(
                    [warning for item in results for warning in item.warnings]
                    + (["possible_brand_divergence"] if possible_brand_divergence(brand, [item.product for item in results]) else [])
                )
            ),
            "items": [
                {
                    "source_id": item.product.source_id,
                    "source_url": item.product.normalized_source_url,
                    "supplier_name": item.product.supplier_name,
                    "supplier_code": item.product_json.get("supplier_code") if item.product_json else None,
                    "final_name": item.product_json.get("final_name") if item.product_json else None,
                    "category": item.product_json.get("category") if item.product_json else None,
                    "review": item.product_json.get("review") if item.product_json else None,
                    "import": item.product_json.get("import") if item.product_json else None,
                    "images": len(item.images),
                    "source_images": len(item.product.image_urls),
                    "result": item.result,
                    "destination": str(item.destination.relative_to(self.catalog_path)) if item.destination.is_relative_to(self.catalog_path) else str(item.destination),
                    "error": item.error,
                }
                for item in results
            ],
        }

    def _write_brand_metadata(self, brand: CatalogBrand, folder_url: str, started_at: str, finished_at: str, results: list[ProductImportResult]) -> None:
        brand_dir = self.catalog_path / brand.slug
        by_category: dict[str, int] = {}
        total = 0
        for product_json in brand_dir.glob("*/*/product.json"):
            try:
                payload = json.loads(product_json.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("import", {}).get("status") == "failed":
                continue
            total += 1
            slug = payload.get("category", {}).get("slug", DEFAULT_CATEGORY_SLUG)
            by_category[slug] = by_category.get(slug, 0) + 1
        metadata = {
            "schema_version": 1,
            "brand": {"name": brand.name, "slug": brand.slug},
            "sources": [{"provider": "yupoo", "folder_url": normalize_url(folder_url), "last_imported_at": finished_at}],
            "stats": {"total_products": total, "by_category": by_category},
            "last_import": {
                "started_at": started_at,
                "finished_at": finished_at,
                "successful_products": sum(item.result in {"created", "updated", "skipped"} for item in results),
                "failed_products": sum(item.result in {"failed", "error"} for item in results),
                "downloaded_images": sum(asset.created for item in results for asset in item.images),
                "failed_images": sum(len(item.failed_images) for item in results),
            },
        }
        atomic_write_json(brand_dir / "_metadata.json", metadata)

    def _build_log(self, manifest: dict, results: list[ProductImportResult]) -> str:
        lines = [
            "Importacao DripZone",
            f"Run: {manifest['run_id']}",
            f"Marca: {manifest['brand']['name']}",
            f"Origem: {manifest['source']['folder_url']}",
            "",
        ]
        for index, item in enumerate(results, start=1):
            lines.append(f"[{index}/{len(results)}] {item.product.supplier_name}")
            lines.append(f"  Resultado: {item.result}")
            lines.append(f"  Destino: {item.destination}")
            if item.error:
                lines.append(f"  Erro: {item.error}")
        return "\n".join(lines) + "\n"


def possible_brand_divergence(brand: CatalogBrand, products: list[CatalogSourceProduct]) -> bool:
    if not products:
        return False
    brand_tokens = [token for token in normalize_product_text(brand.name).split() if len(token) >= 3]
    if not brand_tokens:
        return False
    sample = normalize_product_text(" ".join(product.supplier_name for product in products[:10]))
    return not any(token in sample for token in brand_tokens)


def download_failure(source_url: str, album_url: str | None, exc: Exception, attempt: int) -> dict:
    parsed = urlparse(source_url)
    if isinstance(exc, ApiError):
        details = exc.details if isinstance(exc.details, dict) else {}
        error_type = details.get("blocker") or exc.code
        status_code = details.get("status_code")
        message = exc.message
    else:
        error_type = "download_failed"
        status_code = None
        message = str(exc)[:300] or "Falha ao baixar imagem."
    return {
        "image_url": source_url,
        "album_url": album_url,
        "host": parsed.hostname,
        "attempt": attempt,
        "error_type": error_type,
        "status_code": status_code,
        "message": message,
        "error": error_type,
    }
