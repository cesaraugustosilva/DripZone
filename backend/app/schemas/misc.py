from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ImportRead(ORMModel):
    id: int
    source: str
    external_reference: str | None
    status: Literal["pending", "review", "approved", "rejected", "published", "error"]
    error_message: str | None
    reviewed_at: datetime | None
    published_product_id: int | None
    created_at: datetime
    updated_at: datetime


class SettingsUpdate(BaseModel):
    store_name: str | None = Field(default=None, max_length=120)
    store_description: str | None = Field(default=None, max_length=500)
    currency: str | None = Field(default=None, max_length=10)
    locale: str | None = Field(default=None, max_length=20)
    timezone: str | None = Field(default=None, max_length=80)
    products_per_page: int | None = Field(default=None, ge=1, le=100)
    show_out_of_stock: bool | None = None
    default_sort: str | None = Field(default=None, max_length=40)
    empty_catalog_message: str | None = Field(default=None, max_length=300)
    free_shipping_enabled: bool | None = None
    free_shipping_minimum: str | None = Field(default=None, max_length=40)
    installments_enabled: bool | None = None
    max_installments: int | None = Field(default=None, ge=1, le=24)
    pix_enabled: bool | None = None
    admin_table_density: str | None = Field(default=None, max_length=40)


class ActivityRead(ORMModel):
    id: int
    user_id: int | None
    action: str
    entity_type: str | None
    entity_id: str | None
    summary: str
    activity_metadata: dict | None
    ip_address: str | None
    created_at: datetime
