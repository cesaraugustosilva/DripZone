from pydantic import BaseModel, ConfigDict


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class PaginatedResponse(BaseModel):
    items: list
    pagination: Pagination


class Message(BaseModel):
    message: str


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
