from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.context import WRITE_METHODS, under_api
from app.core.errors import AppError, Err, handle_error
from app.settings import settings


class OriginMiddleware(BaseHTTPMiddleware):
    """Rechaza escrituras cuyo Origin no es el servidor ni está en CORS_ORIGINS (CSRF)."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        origin = request.headers.get("origin")
        if (
            origin
            and request.method in WRITE_METHODS
            and under_api(request.url.path)
            and origin not in settings.cors_origins
            and urlsplit(origin).netloc != request.headers.get("host")
        ):
            return await handle_error(
                request,
                AppError(
                    Err.ORIGIN_NOT_ALLOWED,
                    log_message=f"Escritura desde un origen no permitido: {origin}",
                    details={"origin": origin},
                ),
            )
        return await call_next(request)
