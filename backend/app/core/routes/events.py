from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from fastapi_pagination import Page
from fastapi_pagination.ext.tortoise import apaginate
from pydantic import AwareDatetime

from app.core.dependencies import requires
from app.core.errors import AppError, Err
from app.core.models.event import Event
from app.core.models.user import Users
from app.core.permissions import permission
from app.core.schemas.event import (
    EventDetailOut,
    EventFilters,
    EventOut,
    EventStats,
    IntegrityReport,
)
from app.core.services.audit import build_events_query, event_stats, verify_chain

GROUP = "Auditoría"
LIST = permission(5001, "events.list", GROUP, "Consultar el registro de eventos")
READ = permission(5002, "events.read", GROUP, "Ver el detalle de un evento")
HISTORY = permission(5003, "events.history", GROUP, "Ver el historial de cambios de un registro")
VERIFY = permission(5004, "events.verify", GROUP, "Verificar la integridad del registro")
STATS = permission(5005, "events.stats", GROUP, "Ver estadísticas de eventos")

router = APIRouter(prefix="/events", tags=["Auditoría"])


@router.get("/", response_model=Page[EventOut])
async def list_events(filters: EventFilters = Depends(), actor: Users = requires(LIST)):
    """Eventos paginados con filtros."""
    query = await build_events_query(filters)
    return await apaginate(query, transformer=lambda rows: [EventOut.of(row) for row in rows])


@router.get("/stats", response_model=EventStats)
async def get_stats(actor: Users = requires(STATS)):
    """Totales por categoría, acción y gravedad."""
    return await event_stats()


@router.get("/verify", response_model=IntegrityReport)
async def verify(
    event_id: UUID | None = None,
    date_from: AwareDatetime | None = None,
    date_to: AwareDatetime | None = None,
    actor: Users = requires(VERIFY),
):
    """Comprueba la cadena entera, un periodo (`date_from`, `date_to`) o un evento (`event_id`)."""
    if event_id and (date_from or date_to):
        raise AppError(Err.VALIDATION, fields={"event_id": "No se combina con un periodo"})
    if date_from and date_to and date_from > date_to:
        raise AppError(Err.VALIDATION, fields={"date_to": "Debe ser posterior a date_from"})
    if event_id and not await Event.filter(id=event_id).exists():
        raise AppError(Err.EVENT_NOT_FOUND, details={"event_id": str(event_id)})
    return await verify_chain(date_from, date_to, event_id)


@router.get("/history/{entity_type}/{entity_id}", response_model=Page[EventDetailOut])
async def entity_history(
    entity_type: Annotated[str, Path(max_length=50)],
    entity_id: Annotated[str, Path(max_length=50)],
    actor: Users = requires(HISTORY),
):
    """Historial paginado de un registro."""
    query = Event.filter(entity_type=entity_type, entity_id=entity_id).order_by("id")
    return await apaginate(
        query, transformer=lambda rows: [EventDetailOut.of_detail(row) for row in rows]
    )


@router.get("/{event_id}", response_model=EventDetailOut)
async def get_event(event_id: UUID, actor: Users = requires(READ)):
    """Detalle de un evento."""
    event = await Event.filter(id=event_id).first()
    if event is None:
        raise AppError(Err.EVENT_NOT_FOUND, details={"event_id": str(event_id)})
    return EventDetailOut.of_detail(event)
