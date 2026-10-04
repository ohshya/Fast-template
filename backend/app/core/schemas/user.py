from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.core.schemas.types import Password, Username
from app.core.schemas.validators import validate_password, validate_username


class UserOut(BaseModel):
    id: UUID
    username: str
    is_active: bool
    dev: bool
    role_id: UUID | None
    role_name: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    last_login_at: datetime | None


class UserCreate(BaseModel):
    username: Username
    password: Password
    role_id: UUID | None = None
    is_active: bool = True
    dev: bool = False

    _check_username = field_validator("username")(validate_username)
    _check_password = field_validator("password")(validate_password)


class UserUpdate(BaseModel):
    username: Username | None = None
    role_id: UUID | None = None
    is_active: bool | None = None
    dev: bool | None = None

    @field_validator("username")
    @classmethod
    def _check_username(cls, value: str | None) -> str | None:
        return validate_username(value) if value is not None else None


class PasswordReset(BaseModel):
    new_password: Password

    _check_password = field_validator("new_password")(validate_password)
