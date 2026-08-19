"""add import item intelligence fields"""
from alembic import op
import sqlalchemy as sa

revision = "20260724_0003"
down_revision = "20260724_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("import_items") as batch:
        batch.add_column(sa.Column("suggested_color", sa.String(120)))
        batch.add_column(sa.Column("suggested_color_normalized", sa.String(120)))
        batch.add_column(sa.Column("classification_confidence", sa.Numeric(5, 2)))
        batch.add_column(sa.Column("model_confidence", sa.Numeric(5, 2)))
        batch.add_column(sa.Column("color_confidence", sa.Numeric(5, 2)))
        batch.add_column(sa.Column("grouping_confidence", sa.Numeric(5, 2)))
        batch.add_column(sa.Column("overall_confidence", sa.Numeric(5, 2)))
        batch.add_column(sa.Column("image_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("classification_evidence", sa.JSON()))
        batch.add_column(sa.Column("model_evidence", sa.JSON()))
        batch.add_column(sa.Column("color_evidence", sa.JSON()))
        batch.add_column(sa.Column("grouping_evidence", sa.JSON()))
        batch.create_index("ix_import_items_suggested_color_normalized", ["suggested_color_normalized"])
        batch.create_index("ix_import_items_overall_confidence", ["overall_confidence"])


def downgrade() -> None:
    with op.batch_alter_table("import_items") as batch:
        batch.drop_index("ix_import_items_overall_confidence")
        batch.drop_index("ix_import_items_suggested_color_normalized")
        for column in [
            "grouping_evidence",
            "color_evidence",
            "model_evidence",
            "classification_evidence",
            "image_count",
            "overall_confidence",
            "grouping_confidence",
            "color_confidence",
            "model_confidence",
            "classification_confidence",
            "suggested_color_normalized",
            "suggested_color",
        ]:
            batch.drop_column(column)
