from collections.abc import Awaitable, Callable
from uuid import uuid7

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.context import RequestContext, printable, set_context

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Abre el contexto de la petición y devuelve su request_id (UUIDv7)."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = str(uuid7())
        set_context(
            RequestContext(
                request_id=request_id,
                method=request.method,
                path=printable(request.url.path),
                ip=request.client.host if request.client else "",
                user_agent=request.headers.get("user-agent", ""),
            )
        )
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
