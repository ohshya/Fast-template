import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid7

from tortoise import fields
from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.models import Model

from app.settings import settings

CHAIN_ID = 1


def time_of(identifier: UUID) -> datetime:
    """Fecha escrita dentro de un UUIDv7."""
    return datetime.fromtimestamp((identifier.int >> 80) / 1000, UTC)


def id_at(moment: datetime) -> UUID:
    """Menor UUIDv7 de ese instante (antes de 1970, el de 1970). Exige zona horaria."""
    if moment.tzinfo is None:
        raise ValueError("La fecha necesita zona horaria")
    milliseconds = max(0, (moment - datetime(1970, 1, 1, tzinfo=UTC)) // timedelta(milliseconds=1))
    return UUID(int=(milliseconds << 80) | (0x7 << 76) | (0b10 << 62))


class EventCategory(StrEnum):
    DOMAIN = "domain"
    SECURITY = "security"
    ERROR = "error"
    SYSTEM = "system"


class EventAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    RESTORE = "restore"
    HARD_DELETE = "hard_delete"
    LOGIN = "login"
    LOGOUT = "logout"
    SESSION_REVOKED = "session_revoked"
    PASSWORD_CHANGE = "password_change"
    ACCESS_DENIED = "access_denied"
    ERROR = "error"
    SYSTEM = "system"


class Event(Model):
    """Registro append-only, numerado y firmado en cadena. `actor_id` no es clave foránea."""

    id = fields.UUIDField(primary_key=True, default=uuid7)
    sequence = fields.BigIntField(unique=True)

    category = fields.CharEnumField(EventCategory, max_length=20, db_index=True)
    action = fields.CharEnumField(EventAction, max_length=30, db_index=True)
    severity = fields.CharField(max_length=10, default="info")
    message = fields.TextField()

    actor_id = fields.UUIDField(null=True, db_index=True)
    actor_username = fields.CharField(max_length=50, null=True, db_index=True)
    actor_role_id = fields.UUIDField(null=True, db_index=True)

    entity_type = fields.CharField(max_length=50, null=True, db_index=True)
    entity_id = fields.CharField(max_length=50, null=True, db_index=True)
    entity_label = fields.CharField(max_length=255, null=True)
    changes = fields.JSONField(null=True)
    snapshot = fields.JSONField(null=True)

    error_code = fields.CharField(max_length=20, null=True, db_index=True)
    status_code = fields.IntField(null=True)
    permission_id = fields.IntField(null=True, db_index=True)
    method = fields.CharField(max_length=10, null=True)
    path = fields.CharField(max_length=255, null=True)
    request_id = fields.CharField(max_length=36, null=True, db_index=True)
    ip = fields.CharField(max_length=45, null=True)
    user_agent = fields.CharField(max_length=255, null=True)
    context = fields.JSONField(null=True)

    prev_hash = fields.CharField(max_length=64, null=True)
    hash = fields.CharField(max_length=64, default="")

    class Meta(Model.Meta):
        table = "events"
        ordering = ["-id"]

    @property
    def created_at(self) -> datetime:
        return time_of(self.id)

    def payload(self) -> str:
        """Todos los campos, en JSON estable: lo que se firma."""
        data = {
            "id": str(self.id),
            "sequence": self.sequence,
            "category": str(self.category),
            "action": str(self.action),
            "severity": self.severity,
            "message": self.message,
            "actor_id": str(self.actor_id) if self.actor_id else None,
            "actor_username": self.actor_username,
            "actor_role_id": str(self.actor_role_id) if self.actor_role_id else None,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "entity_label": self.entity_label,
            "changes": self.changes,
            "snapshot": self.snapshot,
            "error_code": self.error_code,
            "status_code": self.status_code,
            "permission_id": self.permission_id,
            "method": self.method,
            "path": self.path,
            "request_id": self.request_id,
            "ip": self.ip,
            "user_agent": self.user_agent,
            "context": self.context,
        }
        return json.dumps(data, sort_keys=True, default=str, ensure_ascii=False)

    def compute_hash(self) -> str:
        """Firma HMAC de la fila encadenada con la anterior."""
        message = f"{self.prev_hash or ''}|{self.payload()}"
        return hmac.new(settings.key("audit"), message.encode(), hashlib.sha256).hexdigest()

    def is_intact(self) -> bool:
        return hmac.compare_digest(self.hash, self.compute_hash())

    async def delete(self, using_db: BaseDBAsyncClient | None = None) -> None:
        """Prohibido."""
        raise RuntimeError("El registro de eventos no se puede borrar.")


class EventChain(Model):
    """Cabeza de la cadena: último número y última firma. Se bloquea al escribir."""

    id = fields.IntField(primary_key=True)
    sequence = fields.BigIntField(default=0)
    last_hash = fields.CharField(max_length=64, null=True)

    class Meta(Model.Meta):
        table = "event_chain"
