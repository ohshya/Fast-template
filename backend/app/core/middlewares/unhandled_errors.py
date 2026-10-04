from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.errors import handle_error


class UnhandledErrorMiddleware(BaseHTTPMiddleware):
    """Convierte cualquier excepción sin controlar en la respuesta de error estándar."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            return await handle_error(request, exc)
