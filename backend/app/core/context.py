from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID

API_PREFIX = "/api"
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def printable(text: str, limit: int = 300) -> str:
    """Recorta un texto del cliente y cambia sus saltos de línea y de control por espacios."""
    text = "".join(char if char.isprintable() else " " for char in text)
    return text if len(text) <= limit else text[:limit] + "…"


def under_api(path: str) -> bool:
    """Si la ruta es `API_PREFIX` o cuelga de él, sin confundir `/apificacion` con `/api`."""
    return path == API_PREFIX or path.startswith(f"{API_PREFIX}/")


@dataclass
class RequestContext:
    request_id: str = ""
    method: str = ""
    path: str = ""
    ip: str = ""
    user_agent: str = ""
    actor_id: UUID | None = None
    actor_username: str | None = None
    actor_role_id: UUID | None = None
    permission_id: int | None = None


_context: ContextVar[RequestContext] = ContextVar("request_context")


def set_context(context: RequestContext) -> None:
    """Abre el contexto de la petición."""
    _context.set(context)


def get_context() -> RequestContext:
    """Contexto actual; uno vacío fuera de una petición."""
    try:
        return _context.get()
    except LookupError:
        return RequestContext(request_id="-", ip="script", user_agent="script")


def set_actor(user_id: UUID, username: str, role_id: UUID | None) -> None:
    """Anota quién hace la petición."""
    context = get_context()
    context.actor_id = user_id
    context.actor_username = username
    context.actor_role_id = role_id


def set_permission(permission_id: int) -> None:
    """Anota el permiso que exige el endpoint."""
    get_context().permission_id = permission_id
