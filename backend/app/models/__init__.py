from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


product_collections = Table(
    "product_collections",
    Base.metadata,
    Column("product_id", ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    Column("collection_id", ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True),
)


class AdminUser(TimestampMixin, Base):
    __tablename__ = "admin_users"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="editor", nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    session_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Brand(TimestampMixin, Base):
    __tablename__ = "brands"
    __table_args__ = (UniqueConstraint("name", name="uq_brands_name"),)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    logo_path: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    products: Mapped[list["Product"]] = relationship(back_populates="brand")
    sneaker_models: Mapped[list["SneakerModel"]] = relationship(back_populates="brand")
    import_records: Mapped[list["ImportRecord"]] = relationship(back_populates="brand")


class Category(TimestampMixin, Base):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parent: Mapped["Category | None"] = relationship(remote_side="Category.id")
    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Collection(TimestampMixin, Base):
    __tablename__ = "collections"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    products: Mapped[list["Product"]] = relationship(secondary=product_collections, back_populates="collections")


class SneakerModel(TimestampMixin, Base):
    __tablename__ = "sneaker_models"

    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    brand: Mapped[Brand | None] = relationship(back_populates="sneaker_models")


class AccessoryType(TimestampMixin, Base):
    __tablename__ = "accessory_types"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("public_id", name="uq_products_public_id"),
        UniqueConstraint("slug", name="uq_products_slug"),
        UniqueConstraint("sku", name="uq_products_sku"),
        Index("ix_products_status_visibility", "status", "visibility"),
    )

    public_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(220), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(80))
    short_description: Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id", ondelete="SET NULL"), index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), index=True)
    sneaker_model_id: Mapped[int | None] = mapped_column(ForeignKey("sneaker_models.id", ondelete="SET NULL"))
    accessory_id: Mapped[int | None] = mapped_column(ForeignKey("accessory_types.id", ondelete="SET NULL"))
    product_type: Mapped[str | None] = mapped_column(String(40))
    audience: Mapped[str | None] = mapped_column(String(40))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    compare_at_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    cost_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    promotional_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    promotion_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    promotion_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    track_inventory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    minimum_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    allow_backorder: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    availability: Mapped[str] = mapped_column(String(30), default="available", nullable=False)
    ready_to_ship: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False, index=True)
    visibility: Mapped[str] = mapped_column(String(30), default="hidden", nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_new: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_best_seller: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    seo_title: Mapped[str | None] = mapped_column(String(180))
    seo_description: Mapped[str | None] = mapped_column(String(300))
    canonical_url: Mapped[str | None] = mapped_column(String(500))
    main_image_alt: Mapped[str | None] = mapped_column(String(180))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id", ondelete="SET NULL"))
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id", ondelete="SET NULL"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    brand: Mapped[Brand | None] = relationship(back_populates="products")
    category: Mapped[Category | None] = relationship(back_populates="products")
    sneaker_model: Mapped[SneakerModel | None] = relationship()
    collections: Mapped[list[Collection]] = relationship(secondary=product_collections, back_populates="products")
    variants: Mapped[list["ProductVariant"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    images: Mapped[list["ProductImage"]] = relationship(back_populates="product", cascade="all, delete-orphan")


class ProductVariant(TimestampMixin, Base):
    __tablename__ = "product_variants"
    __table_args__ = (UniqueConstraint("sku", name="uq_product_variants_sku"),)

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    sku: Mapped[str | None] = mapped_column(String(80))
    size: Mapped[str | None] = mapped_column(String(50))
    color: Mapped[str | None] = mapped_column(String(80))
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    price_override: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    product: Mapped[Product] = relationship(back_populates="variants")


class ProductImage(TimestampMixin, Base):
    __tablename__ = "product_images"

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(180), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(600), nullable=False)
    public_url: Mapped[str] = mapped_column(String(600), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    alt_text: Mapped[str | None] = mapped_column(String(180))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    product: Mapped[Product] = relationship(back_populates="images")


class ImportRecord(TimestampMixin, Base):
    __tablename__ = "import_records"

    source: Mapped[str] = mapped_column(String(80), nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON)
    normalized_payload: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id", ondelete="SET NULL"))
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id", ondelete="RESTRICT"), index=True)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    normalized_source_url: Mapped[str | None] = mapped_column(String(1000), index=True)
    source_type: Mapped[str | None] = mapped_column(String(40))
    folder_name: Mapped[str | None] = mapped_column(String(220))
    current_page: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_pages: Mapped[int | None] = mapped_column(Integer)
    items_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_pending: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_approved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_reviewed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_needs_review: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_published: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_publish_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publishing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publishing_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    import_metadata: Mapped[dict | None] = mapped_column(JSON)
    brand: Mapped[Brand | None] = relationship(back_populates="import_records")
    items: Mapped[list["ImportItem"]] = relationship(back_populates="import_record", cascade="all, delete-orphan")


class ImportItem(TimestampMixin, Base):
    __tablename__ = "import_items"
    __table_args__ = (
        UniqueConstraint("import_record_id", "normalized_source_url", name="uq_import_items_record_url"),
        UniqueConstraint("import_record_id", "external_id", name="uq_import_items_record_external_id"),
    )

    import_record_id: Mapped[int] = mapped_column(ForeignKey("import_records.id", ondelete="CASCADE"), nullable=False, index=True)
    external_id: Mapped[str | None] = mapped_column(String(220))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    normalized_source_url: Mapped[str | None] = mapped_column(String(1000), index=True)
    source_title: Mapped[str | None] = mapped_column(String(300))
    suggested_name: Mapped[str | None] = mapped_column(String(300))
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id", ondelete="SET NULL"), index=True)
    suggested_category: Mapped[str | None] = mapped_column(String(120), index=True)
    suggested_category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    suggested_model: Mapped[str | None] = mapped_column(String(180))
    suggested_color: Mapped[str | None] = mapped_column(String(120))
    suggested_color_normalized: Mapped[str | None] = mapped_column(String(120), index=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 2))
    classification_confidence: Mapped[float | None] = mapped_column(Numeric(5, 2))
    model_confidence: Mapped[float | None] = mapped_column(Numeric(5, 2))
    color_confidence: Mapped[float | None] = mapped_column(Numeric(5, 2))
    grouping_confidence: Mapped[float | None] = mapped_column(Numeric(5, 2))
    overall_confidence: Mapped[float | None] = mapped_column(Numeric(5, 2), index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    image_urls: Mapped[list | None] = mapped_column(JSON)
    cover_image_url: Mapped[str | None] = mapped_column(String(1000))
    image_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_reason: Mapped[str | None] = mapped_column(String(300))
    warnings: Mapped[list | None] = mapped_column(JSON)
    classification_evidence: Mapped[dict | None] = mapped_column(JSON)
    model_evidence: Mapped[dict | None] = mapped_column(JSON)
    color_evidence: Mapped[dict | None] = mapped_column(JSON)
    grouping_evidence: Mapped[dict | None] = mapped_column(JSON)
    raw_metadata: Mapped[dict | None] = mapped_column(JSON)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id", ondelete="SET NULL"), index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    published_by_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id", ondelete="SET NULL"), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    published_product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), unique=True, index=True)
    publish_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    publish_error: Mapped[str | None] = mapped_column(String(500))
    publish_metadata: Mapped[dict | None] = mapped_column(JSON)
    import_record: Mapped[ImportRecord] = relationship(back_populates="items")
    images: Mapped[list["ImportImage"]] = relationship(back_populates="import_item", cascade="all, delete-orphan", order_by="ImportImage.position")


