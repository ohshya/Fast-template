from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class RoleOut(BaseModel):
    id: UUID
    name: str
    description: str
    permissions: list[int]
    users_count: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=255)
    permissions: list[int] = Field(default_factory=list, max_length=2000)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        return value.strip()


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    permissions: list[int] | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None
