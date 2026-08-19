from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserRead


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class SessionRead(BaseModel):
    authenticated: bool
    user: UserRead | None = None


class CsrfRead(BaseModel):
    csrf_token: str
