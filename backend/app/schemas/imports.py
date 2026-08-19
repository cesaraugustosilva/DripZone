from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.schemas.common import ORMModel
from app.schemas.resources import BrandRead

ImportStatus = Literal["draft", "scanning", "preview_ready", "failed", "cancelled"]
ImportItemStatus = Literal["pending", "duplicate", "needs_review", "invalid", "reviewed", "approved", "publishing", "published", "publish_failed"]
ImportImageStatus = Literal["active", "ignored", "duplicate", "invalid"]
ImportImageIngestionStatus = Literal["not_requested", "downloading", "validating", "stored", "failed", "skipped"]


class ImportPreviewCreate(BaseModel):
    brand_id: int | None = None
    brand: str | None = Field(default=None, min_length=1, max_length=120)
    source_url: HttpUrl


class ImportItemRead(ORMModel):
    id: int
    import_record_id: int
    external_id: str | None
    source_url: str | None
    normalized_source_url: str | None
    source_title: str | None
    suggested_name: str | None
    brand_id: int | None
    suggested_category: str | None
    suggested_category_id: int | None
    suggested_model: str | None
    suggested_color: str | None
    suggested_color_normalized: str | None
    confidence: Decimal | None
    classification_confidence: Decimal | None
    model_confidence: Decimal | None
    color_confidence: Decimal | None
    grouping_confidence: Decimal | None
    overall_confidence: Decimal | None
    status: ImportItemStatus
    image_urls: list[str] | None
    cover_image_url: str | None
    image_count: int
    page_number: int | None
    position: int
    duplicate_reason: str | None
    warnings: list[str] | None
    classification_evidence: dict | None
    model_evidence: dict | None
    color_evidence: dict | None
    grouping_evidence: dict | None
    raw_metadata: dict | None
    reviewed_by_id: int | None
    reviewed_at: datetime | None
    approved_by_id: int | None
    approved_at: datetime | None
    published_by_id: int | None
    published_at: datetime | None
    published_product_id: int | None
    publish_attempts: int
    publish_error: str | None
    publish_metadata: dict | None
    created_at: datetime
    updated_at: datetime


class ImportImageRead(ORMModel):
    id: int
    import_item_id: int
    source_url: str
    normalized_source_url: str
    position: int
    is_cover: bool
    is_selected: bool
    status: ImportImageStatus
    width: int | None
    height: int | None
    alt_text: str | None
    source_type: str | None
    duplicate_of_id: int | None
    warnings: list[str] | None
    image_metadata: dict | None
    ingestion_status: ImportImageIngestionStatus
    ingestion_attempts: int
    ingestion_started_at: datetime | None
    ingestion_finished_at: datetime | None
    ingested_by_id: int | None
    ingestion_error: str | None
    ingestion_metadata: dict | None
    local_filename: str | None
    local_storage_path: str | None
    local_public_url: str | None
    local_mime_type: str | None
    local_size_bytes: int | None
    local_width: int | None
    local_height: int | None
    content_sha256: str | None
    created_at: datetime
    updated_at: datetime


class ImportItemDetail(ImportItemRead):
    images: list[ImportImageRead] = []
    publication_readiness: "ImportItemPublicationReadiness | None" = None


class ImportItemPublicationReadiness(BaseModel):
    ready: bool
    blockers: list[str] = []
    warnings: list[str] = []


class ImportImageIngestionReadiness(BaseModel):
    ready: bool
    blockers: list[str] = []
    warnings: list[str] = []


class ImportImageIngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updated_at: datetime | None = None


class ImportSelectedImagesIngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_ids: list[int] = Field(min_length=1)
    updated_at: datetime | None = None

    @field_validator("image_ids")
    @classmethod
    def no_duplicate_image_ids(cls, value: list[int]):
        if len(value) != len(set(value)):
            raise ValueError("IDs duplicados nao sao permitidos.")
        return value


class ImportImageIngestionResult(BaseModel):
    image: ImportImageRead
    ready: bool
    created: bool
    message: str


class ImportSelectedImagesIngestionResult(BaseModel):
    images: list[ImportImageRead]
    message: str


class ImportItemApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updated_at: datetime | None = None


class ImportItemPublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updated_at: datetime | None = None


class ImportItemPublicationResult(BaseModel):
    item: ImportItemDetail
    product_id: int | None = None
    created: bool
    message: str


class ImportItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggested_name: str | None = Field(default=None, max_length=300)
    suggested_category_id: int | None = Field(default=None, ge=1)
    suggested_model: str | None = Field(default=None, max_length=180)
    suggested_color: str | None = Field(default=None, max_length=120)
    status: ImportItemStatus | None = None
    warnings: list[str] | None = None
    updated_at: datetime | None = None

    @field_validator("suggested_name", "suggested_model", "suggested_color")
    @classmethod
    def reject_html(cls, value: str | None):
        if value and ("<" in value or ">" in value):
            raise ValueError("HTML nao e permitido.")
        return value

    @field_validator("warnings")
    @classmethod
    def validate_warnings(cls, value: list[str] | None):
        if value is None:
            return value
        cleaned = []
        for warning in value:
            if not warning or len(warning) > 120 or "<" in warning or ">" in warning:
                raise ValueError("Aviso invalido.")
            cleaned.append(warning)
        return cleaned


class ImportImageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_selected: bool | None = None
    is_cover: bool | None = None
    status: ImportImageStatus | None = None
    updated_at: datetime | None = None


class ImportImageReorder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_ids: list[int] = Field(min_length=1)
    updated_at: datetime | None = None

    @field_validator("image_ids")
    @classmethod
    def no_duplicate_ids(cls, value: list[int]):
        if len(value) != len(set(value)):
            raise ValueError("IDs duplicados nao sao permitidos.")
        return value


class ImportRecordRead(ORMModel):
    id: int
    source: str
    external_reference: str | None
    status: str
    brand_id: int | None
    brand: BrandRead | None = None
    source_url: str | None
    normalized_source_url: str | None
    source_type: str | None
    folder_name: str | None
    current_page: int
    total_pages: int | None
    items_found: int
    items_pending: int
    items_approved: int
    items_rejected: int
    items_reviewed: int
    items_needs_review: int
    items_published: int
    items_publish_failed: int
    duplicate_items: int
    error_count: int
    started_at: datetime | None
    finished_at: datetime | None
    publishing_started_at: datetime | None
    publishing_finished_at: datetime | None
    error_message: str | None
    import_metadata: dict | None
    created_at: datetime
    updated_at: datetime


class ImportRecordDetail(ImportRecordRead):
    items: list[ImportItemDetail] = []


class ImportListResponse(BaseModel):
    items: list[ImportRecordRead]
    pagination: dict


class ImportItemListResponse(BaseModel):
    items: list[ImportItemRead]
    pagination: dict


class ImportPreviewResponse(BaseModel):
    id: int
    status: str
    brand: BrandRead
    source_url: str
    message: str
