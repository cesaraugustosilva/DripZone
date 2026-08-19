"""add import images and review fields"""
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from alembic import op
import sqlalchemy as sa

revision = "20260724_0004"
down_revision = "20260724_0003"
branch_labels = None
depends_on = None


def normalize_url(value: str) -> str:
    parsed = urlparse(str(value).strip())
    query = []
    for key, query_value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered in {"fbclid", "gclid", "ref", "source"} or lowered.startswith("utm_"):
            continue
        query.append((key, query_value))
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunparse(parsed._replace(scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower(), path=path, params="", query=urlencode(sorted(query)), fragment=""))


def upgrade() -> None:
    with op.batch_alter_table("import_records") as batch:
        batch.add_column(sa.Column("items_reviewed", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("items_needs_review", sa.Integer(), nullable=False, server_default="0"))

    with op.batch_alter_table("import_items") as batch:
        batch.add_column(sa.Column("reviewed_by_id", sa.Integer()))
        batch.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True)))
        batch.create_foreign_key("fk_import_items_reviewed_by_id_admin_users", "admin_users", ["reviewed_by_id"], ["id"], ondelete="SET NULL")

    op.create_table(
        "import_images",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("import_item_id", sa.Integer(), sa.ForeignKey("import_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("normalized_source_url", sa.String(1000), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_cover", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_selected", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("alt_text", sa.String(300)),
        sa.Column("source_type", sa.String(60)),
        sa.Column("duplicate_of_id", sa.Integer(), sa.ForeignKey("import_images.id", ondelete="SET NULL")),
        sa.Column("warnings", sa.JSON()),
        sa.Column("image_metadata", sa.JSON()),
        sa.UniqueConstraint("import_item_id", "normalized_source_url", name="uq_import_images_item_url"),
        sa.CheckConstraint("position >= 0", name="ck_import_images_position_non_negative"),
    )
    op.create_index("ix_import_images_import_item_id", "import_images", ["import_item_id"])
    op.create_index("ix_import_images_normalized_source_url", "import_images", ["normalized_source_url"])
    op.create_index("ix_import_images_status", "import_images", ["status"])
    op.create_index("ix_import_images_is_selected", "import_images", ["is_selected"])
    op.create_index("ix_import_images_is_cover", "import_images", ["is_cover"])
    op.create_index("ix_import_images_position", "import_images", ["position"])
    op.create_index(
        "ix_import_images_item_cover",
        "import_images",
        ["import_item_id"],
        unique=True,
        postgresql_where=sa.text("is_cover = true"),
        sqlite_where=sa.text("is_cover = 1"),
    )

    connection = op.get_bind()
    items = connection.execute(sa.text("SELECT id, image_urls, cover_image_url FROM import_items")).mappings().all()
    import_images = sa.table(
        "import_images",
        sa.column("import_item_id"),
        sa.column("source_url"),
        sa.column("normalized_source_url"),
        sa.column("position"),
        sa.column("is_cover"),
        sa.column("is_selected"),
        sa.column("status"),
        sa.column("source_type"),
        sa.column("warnings"),
        sa.column("image_metadata"),
    )
    for item in items:
        image_urls = item["image_urls"] or []
        if not isinstance(image_urls, list):
            continue
        seen: set[str] = set()
        position = 0
        normalized_cover = normalize_url(item["cover_image_url"]) if item["cover_image_url"] else None
        for source_url in image_urls:
            if not source_url:
                continue
            normalized = normalize_url(str(source_url))
            if normalized in seen:
                continue
            seen.add(normalized)
            connection.execute(
                import_images.insert().values(
                    import_item_id=item["id"],
                    source_url=str(source_url),
                    normalized_source_url=normalized,
                    position=position,
                    is_cover=normalized == normalized_cover or (not normalized_cover and position == 0),
                    is_selected=True,
                    status="active",
                    source_type="legacy_image_urls",
                    warnings=[],
                    image_metadata={"source": "migration_20260724_0004"},
                )
            )
            position += 1

    connection.execute(sa.text("UPDATE import_records SET items_reviewed = (SELECT COUNT(*) FROM import_items WHERE import_items.import_record_id = import_records.id AND import_items.status = 'reviewed')"))
    connection.execute(sa.text("UPDATE import_records SET items_needs_review = (SELECT COUNT(*) FROM import_items WHERE import_items.import_record_id = import_records.id AND import_items.status = 'needs_review')"))


def downgrade() -> None:
    op.drop_index("ix_import_images_item_cover", table_name="import_images")
    op.drop_index("ix_import_images_position", table_name="import_images")
    op.drop_index("ix_import_images_is_cover", table_name="import_images")
    op.drop_index("ix_import_images_is_selected", table_name="import_images")
    op.drop_index("ix_import_images_status", table_name="import_images")
    op.drop_index("ix_import_images_normalized_source_url", table_name="import_images")
    op.drop_index("ix_import_images_import_item_id", table_name="import_images")
    op.drop_table("import_images")
    with op.batch_alter_table("import_items") as batch:
        batch.drop_constraint("fk_import_items_reviewed_by_id_admin_users", type_="foreignkey")
        batch.drop_column("reviewed_at")
        batch.drop_column("reviewed_by_id")
    with op.batch_alter_table("import_records") as batch:
        batch.drop_column("items_needs_review")
        batch.drop_column("items_reviewed")
