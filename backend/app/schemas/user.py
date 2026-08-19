from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel

Role = Literal["owner", "admin", "editor"]


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    role: Role = "editor"
    is_active: bool = True


class UserRead(ORMModel):
    id: int
    name: str
    email: EmailStr
    role: Role
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
