"""add import image ingestion fields"""
from alembic import op
import sqlalchemy as sa

revision = "20260725_0006"
down_revision = "20260724_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("import_images") as batch:
        batch.add_column(sa.Column("ingestion_status", sa.String(30), nullable=False, server_default="not_requested"))
        batch.add_column(sa.Column("ingestion_attempts", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("ingestion_started_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("ingestion_finished_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("ingested_by_id", sa.Integer()))
        batch.add_column(sa.Column("ingestion_error", sa.String(120)))
        batch.add_column(sa.Column("ingestion_metadata", sa.JSON()))
        batch.add_column(sa.Column("local_filename", sa.String(180)))
        batch.add_column(sa.Column("local_storage_path", sa.String(600)))
        batch.add_column(sa.Column("local_public_url", sa.String(600)))
        batch.add_column(sa.Column("local_mime_type", sa.String(80)))
        batch.add_column(sa.Column("local_size_bytes", sa.Integer()))
        batch.add_column(sa.Column("local_width", sa.Integer()))
        batch.add_column(sa.Column("local_height", sa.Integer()))
        batch.add_column(sa.Column("content_sha256", sa.String(64)))
        batch.create_foreign_key("fk_import_images_ingested_by_id_admin_users", "admin_users", ["ingested_by_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_import_images_ingestion_status", ["ingestion_status"])
        batch.create_index("ix_import_images_content_sha256", ["content_sha256"])
        batch.create_index("ix_import_images_ingested_by_id", ["ingested_by_id"])
        batch.create_index("ix_import_images_local_storage_path", ["local_storage_path"])


def downgrade() -> None:
    with op.batch_alter_table("import_images") as batch:
        batch.drop_index("ix_import_images_local_storage_path")
        batch.drop_index("ix_import_images_ingested_by_id")
        batch.drop_index("ix_import_images_content_sha256")
        batch.drop_index("ix_import_images_ingestion_status")
        batch.drop_constraint("fk_import_images_ingested_by_id_admin_users", type_="foreignkey")
        batch.drop_column("content_sha256")
        batch.drop_column("local_height")
        batch.drop_column("local_width")
        batch.drop_column("local_size_bytes")
        batch.drop_column("local_mime_type")
        batch.drop_column("local_public_url")
        batch.drop_column("local_storage_path")
        batch.drop_column("local_filename")
        batch.drop_column("ingestion_metadata")
        batch.drop_column("ingestion_error")
        batch.drop_column("ingested_by_id")
        batch.drop_column("ingestion_finished_at")
        batch.drop_column("ingestion_started_at")
        batch.drop_column("ingestion_attempts")
        batch.drop_column("ingestion_status")
