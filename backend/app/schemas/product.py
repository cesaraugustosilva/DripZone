from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel

ProductStatus = Literal["draft", "published", "archived"]
Visibility = Literal["public", "hidden"]
Availability = Literal["available", "out_of_stock", "pre_order", "unavailable"]


class VariantBase(BaseModel):
    sku: str | None = Field(default=None, max_length=80)
    size: str | None = Field(default=None, max_length=50)
    color: str | None = Field(default=None, max_length=80)
    stock_quantity: int = Field(default=0, ge=0)
    price_override: Decimal | None = Field(default=None, ge=0)
    is_active: bool = True
    position: int = Field(default=0, ge=0)


class VariantCreate(VariantBase):
    pass


class VariantRead(VariantBase, ORMModel):
    id: int
    product_id: int
    created_at: datetime
    updated_at: datetime


class ImageRead(ORMModel):
    id: int
    product_id: int
    filename: str
    public_url: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    alt_text: str | None
    is_primary: bool
    position: int
    created_at: datetime
    updated_at: datetime


class ProductBase(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    slug: str | None = Field(default=None, max_length=220, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    sku: str | None = Field(default=None, max_length=80)
    short_description: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    brand_id: int | None = None
    category_id: int | None = None
    collection_ids: list[int] = []
    sneaker_model_id: int | None = None
    accessory_id: int | None = None
    product_type: str | None = Field(default=None, max_length=40)
    audience: str | None = Field(default=None, max_length=40)
    price: Decimal = Field(default=Decimal("0.00"), ge=0)
    compare_at_price: Decimal | None = Field(default=None, ge=0)
    cost_price: Decimal | None = Field(default=None, ge=0)
    promotional_price: Decimal | None = Field(default=None, ge=0)
    promotion_starts_at: datetime | None = None
    promotion_ends_at: datetime | None = None
    track_inventory: bool = True
    stock_quantity: int = Field(default=0, ge=0)
    minimum_stock: int = Field(default=0, ge=0)
    allow_backorder: bool = False
    availability: Availability = "available"
    ready_to_ship: bool = False
    status: ProductStatus = "draft"
    visibility: Visibility = "hidden"
    is_featured: bool = False
    is_new: bool = False
    is_best_seller: bool = False
    seo_title: str | None = Field(default=None, max_length=180)
    seo_description: str | None = Field(default=None, max_length=300)
    canonical_url: str | None = Field(default=None, max_length=500)
    main_image_alt: str | None = Field(default=None, max_length=180)

    @field_validator("promotion_ends_at")
    @classmethod
    def validate_promo_dates(cls, value, info):
        start = info.data.get("promotion_starts_at")
        if value and start and value <= start:
            raise ValueError("Fim da promoção deve ser posterior ao início.")
        return value

    @field_validator("promotional_price")
    @classmethod
    def validate_promo_price(cls, value, info):
        price = info.data.get("price")
        if value is not None and price is not None and value > price:
            raise ValueError("Preço promocional não pode ser maior que o preço.")
        return value


class ProductCreate(ProductBase):
    variants: list[VariantCreate] = []


class ProductUpdate(ProductBase):
    name: str = Field(min_length=2, max_length=180)


class ProductPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    slug: str | None = Field(default=None, max_length=220, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    sku: str | None = Field(default=None, max_length=80)
    short_description: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    price: Decimal | None = Field(default=None, ge=0)
    stock_quantity: int | None = Field(default=None, ge=0)
    status: ProductStatus | None = None
    visibility: Visibility | None = None
    availability: Availability | None = None
    is_featured: bool | None = None
    is_new: bool | None = None
    is_best_seller: bool | None = None


class ProductRead(ProductBase, ORMModel):
    id: int
    public_id: str
    slug: str
    price: Decimal
    status: ProductStatus
    visibility: Visibility
    variants: list[VariantRead] = []
    images: list[ImageRead] = []
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
