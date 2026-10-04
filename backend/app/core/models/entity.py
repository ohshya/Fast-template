import hashlib
import hmac
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Self, cast
from uuid import UUID, uuid7

from tortoise import fields
from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.manager import Manager
from tortoise.models import Model, ModelMeta
from tortoise.queryset import QuerySet
from tortoise.signals import post_delete, post_save, pre_save
from tortoise.transactions import in_transaction

from app.core.context import get_context
from app.core.models.event import EventAction, EventCategory
from app.core.services.event_log import record
from app.settings import settings

STAMPED_FIELDS = ("updated_at", "updated_by_id")


def _serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (str, int, float, bool, list, dict)) or value is None:
        return value
    return str(value)


def _fingerprint(value: Any) -> str:
    digest = hmac.new(settings.key("fingerprint"), str(value).encode(), hashlib.sha256)
    return "hmac:" + digest.hexdigest()[:16]


def _values(instance: Entity, only: Iterable[str] | None = None) -> dict[str, Any]:
    """Estado del registro para el historial: sin campos ignorados, secretos en huella."""
    ignored = {*STAMPED_FIELDS, *instance.audit_ignore}
    wanted = None if only is None else frozenset(only)
    values: dict[str, Any] = {}
    for name in sorted(instance._meta.db_fields):
        if name in ignored or (wanted is not None and name not in wanted):
            continue
        if not hasattr(instance, name):
            continue
        value = getattr(instance, name)
        values[name] = _fingerprint(value) if name in instance.audit_redact else _serialize(value)
    return values


def _diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {
        name: {"before": before.get(name), "after": after[name]}
        for name in after
        if before.get(name) != after[name]
    }


def _action_for(before: dict[str, Any], after: dict[str, Any]) -> EventAction:
    was_deleted = before.get("deleted_at") is not None
    is_deleted = after.get("deleted_at") is not None
    if is_deleted and not was_deleted:
        return EventAction.DELETE
    if was_deleted and not is_deleted:
        return EventAction.RESTORE
    return EventAction.UPDATE


def _describe(instance: Entity, action: EventAction) -> str:
    verb = {
        EventAction.CREATE: "creó",
        EventAction.UPDATE: "modificó",
        EventAction.DELETE: "eliminó",
        EventAction.RESTORE: "restauró",
        EventAction.HARD_DELETE: "borró definitivamente",
    }[action]
    actor = get_context().actor_username or "El sistema"
    label = instance.audit_label() or instance.pk
    return f"{actor} {verb} '{label}' en {instance.entity_name()}"


async def _pre_save(
    sender: type[Entity],
    instance: Entity,
    using_db: BaseDBAsyncClient | None,
    update_fields: Iterable[str] | None,
) -> None:
    """Rellena la autoría y calcula el diff de lo que se va a guardar contra la fila actual."""
    actor_id = get_context().actor_id
    previous = None
    if instance._saved_in_db:
        previous = (
            await QuerySet(sender)
            .using_db(using_db)
            .filter(pk=instance.pk)
            .select_for_update()
            .first()
        )

    instance.audit_snapshot = None
    if previous is None:
        instance.created_by_id = instance.created_by_id or actor_id
        instance.updated_by_id = actor_id
        instance.audit_action = EventAction.CREATE
        instance.audit_changes = None
        return

    instance.updated_by_id = actor_id
    before = _values(previous)
    after = _values(instance, update_fields or None)
    merged = {**before, **after}
    instance.audit_action = _action_for(before, merged)
    instance.audit_changes = _diff(before, after)
    instance.audit_snapshot = merged


async def _post_save(
    sender: type[Entity],
    instance: Entity,
    created: bool,
    using_db: BaseDBAsyncClient | None,
    update_fields: list[str] | None,
) -> None:
    """Escribe el evento del cambio, si lo hubo."""
    action = instance.audit_action
    changes = instance.audit_changes
    if action is None:
        return
    if action is not EventAction.CREATE and not changes:
        return

    await record(
        EventCategory.DOMAIN,
        action,
        _describe(instance, action),
        entity_type=instance.entity_name(),
        entity_id=str(instance.pk),
        entity_label=instance.audit_label(),
        changes=changes,
        snapshot=instance.audit_snapshot or _values(instance),
    )


