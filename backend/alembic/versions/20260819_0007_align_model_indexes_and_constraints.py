"""align model indexes and constraints

Revision ID: 20260819_0007
Revises: 20260725_0006
Create Date: 2026-08-19 16:34:39.626538
"""
from typing import Sequence, Union

from alembic import op



revision: str = "20260819_0007"
down_revision: Union[str, None] = "20260725_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f("ix_accessory_types_slug"), table_name="accessory_types")
    op.create_index(op.f("ix_activities_entity_id"), "activities", ["entity_id"], unique=False)
    op.create_index(op.f("ix_activities_entity_type"), "activities", ["entity_type"], unique=False)
    op.drop_index(op.f("ix_admin_users_email"), table_name="admin_users")
    op.drop_index(op.f("ix_brands_slug"), table_name="brands")
    op.drop_index(op.f("ix_categories_slug"), table_name="categories")
    op.drop_index(op.f("ix_collections_slug"), table_name="collections")
    op.drop_index(op.f("ix_products_sku"), table_name="products")
    op.drop_index(op.f("ix_products_slug"), table_name="products")
    op.create_index(op.f("ix_products_brand_id"), "products", ["brand_id"], unique=False)
    op.create_index(op.f("ix_products_category_id"), "products", ["category_id"], unique=False)
    op.drop_index(op.f("ix_sneaker_models_slug"), table_name="sneaker_models")
    op.drop_index(op.f("ix_store_settings_key"), table_name="store_settings")


def downgrade() -> None:
    op.create_index(op.f("ix_store_settings_key"), "store_settings", ["key"], unique=False)
    op.create_index(op.f("ix_sneaker_models_slug"), "sneaker_models", ["slug"], unique=False)
    op.drop_index(op.f("ix_products_category_id"), table_name="products")
    op.drop_index(op.f("ix_products_brand_id"), table_name="products")
    op.create_index(op.f("ix_products_slug"), "products", ["slug"], unique=False)
    op.create_index(op.f("ix_products_sku"), "products", ["sku"], unique=False)
    op.create_index(op.f("ix_collections_slug"), "collections", ["slug"], unique=False)
    op.create_index(op.f("ix_categories_slug"), "categories", ["slug"], unique=False)
    op.create_index(op.f("ix_brands_slug"), "brands", ["slug"], unique=False)
    op.create_index(op.f("ix_admin_users_email"), "admin_users", ["email"], unique=False)
    op.drop_index(op.f("ix_activities_entity_type"), table_name="activities")
    op.drop_index(op.f("ix_activities_entity_id"), table_name="activities")
    op.create_index(op.f("ix_accessory_types_slug"), "accessory_types", ["slug"], unique=False)
