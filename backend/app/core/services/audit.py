from datetime import UTC, datetime, timedelta
from uuid import UUID

from tortoise.expressions import Subquery
from tortoise.functions import Count
from tortoise.queryset import QuerySet
from tortoise.transactions import in_transaction

from app.core.models.event import CHAIN_ID, Event, EventChain, id_at
from app.core.models.user import Users
from app.core.schemas.event import EventFilters, EventStats, IntegrityReport
from app.core.services.event_log import event_guards_active

VERIFY_BATCH = 1000


def _within(
    query: QuerySet[Event], date_from: datetime | None, date_to: datetime | None
) -> QuerySet[Event]:
    """Limita la consulta a un periodo. Las fechas se comparan con el UUIDv7."""
    if date_from:
        query = query.filter(id__gte=id_at(date_from))
    if date_to:
        last_day = min(date_to, datetime(9998, 12, 31, tzinfo=UTC))
        query = query.filter(id__lt=id_at(last_day + timedelta(milliseconds=1)))
    return query


async def build_events_query(filters: EventFilters) -> QuerySet[Event]:
    """Consulta de eventos con los filtros pedidos. Las fechas se comparan con el UUIDv7."""
    query = Event.all()
    exact = {
        "category": filters.category,
        "action": filters.action,
        "severity": filters.severity,
        "actor_id": filters.actor_id,
        "actor_role_id": filters.role_id,
        "entity_type": filters.entity_type,
        "entity_id": filters.entity_id,
        "error_code": filters.error_code,
        "request_id": filters.request_id,
        "permission_id": filters.permission_id,
        "method": filters.method.upper() if filters.method else None,
    }
    for field, value in exact.items():
        if value is not None and value != "":
            query = query.filter(**{field: value})

    partial = {
        "actor_username": filters.actor_username,
        "path": filters.path,
        "ip": filters.ip,
        "message": filters.search,
    }
    for field, value in partial.items():
        if value:
            query = query.filter(**{f"{field}__icontains": value})

    if filters.current_role_id is not None:
        actors = Users.with_deleted().filter(role_id=filters.current_role_id).values("id")
        query = query.filter(actor_id__in=Subquery(actors))
    query = _within(query, filters.date_from, filters.date_to)
    if filters.only_changes:
        query = query.exclude(changes=None)
    return query.order_by("id" if filters.order == "oldest" else "-id")


async def event_stats() -> EventStats:
    """Totales por categoría, acción y gravedad."""

    async def group(field: str) -> dict[str, int]:
        rows = await Event.annotate(total=Count("id")).group_by(field).values(field, "total")
        return {str(row[field]): int(row["total"]) for row in rows}

    last = await Event.all().order_by("-id").first()
    return EventStats(
        total=await Event.all().count(),
        by_category=await group("category"),
        by_action=await group("action"),
        by_severity=await group("severity"),
        last_event_at=last.created_at if last else None,
    )


def _break_in_chain(event: Event, previous: Event | None) -> str | None:
    if not event.is_intact():
        return f"El evento {event.id} no coincide con su firma."
    expected_sequence = previous.sequence + 1 if previous else 1
    expected_prev_hash = previous.hash if previous else None
    if event.sequence != expected_sequence or event.prev_hash != expected_prev_hash:
        return f"La cadena se rompe antes del evento {event.id}: falta algún registro."
    return None


async def verify_chain(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    event_id: UUID | None = None,
) -> IntegrityReport:
    """Verifica toda la cadena, un periodo o un evento sobre una instantánea de la base."""
    async with in_transaction() as connection:
        await connection.execute_query("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        return await _verify(date_from, date_to, event_id)


async def _verify(
    date_from: datetime | None, date_to: datetime | None, event_id: UUID | None
) -> IntegrityReport:
    """Firmas, huecos y enlaces de los eventos pedidos y, si incluyen el último, la cabeza."""
    scoped = bool(date_from or date_to or event_id)
    scope = _within(Event.filter(id=event_id) if event_id else Event.all(), date_from, date_to)
    first = await scope.order_by("sequence").first()
    final = await scope.order_by("-sequence").first()
    low = first.sequence if first else 1
    high = final.sequence if final else 0
    chain = Event.filter(sequence__gte=low, sequence__lte=high)
    total = await chain.count()
    append_only = await event_guards_active()
    link = await Event.filter(sequence=low - 1).first()
    last: Event | None = None
    checked = 0

    def report(intact: bool, detail: str, broken: UUID | None = None) -> IntegrityReport:
        return IntegrityReport(
            total=total,
            checked=checked,
            intact=intact,
            first_broken_id=broken,
            detail=detail,
            append_only=append_only,
        )

    while True:
        after = link.sequence if link else low - 1
        batch = await chain.filter(sequence__gt=after).order_by("sequence").limit(VERIFY_BATCH)
        for event in batch:
            reason = _break_in_chain(event, link)
            if reason:
                return report(False, reason, event.id)
            link = last = event
            checked += 1
        if len(batch) < VERIFY_BATCH:
            break

    tail = await Event.all().order_by("-sequence").first()
    head = await EventChain.get_or_none(id=CHAIN_ID)
    if high == (tail.sequence if tail else 0):
        last_sequence = last.sequence if last else 0
        if head is None:
            return report(False, "Falta la cabeza de la cadena de eventos.")
        if head.sequence != last_sequence or head.last_hash != (last.hash if last else None):
            return report(
                False,
                f"La cabeza de la cadena ({head.sequence}) no coincide con el último evento "
                f"guardado ({last_sequence}): faltan eventos al final o la cabeza fue alterada.",
            )

    if not scoped:
        return report(True, f"La cadena de eventos está intacta. Eventos comprobados: {checked}.")
    if not checked:
        return report(True, "No hay eventos que comprobar.")
    return report(True, f"Firmas y enlaces correctos. Eventos comprobados: {checked}.")
