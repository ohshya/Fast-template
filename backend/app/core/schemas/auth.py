from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.core.schemas.types import Password, Username
from app.core.schemas.validators import validate_password

if TYPE_CHECKING:
    from app.core.models.session import UserSession


class LoginIn(BaseModel):
    username: Username
    password: Password

    @field_validator("username")
    @classmethod
    def _normalize_username(cls, value: str) -> str:
        return value.strip().lower()


class MeOut(BaseModel):
    id: UUID
    username: str
    is_active: bool
    dev: bool
    role_id: UUID | None
    role_name: str | None
    permissions: list[int]
    permission_keys: list[str]
    last_login_at: datetime | None


class SessionOut(BaseModel):
    id: UUID
    device: str
    ip_address: str | None
    created_at: datetime
    last_activity: datetime
    expires_at: datetime
    is_current: bool

    @classmethod
    def of(cls, session: UserSession, current_id: UUID | None) -> SessionOut:
        return cls(
            id=session.id,
            device=session.user_agent or "Desconocido",
            ip_address=session.ip_address,
            created_at=session.created_at,
            last_activity=session.last_activity,
            expires_at=session.expires_at,
            is_current=session.id == current_id,
        )


class PasswordChange(BaseModel):
    current_password: Password
    new_password: Password

    _check_password = field_validator("new_password")(validate_password)
