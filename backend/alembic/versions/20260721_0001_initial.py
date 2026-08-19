"""initial admin backend schema"""
from alembic import op
import sqlalchemy as sa

revision = "20260721_0001"
down_revision = None
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table("admin_users", *timestamps(), sa.Column("name", sa.String(120), nullable=False), sa.Column("email", sa.String(255), nullable=False), sa.Column("password_hash", sa.String(255), nullable=False), sa.Column("role", sa.String(20), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("last_login_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("email"))
    op.create_index("ix_admin_users_email", "admin_users", ["email"])
    op.create_index("ix_admin_users_role", "admin_users", ["role"])
    op.create_table("brands", *timestamps(), sa.Column("name", sa.String(120), nullable=False), sa.Column("slug", sa.String(140), nullable=False), sa.Column("description", sa.Text()), sa.Column("logo_path", sa.String(500)), sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("position", sa.Integer(), nullable=False), sa.UniqueConstraint("name", name="uq_brands_name"), sa.UniqueConstraint("slug"))
    op.create_index("ix_brands_slug", "brands", ["slug"])
    op.create_table("categories", *timestamps(), sa.Column("name", sa.String(120), nullable=False), sa.Column("slug", sa.String(140), nullable=False), sa.Column("description", sa.Text()), sa.Column("parent_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL")), sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("position", sa.Integer(), nullable=False), sa.UniqueConstraint("slug"))
    op.create_index("ix_categories_slug", "categories", ["slug"])
    op.create_table("collections", *timestamps(), sa.Column("name", sa.String(120), nullable=False), sa.Column("slug", sa.String(140), nullable=False), sa.Column("description", sa.Text()), sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("starts_at", sa.DateTime(timezone=True)), sa.Column("ends_at", sa.DateTime(timezone=True)), sa.Column("position", sa.Integer(), nullable=False), sa.UniqueConstraint("slug"))
    op.create_index("ix_collections_slug", "collections", ["slug"])
    op.create_table("accessory_types", *timestamps(), sa.Column("name", sa.String(120), nullable=False), sa.Column("slug", sa.String(140), nullable=False), sa.Column("description", sa.Text()), sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("position", sa.Integer(), nullable=False), sa.UniqueConstraint("slug"))
    op.create_index("ix_accessory_types_slug", "accessory_types", ["slug"])
    op.create_table("sneaker_models", *timestamps(), sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brands.id", ondelete="SET NULL")), sa.Column("name", sa.String(120), nullable=False), sa.Column("slug", sa.String(160), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("position", sa.Integer(), nullable=False), sa.UniqueConstraint("slug"))
    op.create_index("ix_sneaker_models_brand_id", "sneaker_models", ["brand_id"])
    op.create_index("ix_sneaker_models_slug", "sneaker_models", ["slug"])
    op.create_table("products", *timestamps(), sa.Column("public_id", sa.String(64), nullable=False), sa.Column("name", sa.String(180), nullable=False), sa.Column("slug", sa.String(220), nullable=False), sa.Column("sku", sa.String(80)), sa.Column("short_description", sa.String(300)), sa.Column("description", sa.Text()), sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brands.id", ondelete="SET NULL")), sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL")), sa.Column("sneaker_model_id", sa.Integer(), sa.ForeignKey("sneaker_models.id", ondelete="SET NULL")), sa.Column("accessory_id", sa.Integer(), sa.ForeignKey("accessory_types.id", ondelete="SET NULL")), sa.Column("product_type", sa.String(40)), sa.Column("audience", sa.String(40)), sa.Column("price", sa.Numeric(12, 2), nullable=False), sa.Column("compare_at_price", sa.Numeric(12, 2)), sa.Column("cost_price", sa.Numeric(12, 2)), sa.Column("promotional_price", sa.Numeric(12, 2)), sa.Column("promotion_starts_at", sa.DateTime(timezone=True)), sa.Column("promotion_ends_at", sa.DateTime(timezone=True)), sa.Column("track_inventory", sa.Boolean(), nullable=False), sa.Column("stock_quantity", sa.Integer(), nullable=False), sa.Column("minimum_stock", sa.Integer(), nullable=False), sa.Column("allow_backorder", sa.Boolean(), nullable=False), sa.Column("availability", sa.String(30), nullable=False), sa.Column("ready_to_ship", sa.Boolean(), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("visibility", sa.String(30), nullable=False), sa.Column("is_featured", sa.Boolean(), nullable=False), sa.Column("is_new", sa.Boolean(), nullable=False), sa.Column("is_best_seller", sa.Boolean(), nullable=False), sa.Column("seo_title", sa.String(180)), sa.Column("seo_description", sa.String(300)), sa.Column("canonical_url", sa.String(500)), sa.Column("main_image_alt", sa.String(180)), sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("admin_users.id", ondelete="SET NULL")), sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("admin_users.id", ondelete="SET NULL")), sa.Column("published_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("public_id", name="uq_products_public_id"), sa.UniqueConstraint("slug", name="uq_products_slug"), sa.UniqueConstraint("sku", name="uq_products_sku"))
    op.create_index("ix_products_name", "products", ["name"])
    op.create_index("ix_products_slug", "products", ["slug"])
    op.create_index("ix_products_sku", "products", ["sku"])
    op.create_index("ix_products_status", "products", ["status"])
    op.create_index("ix_products_status_visibility", "products", ["status", "visibility"])
    op.create_table("product_collections", sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True), sa.Column("collection_id", sa.Integer(), sa.ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True))
    op.create_table("product_variants", *timestamps(), sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False), sa.Column("sku", sa.String(80)), sa.Column("size", sa.String(50)), sa.Column("color", sa.String(80)), sa.Column("stock_quantity", sa.Integer(), nullable=False), sa.Column("price_override", sa.Numeric(12, 2)), sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("position", sa.Integer(), nullable=False), sa.UniqueConstraint("sku", name="uq_product_variants_sku"))
    op.create_index("ix_product_variants_product_id", "product_variants", ["product_id"])
    op.create_table("product_images", *timestamps(), sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False), sa.Column("filename", sa.String(180), nullable=False), sa.Column("storage_path", sa.String(600), nullable=False), sa.Column("public_url", sa.String(600), nullable=False), sa.Column("mime_type", sa.String(80), nullable=False), sa.Column("size_bytes", sa.Integer(), nullable=False), sa.Column("width", sa.Integer(), nullable=False), sa.Column("height", sa.Integer(), nullable=False), sa.Column("alt_text", sa.String(180)), sa.Column("is_primary", sa.Boolean(), nullable=False), sa.Column("position", sa.Integer(), nullable=False))
    op.create_index("ix_product_images_product_id", "product_images", ["product_id"])
    op.create_table("import_records", *timestamps(), sa.Column("source", sa.String(80), nullable=False), sa.Column("external_reference", sa.String(180)), sa.Column("status", sa.String(30), nullable=False), sa.Column("raw_payload", sa.JSON()), sa.Column("normalized_payload", sa.JSON()), sa.Column("error_message", sa.Text()), sa.Column("reviewed_by_id", sa.Integer(), sa.ForeignKey("admin_users.id", ondelete="SET NULL")), sa.Column("reviewed_at", sa.DateTime(timezone=True)), sa.Column("published_product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="SET NULL")))
    op.create_index("ix_import_records_status", "import_records", ["status"])
    op.create_table("store_settings", *timestamps(), sa.Column("key", sa.String(80), nullable=False), sa.Column("value", sa.Text()), sa.Column("value_type", sa.String(20), nullable=False), sa.UniqueConstraint("key"))
    op.create_index("ix_store_settings_key", "store_settings", ["key"])
    op.create_table("activities", *timestamps(), sa.Column("user_id", sa.Integer(), sa.ForeignKey("admin_users.id", ondelete="SET NULL")), sa.Column("action", sa.String(80), nullable=False), sa.Column("entity_type", sa.String(80)), sa.Column("entity_id", sa.String(80)), sa.Column("summary", sa.String(300), nullable=False), sa.Column("activity_metadata", sa.JSON()), sa.Column("ip_address", sa.String(80)))
    op.create_index("ix_activities_action", "activities", ["action"])
    op.create_index("ix_activities_user_id", "activities", ["user_id"])


def downgrade() -> None:
    for table in ["activities", "store_settings", "import_records", "product_images", "product_variants", "product_collections", "products", "sneaker_models", "accessory_types", "collections", "categories", "brands", "admin_users"]:
        op.drop_table(table)
