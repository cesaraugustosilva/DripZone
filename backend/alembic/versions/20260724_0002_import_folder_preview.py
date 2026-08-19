"""add folder preview imports"""
from alembic import op
import sqlalchemy as sa

revision = "20260724_0002"
down_revision = "20260721_0001"
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    with op.batch_alter_table("import_records") as batch:
        batch.add_column(sa.Column("created_by_id", sa.Integer()))
        batch.add_column(sa.Column("brand_id", sa.Integer()))
        batch.add_column(sa.Column("source_url", sa.String(1000)))
        batch.add_column(sa.Column("normalized_source_url", sa.String(1000)))
        batch.add_column(sa.Column("source_type", sa.String(40)))
        batch.add_column(sa.Column("folder_name", sa.String(220)))
        batch.add_column(sa.Column("current_page", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("total_pages", sa.Integer()))
        batch.add_column(sa.Column("items_found", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("items_pending", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("items_approved", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("items_rejected", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("duplicate_items", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("started_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("finished_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("import_metadata", sa.JSON()))
        batch.create_index("ix_import_records_brand_id", ["brand_id"])
        batch.create_index("ix_import_records_normalized_source_url", ["normalized_source_url"])
        batch.create_foreign_key("fk_import_records_created_by_id_admin_users", "admin_users", ["created_by_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_import_records_brand_id_brands", "brands", ["brand_id"], ["id"], ondelete="RESTRICT")

    op.create_table(
        "import_items",
        *timestamps(),
        sa.Column("import_record_id", sa.Integer(), sa.ForeignKey("import_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(220)),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("normalized_source_url", sa.String(1000)),
        sa.Column("source_title", sa.String(300)),
        sa.Column("suggested_name", sa.String(300)),
        sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brands.id", ondelete="SET NULL")),
        sa.Column("suggested_category", sa.String(120)),
        sa.Column("suggested_category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL")),
        sa.Column("suggested_model", sa.String(180)),
        sa.Column("confidence", sa.Numeric(5, 2)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("image_urls", sa.JSON()),
        sa.Column("cover_image_url", sa.String(1000)),
        sa.Column("page_number", sa.Integer()),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("duplicate_reason", sa.String(300)),
        sa.Column("warnings", sa.JSON()),
        sa.Column("raw_metadata", sa.JSON()),
        sa.UniqueConstraint("import_record_id", "normalized_source_url", name="uq_import_items_record_url"),
        sa.UniqueConstraint("import_record_id", "external_id", name="uq_import_items_record_external_id"),
    )
    op.create_index("ix_import_items_import_record_id", "import_items", ["import_record_id"])
    op.create_index("ix_import_items_brand_id", "import_items", ["brand_id"])
    op.create_index("ix_import_items_normalized_source_url", "import_items", ["normalized_source_url"])
    op.create_index("ix_import_items_suggested_category", "import_items", ["suggested_category"])
    op.create_index("ix_import_items_status", "import_items", ["status"])


def downgrade() -> None:
    op.drop_table("import_items")
    with op.batch_alter_table("import_records") as batch:
        batch.drop_constraint("fk_import_records_brand_id_brands", type_="foreignkey")
        batch.drop_constraint("fk_import_records_created_by_id_admin_users", type_="foreignkey")
        batch.drop_index("ix_import_records_normalized_source_url")
        batch.drop_index("ix_import_records_brand_id")
        for column in [
            "import_metadata",
            "finished_at",
            "started_at",
            "error_count",
            "duplicate_items",
            "items_rejected",
            "items_approved",
            "items_pending",
            "items_found",
            "total_pages",
            "current_page",
            "folder_name",
            "source_type",
            "normalized_source_url",
            "source_url",
            "brand_id",
            "created_by_id",
        ]:
            batch.drop_column(column)
