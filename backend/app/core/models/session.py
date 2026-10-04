from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from tortoise import fields

from app.core.context import get_context
from app.core.models.entity import Entity

if TYPE_CHECKING:
    from app.core.models.user import Users


class UserSession(Entity):
    """Sesión de un usuario en un dispositivo. Cerrarla no la borra: guarda el motivo."""

    user: fields.ForeignKeyRelation[Users] = fields.ForeignKeyField(
        "models.Users", related_name="sessions", on_delete=fields.CASCADE
    )
    user_id: UUID
    refresh_token_jti = fields.CharField(max_length=36, db_index=True)
    access_token_jti = fields.CharField(max_length=36, db_index=True)
    expires_at = fields.DatetimeField()
    last_activity = fields.DatetimeField()
    user_agent = fields.CharField(max_length=255, null=True)
    ip_address = fields.CharField(max_length=45, null=True)
    revoked_reason = fields.CharField(max_length=100, null=True)

    audit = False

    class Meta(Entity.Meta):
        table = "user_sessions"

    def is_expired(self) -> bool:
        """Caducó su plazo de renovación o cumplió los 30 días desde que se abrió."""
        now = datetime.now(UTC)
        return self.expires_at < now or self.created_at + timedelta(days=30) < now

    async def touch(self) -> None:
        """Marca actividad reciente."""
        self.last_activity = datetime.now(UTC)
        await self.save(update_fields=["last_activity"])

    async def revoke(self, reason: str) -> None:
        """Cierra la sesión y anota el motivo."""
        self.revoked_reason = reason
        self.deleted_at = datetime.now(UTC)
        self.deleted_by_id = get_context().actor_id
        await self.save(
            update_fields=["revoked_reason", "deleted_at", "deleted_by_id", "updated_at"]
        )
