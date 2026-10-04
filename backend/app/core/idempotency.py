from fastapi_idempotency import (
    ConflictingRequestError,
    IdempotencyError,
    InvalidKeyError,
    PayloadTooLargeError,
    RequestInProgressError,
)
from fastapi_idempotency.stores.tortoise import TortoiseStore
from starlette.requests import Request
from starlette.responses import Response

from app.core.errors import AppError, Err, handle_error
from app.core.models.session import UserSession
from app.core.security import ACCESS_COOKIE, TokenError, read_token

store = TortoiseStore()


def _session_of(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return str(read_token(token, "access").session_id)
    except TokenError:
        return None


async def scope(request: Request) -> str:
    """La sesión abierta si el token de acceso es legible (estable aunque rote); si no, la IP."""
    session = _session_of(request.cookies.get(ACCESS_COOKIE))
    if session is not None and await UserSession.filter(id=session).exists():
        return f"session:{session}"
    return f"ip:{request.client.host if request.client else ''}"


async def on_error(request: Request, error: IdempotencyError) -> Response:
    """Traduce las excepciones de la librería al catálogo y a la forma propios."""
    spec = {
        InvalidKeyError: Err.IDEMPOTENCY_KEY_INVALID,
        ConflictingRequestError: Err.IDEMPOTENCY_KEY_REUSED,
        RequestInProgressError: Err.IDEMPOTENCY_IN_PROGRESS,
        PayloadTooLargeError: Err.PAYLOAD_TOO_LARGE,
    }.get(type(error), Err.UNEXPECTED)
    return await handle_error(request, AppError(spec, log_message=str(error)))
