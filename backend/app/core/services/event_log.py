import json
from typing import Any
from uuid import UUID

from tortoise import connections
from tortoise.transactions import in_transaction

from app.core.context import get_context
from app.core.models.event import CHAIN_ID, Event, EventAction, EventCategory, EventChain


async def ensure_event_chain() -> None:
    """Crea la cabeza de la cadena si no existe."""
    await EventChain.get_or_create(id=CHAIN_ID)


async def event_guards_active() -> bool:
    """Si la base rechaza UPDATE, DELETE y TRUNCATE sobre `events` (triggers activos)."""
    rows = await connections.get("default").execute_query_dict(
        "SELECT count(*) AS active FROM pg_trigger WHERE tgrelid = 'events'::regclass "
        "AND tgname IN ('events_no_change', 'events_no_truncate') AND tgenabled IN ('O', 'A')"
    )
    return rows[0]["active"] == 2


async def install_event_guards() -> None:
    """Instala los triggers de solo añadir de `events` si faltan; si había eventos, lo registra."""
    if await event_guards_active():
        return
    installed = False
    async with in_transaction() as connection:
        await connection.execute_query("SELECT pg_advisory_xact_lock(7343)")
        if not await event_guards_active():
            await connection.execute_script(
                """
                CREATE OR REPLACE FUNCTION events_append_only()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    RAISE EXCEPTION 'El registro de eventos es de solo añadir: no se permite %',
                        TG_OP;
                END
                $$;
                CREATE OR REPLACE TRIGGER events_no_change BEFORE UPDATE OR DELETE ON events
                    FOR EACH ROW EXECUTE FUNCTION events_append_only();
                CREATE OR REPLACE TRIGGER events_no_truncate BEFORE TRUNCATE ON events
                    FOR EACH STATEMENT EXECUTE FUNCTION events_append_only();
                """
            )
            installed = True
    if installed and await Event.all().exists():
        await record_system(
            "Se instalaron los triggers de solo añadir de la tabla events: faltaban o estaban "
            "desactivados",
            severity="warning",
        )


def _fit(column: str, value: str | None) -> str | None:
    """Recorta un texto al ancho de su columna en `events`."""
    field: Any = Event._meta.fields_map[column]
    return value[: field.max_length] if value else value


def _as_json(value: dict[str, Any] | None) -> dict[str, Any] | None:
    return None if value is None else json.loads(json.dumps(value, default=str))


async def record(
    category: EventCategory,
    action: EventAction,
    message: str,
    *,
    severity: str = "info",
    entity_type: str | None = None,
    entity_id: str | UUID | None = None,
    entity_label: str | None = None,
    changes: dict[str, Any] | None = None,
    snapshot: dict[str, Any] | None = None,
    error_code: str | None = None,
    status_code: int | None = None,
    context_data: dict[str, Any] | None = None,
    actor_id: UUID | None = None,
    actor_username: str | None = None,
    actor_role_id: UUID | None = None,
) -> Event:
    """Escribe un evento en la cadena. Único punto de escritura de la tabla."""
    request = get_context()
    async with in_transaction():
        head = await EventChain.select_for_update().get_or_none(id=CHAIN_ID)
        if head is None:
            head = await EventChain.create(id=CHAIN_ID)
        event = Event(
            sequence=head.sequence + 1,
            category=category,
            action=action,
            severity=severity,
            message=message,
            actor_id=actor_id or request.actor_id,
            actor_username=_fit("actor_username", actor_username or request.actor_username),
            actor_role_id=actor_role_id or request.actor_role_id,
            entity_type=_fit("entity_type", entity_type),
            entity_id=_fit("entity_id", str(entity_id) if entity_id is not None else None),
            entity_label=_fit("entity_label", entity_label),
            changes=_as_json(changes),
            snapshot=_as_json(snapshot),
            error_code=_fit("error_code", error_code),
            status_code=status_code,
            permission_id=request.permission_id,
            method=_fit("method", request.method) or None,
            path=_fit("path", request.path) or None,
            request_id=_fit("request_id", request.request_id) or None,
            ip=_fit("ip", request.ip) or None,
            user_agent=_fit("user_agent", request.user_agent) or None,
            context=_as_json(context_data),
            prev_hash=head.last_hash,
        )
        event.hash = event.compute_hash()
        await event.save()
        head.sequence = event.sequence
        head.last_hash = event.hash
        await head.save(update_fields=["sequence", "last_hash"])
    return event


async def record_security(
    action: EventAction, message: str, *, severity: str = "info", **kwargs: Any
) -> Event:
    """Evento de seguridad: sesiones, accesos, contraseñas."""
    return await record(EventCategory.SECURITY, action, message, severity=severity, **kwargs)


async def record_system(message: str, **kwargs: Any) -> Event:
    """Evento de sistema: arranque, scripts."""
    return await record(EventCategory.SYSTEM, EventAction.SYSTEM, message, **kwargs)
