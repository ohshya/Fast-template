import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi_idempotency import (
    DEFAULT_HEADER_NAME,
    DEFAULT_REPLAYED_HEADER_NAME,
    IdempotencyMiddleware,
)
from fastapi_pagination import add_pagination
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware import Middleware
from tortoise.contrib.fastapi import RegisterTortoise

from app import registry
from app.core import idempotency
from app.core import registry as core
from app.core.context import API_PREFIX
from app.core.database import TORTOISE_ORM, require_migrations, uses_migrations
from app.core.errors import AppError, handle_error, register_error
from app.core.middlewares.body_limit import BodyLimitMiddleware
from app.core.middlewares.origin import OriginMiddleware
from app.core.middlewares.request_context import REQUEST_ID_HEADER, RequestContextMiddleware
from app.core.middlewares.security_headers import SecurityHeadersMiddleware
from app.core.middlewares.unhandled_errors import UnhandledErrorMiddleware
from app.core.openapi import document_permissions
from app.core.permissions import verify_route_permissions
from app.core.services.event_log import ensure_event_chain, install_event_guards
from app.settings import settings

logger = logging.getLogger("uvicorn.error")

for error in registry.ERRORS:
    register_error(error)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Arranque: tablas (o migraciones), permisos, cabeza de la cadena y protección de eventos."""
    if settings.debug:
        logger.warning(
            "DEBUG=true: documentación abierta, detalle de errores y cookies sin Secure. "
            "En producción pon DEBUG=false."
        )
    async with RegisterTortoise(
        app,
        config=TORTOISE_ORM,
        generate_schemas=not uses_migrations(),
        add_exception_handlers=False,
    ):
        await require_migrations()
        app.state.route_map = verify_route_permissions(app)
        if settings.debug:
            document_permissions(app, app.state.route_map)
        await ensure_event_chain()
        await install_event_guards()
        yield


app = FastAPI(
    title=settings.app_name,
    description="Plantilla FastAPI con errores unificados, permisos por endpoint y auditoría.",
    version=settings.app_version,
    lifespan=lifespan,
    redirect_slashes=False,
    docs_url=(None, "/docs")[settings.debug],
    redoc_url=None,
    openapi_url=(None, "/openapi.json")[settings.debug],
    exception_handlers={
        AppError: handle_error,
        RequestValidationError: handle_error,
        StarletteHTTPException: handle_error,
    },
    middleware=[
        Middleware(SecurityHeadersMiddleware),
        Middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "Accept",
                "Origin",
                REQUEST_ID_HEADER,
                DEFAULT_HEADER_NAME,
            ],
            expose_headers=[REQUEST_ID_HEADER, DEFAULT_REPLAYED_HEADER_NAME, "Content-Disposition"],
        ),
        Middleware(BodyLimitMiddleware, limit=1_048_576),
        Middleware(RequestContextMiddleware),
        Middleware(UnhandledErrorMiddleware),
        Middleware(OriginMiddleware),
        Middleware(
            IdempotencyMiddleware,
            store=idempotency.store,
            scope=idempotency.scope,
            on_error=idempotency.on_error,
            path_prefix=API_PREFIX,
        ),
        *registry.MIDDLEWARES,
    ],
)

for router in [*core.ROUTERS, *registry.ROUTERS]:
    app.include_router(router, prefix=API_PREFIX)

add_pagination(app)
