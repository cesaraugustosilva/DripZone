from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ResourceBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, max_length=160, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = True
    position: int = Field(default=0, ge=0)


class BrandCreate(ResourceBase):
    logo_path: str | None = Field(default=None, max_length=500)


class BrandRead(BrandCreate, ORMModel):
    id: int
    slug: str
    created_at: datetime
    updated_at: datetime


class CategoryCreate(ResourceBase):
    parent_id: int | None = None


class CategoryRead(CategoryCreate, ORMModel):
    id: int
    slug: str
    created_at: datetime
    updated_at: datetime


class CollectionCreate(ResourceBase):
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class CollectionRead(CollectionCreate, ORMModel):
    id: int
    slug: str
    created_at: datetime
    updated_at: datetime


class SneakerCreate(BaseModel):
    brand_id: int | None = None
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, max_length=160, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    is_active: bool = True
    position: int = Field(default=0, ge=0)


class SneakerRead(SneakerCreate, ORMModel):
    id: int
    slug: str
    created_at: datetime
    updated_at: datetime


class AccessoryCreate(ResourceBase):
    pass


class AccessoryRead(AccessoryCreate, ORMModel):
    id: int
    slug: str
    created_at: datetime
    updated_at: datetime