async def _post_delete(
    sender: type[Entity], instance: Entity, using_db: BaseDBAsyncClient | None
) -> None:
    """Deja constancia del borrado físico."""
    await record(
        EventCategory.DOMAIN,
        EventAction.HARD_DELETE,
        _describe(instance, EventAction.HARD_DELETE),
        severity="warning",
        entity_type=instance.entity_name(),
        entity_id=str(instance.pk),
        entity_label=instance.audit_label(),
        snapshot=_values(instance),
    )


class SoftDeleteManager(Manager):
    """Manager por defecto: esconde lo eliminado."""

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(deleted_at=None)


class EntityMeta(ModelMeta):
    """Da a cada entidad su manager, su Meta propia y el historial automático."""

    def __new__(cls, name: str, bases: tuple[type, ...], attrs: dict[str, Any]) -> ModelMeta:
        declared = attrs.get("Meta")
        own = (
            {key: value for key, value in vars(declared).items() if not key.startswith("__")}
            if declared
            else {}
        )
        parent = next(
            vars(klass)["Meta"] for base in bases for klass in base.__mro__ if "Meta" in vars(klass)
        )
        attrs["Meta"] = type(
            "Meta",
            (parent,),
            {**own, "abstract": own.get("abstract", False), "manager": SoftDeleteManager()},
        )
        entity = cast(type[Model], super().__new__(cls, name, bases, attrs))
        if not entity._meta.abstract and getattr(entity, "audit", True):
            pre_save(entity)(_pre_save)
            post_save(entity)(_post_save)
            post_delete(entity)(_post_delete)
        return cast(ModelMeta, entity)


class Entity(Model, metaclass=EntityMeta):
    """Base de las tablas: UUIDv7, autoría, borrado reversible e historial."""

    id = fields.UUIDField(primary_key=True, default=uuid7)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    created_by_id = fields.UUIDField(null=True)
    updated_by_id = fields.UUIDField(null=True)
    deleted_at = fields.DatetimeField(null=True)
    deleted_by_id = fields.UUIDField(null=True)

    audit: bool = True
    audit_label_field: str = ""
    audit_redact: frozenset[str] = frozenset()
    audit_ignore: frozenset[str] = frozenset()
    audit_action: EventAction | None = None
    audit_changes: dict[str, Any] | None = None
    audit_snapshot: dict[str, Any] | None = None

    class Meta(Model.Meta):
        abstract = True

    @classmethod
    def entity_name(cls) -> str:
        """Nombre del registro en el historial: su tabla."""
        return cls._meta.db_table

    @classmethod
    def with_deleted(cls) -> QuerySet[Self]:
        """Consulta que incluye los eliminados."""
        return QuerySet(cls)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def audit_label(self) -> str | None:
        """Nombre legible del registro en el historial."""
        if not self.audit_label_field:
            return None
        value = getattr(self, self.audit_label_field, None)
        return str(value) if value is not None else None

    async def soft_delete(self) -> None:
        """Elimina de forma reversible."""
        self.deleted_at = datetime.now(UTC)
        self.deleted_by_id = get_context().actor_id
        await self.save(update_fields=["deleted_at", "deleted_by_id", "updated_at"])

    async def restore(self) -> None:
        """Restaura un registro eliminado."""
        self.deleted_at = None
        self.deleted_by_id = None
        await self.save(update_fields=["deleted_at", "deleted_by_id", "updated_at"])

    async def save(
        self,
        using_db: BaseDBAsyncClient | None = None,
        update_fields: Iterable[str] | None = None,
        force_create: bool = False,
        force_update: bool = False,
    ) -> None:
        """Guarda la fila y su evento en una sola transacción; sellan `updated_at` y el autor."""
        fields = list(dict.fromkeys([*update_fields, *STAMPED_FIELDS])) if update_fields else None
        for name in STAMPED_FIELDS:
            if fields and not hasattr(self, name):
                setattr(self, name, None)
        async with in_transaction(self._meta.default_connection) as connection:
            await super().save(
                using_db=connection,
                update_fields=fields,
                force_create=force_create,
                force_update=force_update,
            )

    async def hard_delete(self) -> None:
        """Borra la fila de verdad; el borrado y su evento van en una sola transacción."""
        async with in_transaction(self._meta.default_connection) as connection:
            await super().delete(using_db=connection)

    async def delete(self, using_db: BaseDBAsyncClient | None = None) -> None:
        """Prohibido: usa soft_delete() o hard_delete()."""
        raise RuntimeError(
            f"{type(self).__name__}: usa soft_delete() para eliminar o hard_delete() "
            "si de verdad quieres borrar la fila."
        )
