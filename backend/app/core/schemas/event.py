from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from fastapi import Query
from pydantic import AwareDatetime, BaseModel

from app.core.models.event import EventAction, EventCategory

if TYPE_CHECKING:
    from app.core.models.event import Event


class EventOut(BaseModel):
    id: UUID
    sequence: int
    created_at: datetime
    category: EventCategory
    action: EventAction
    severity: str
    message: str
    actor_id: UUID | None
    actor_username: str | None
    actor_role_id: UUID | None
    entity_type: str | None
    entity_id: str | None
    entity_label: str | None
    changes: dict[str, Any] | None
    error_code: str | None
    status_code: int | None
    permission_id: int | None
    method: str | None
    path: str | None
    request_id: str | None
    ip: str | None

    @classmethod
    def of(cls, event: Event) -> EventOut:
        return cls(
            id=event.id,
            sequence=event.sequence,
            created_at=event.created_at,
            category=event.category,
            action=event.action,
            severity=event.severity,
            message=event.message,
            actor_id=event.actor_id,
            actor_username=event.actor_username,
            actor_role_id=event.actor_role_id,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            entity_label=event.entity_label,
            changes=event.changes,
            error_code=event.error_code,
            status_code=event.status_code,
            permission_id=event.permission_id,
            method=event.method,
            path=event.path,
            request_id=event.request_id,
            ip=event.ip,
        )


class EventDetailOut(EventOut):
    snapshot: dict[str, Any] | None
    context: dict[str, Any] | None
    user_agent: str | None
    prev_hash: str | None
    hash: str
    is_intact: bool

    @classmethod
    def of_detail(cls, event: Event) -> EventDetailOut:
        return cls(
            **EventOut.of(event).model_dump(),
            snapshot=event.snapshot,
            context=event.context,
            user_agent=event.user_agent,
            prev_hash=event.prev_hash,
            hash=event.hash,
            is_intact=event.is_intact(),
        )


class IntegrityReport(BaseModel):
    total: int
    checked: int
    intact: bool
    first_broken_id: UUID | None
    detail: str
    append_only: bool


class EventStats(BaseModel):
    total: int
    by_category: dict[str, int]
    by_action: dict[str, int]
    by_severity: dict[str, int]
    last_event_at: datetime | None


@dataclass
class EventFilters:
    """Filtros combinables del registro de eventos. Las fechas exigen zona horaria."""

    category: EventCategory | None = None
    action: EventAction | None = None
    severity: str | None = Query(None, max_length=10)
    actor_id: UUID | None = None
    actor_username: str | None = Query(None, max_length=50)
    role_id: UUID | None = Query(None, description="Rol del actor al ocurrir el evento")
    current_role_id: UUID | None = Query(None, description="Rol del actor ahora")
    entity_type: str | None = Query(None, max_length=50)
    entity_id: str | None = Query(None, max_length=50)
    error_code: str | None = Query(None, max_length=20)
    request_id: str | None = Query(None, max_length=36)
    permission_id: int | None = None
    method: str | None = Query(None, max_length=10)
    path: str | None = Query(None, max_length=255)
    ip: str | None = Query(None, max_length=45)
    search: str | None = Query(None, max_length=255, description="Texto del mensaje")
    date_from: AwareDatetime | None = None
    date_to: AwareDatetime | None = None
    only_changes: bool = Query(False, description="Solo eventos que modificaron datos")
    order: Literal["recent", "oldest"] = "recent"