class ImportImage(TimestampMixin, Base):
    __tablename__ = "import_images"
    __table_args__ = (
        UniqueConstraint("import_item_id", "normalized_source_url", name="uq_import_images_item_url"),
        CheckConstraint("position >= 0", name="ck_import_images_position_non_negative"),
        Index("ix_import_images_ingestion_status", "ingestion_status"),
        Index("ix_import_images_content_sha256", "content_sha256"),
        Index("ix_import_images_ingested_by_id", "ingested_by_id"),
        Index("ix_import_images_local_storage_path", "local_storage_path"),
        Index("ix_import_images_item_cover", "import_item_id", unique=True, postgresql_where=text("is_cover = true"), sqlite_where=text("is_cover = 1")),
    )

    import_item_id: Mapped[int] = mapped_column(ForeignKey("import_items.id", ondelete="CASCADE"), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    normalized_source_url: Mapped[str] = mapped_column(String(1000), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    is_cover: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False, index=True)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    alt_text: Mapped[str | None] = mapped_column(String(300))
    source_type: Mapped[str | None] = mapped_column(String(60))
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("import_images.id", ondelete="SET NULL"))
    warnings: Mapped[list | None] = mapped_column(JSON)
    image_metadata: Mapped[dict | None] = mapped_column(JSON)
    ingestion_status: Mapped[str] = mapped_column(String(30), default="not_requested", nullable=False)
    ingestion_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ingestion_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingestion_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_by_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id", ondelete="SET NULL"))
    ingestion_error: Mapped[str | None] = mapped_column(String(120))
    ingestion_metadata: Mapped[dict | None] = mapped_column(JSON)
    local_filename: Mapped[str | None] = mapped_column(String(180))
    local_storage_path: Mapped[str | None] = mapped_column(String(600))
    local_public_url: Mapped[str | None] = mapped_column(String(600))
    local_mime_type: Mapped[str | None] = mapped_column(String(80))
    local_size_bytes: Mapped[int | None] = mapped_column(Integer)
    local_width: Mapped[int | None] = mapped_column(Integer)
    local_height: Mapped[int | None] = mapped_column(Integer)
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    import_item: Mapped[ImportItem] = relationship(back_populates="images")
    duplicate_of: Mapped["ImportImage | None"] = relationship(remote_side="ImportImage.id")
    ingested_by: Mapped[AdminUser | None] = relationship()


class StoreSetting(TimestampMixin, Base):
    __tablename__ = "store_settings"
    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    value: Mapped[str | None] = mapped_column(Text)
    value_type: Mapped[str] = mapped_column(String(20), default="string", nullable=False)


class Activity(TimestampMixin, Base):
    __tablename__ = "activities"

    user_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(80), index=True)
    summary: Mapped[str] = mapped_column(String(300), nullable=False)
    activity_metadata: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(80))
