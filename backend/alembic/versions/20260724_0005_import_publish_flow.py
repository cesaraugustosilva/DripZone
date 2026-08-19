"""add import approval and publish flow"""
from alembic import op
import sqlalchemy as sa

revision = "20260724_0005"
down_revision = "20260724_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("import_records") as batch:
        batch.add_column(sa.Column("items_published", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("items_publish_failed", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("publishing_started_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("publishing_finished_at", sa.DateTime(timezone=True)))

    with op.batch_alter_table("import_items") as batch:
        batch.add_column(sa.Column("approved_by_id", sa.Integer()))
        batch.add_column(sa.Column("approved_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("published_by_id", sa.Integer()))
        batch.add_column(sa.Column("published_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("published_product_id", sa.Integer()))
        batch.add_column(sa.Column("publish_attempts", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("publish_error", sa.String(500)))
        batch.add_column(sa.Column("publish_metadata", sa.JSON()))
        batch.create_foreign_key("fk_import_items_approved_by_id_admin_users", "admin_users", ["approved_by_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_import_items_published_by_id_admin_users", "admin_users", ["published_by_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_import_items_published_product_id_products", "products", ["published_product_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_import_items_approved_by_id", ["approved_by_id"])
        batch.create_index("ix_import_items_approved_at", ["approved_at"])
        batch.create_index("ix_import_items_published_by_id", ["published_by_id"])
        batch.create_index("ix_import_items_published_at", ["published_at"])
        batch.create_index("ix_import_items_published_product_id", ["published_product_id"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("import_items") as batch:
        batch.drop_index("ix_import_items_published_product_id")
        batch.drop_index("ix_import_items_published_at")
        batch.drop_index("ix_import_items_published_by_id")
        batch.drop_index("ix_import_items_approved_at")
        batch.drop_index("ix_import_items_approved_by_id")
        batch.drop_constraint("fk_import_items_published_product_id_products", type_="foreignkey")
        batch.drop_constraint("fk_import_items_published_by_id_admin_users", type_="foreignkey")
        batch.drop_constraint("fk_import_items_approved_by_id_admin_users", type_="foreignkey")
        batch.drop_column("publish_metadata")
        batch.drop_column("publish_error")
        batch.drop_column("publish_attempts")
        batch.drop_column("published_product_id")
        batch.drop_column("published_at")
        batch.drop_column("published_by_id")
        batch.drop_column("approved_at")
        batch.drop_column("approved_by_id")
    with op.batch_alter_table("import_records") as batch:
        batch.drop_column("publishing_finished_at")
        batch.drop_column("publishing_started_at")
        batch.drop_column("items_publish_failed")
        batch.drop_column("items_published")
