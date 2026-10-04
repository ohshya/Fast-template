from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import AppError, Err


class BodyLimitMiddleware:
    """Rechaza con 413 los cuerpos de más de `limit` bytes sin leerlos enteros en memoria."""

    def __init__(self, app: ASGIApp, limit: int) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length", "")
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            if declared.isdigit() and int(declared) > self.limit:
                raise AppError(Err.PAYLOAD_TOO_LARGE, log_message=f"Content-Length {declared}")
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.limit:
                    raise AppError(Err.PAYLOAD_TOO_LARGE, log_message="Cuerpo demasiado grande")
            return message

        await self.app(scope, limited_receive, send)
