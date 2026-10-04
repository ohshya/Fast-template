from dataclasses import replace
from typing import Any

from fastapi import APIRouter, Path, Request
from tortoise import connections

from app.core import security
from app.core.dependencies import requires
from app.core.errors import CATALOG, AppError, Err
from app.core.models.user import Users
from app.core.permissions import PERMISSIONS, Scope, permission
from app.core.schemas import validators
from app.core.services import auth as auth_service
from app.settings import settings

GROUP = "Sistema"
HEALTH = permission(1001, "system.health", GROUP, "Consultar el estado del servidor", Scope.PUBLIC)
INFO = permission(
    1002, "system.info", GROUP, "Ver información básica de la API", Scope.AUTHENTICATED
)
PERMISSION_CATALOG = permission(
    1003, "system.permissions", GROUP, "Listar el catálogo de permisos", Scope.AUTHENTICATED
)
ERROR_CATALOG = permission(1004, "system.errors", GROUP, "Listar el catálogo de errores")
TEST_ERROR = permission(1005, "system.test_error", GROUP, "Provocar errores de prueba", Scope.DEV)

router = APIRouter(prefix="/system", tags=["Sistema"])


@router.get("/health")
async def health(_public: None = requires(HEALTH)) -> dict[str, Any]:
    """Estado del servidor y de la base de datos; 503 si la base no responde."""
    try:
        await connections.get("default").execute_query("SELECT 1")
    except Exception as exc:
        raise AppError(Err.DATABASE_ERROR, log_message=f"Health check fallido: {exc}") from exc
    return {"status": "up", "database": "up"}


@router.get("/info")
async def info(user: Users = requires(INFO)) -> dict[str, Any]:
    """Configuración y políticas vigentes."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "debug": settings.debug,
        "access_expire_minutes": security.ACCESS_MINUTES,
        "refresh_expire_days": security.REFRESH_DAYS,
        "max_sessions_per_user": auth_service.MAX_SESSIONS_PER_USER,
        "password_min_length": validators.PASSWORD_MIN_LENGTH,
        "login_attempts": auth_service.LOGIN_ATTEMPTS,
        "login_attempts_per_ip": auth_service.LOGIN_ATTEMPTS_PER_IP,
        "login_window_seconds": auth_service.LOGIN_WINDOW_SECONDS,
    }


@router.get("/permissions")
async def list_permissions(
    request: Request, user: Users = requires(PERMISSION_CATALOG)
) -> list[dict[str, Any]]:
    """Catálogo de permisos con su endpoint y si el usuario lo tiene."""
    routes: dict[int, str] = getattr(request.app.state, "route_map", {})
    catalog: list[dict[str, Any]] = []
    for item in sorted(PERMISSIONS.values(), key=lambda value: value.id):
        catalog.append(
            {
                "id": item.id,
                "key": item.key,
                "group": item.group,
                "description": item.description,
                "scope": item.scope,
                "assignable": item.assignable,
                "endpoint": routes.get(item.id),
                "granted": await user.can(item),
            }
        )
    return catalog


@router.get("/errors")
async def list_errors(user: Users = requires(ERROR_CATALOG)) -> list[dict[str, Any]]:
    """Catálogo de errores."""
    return [
        {
            "code": spec.code,
            "status": spec.status,
            "message": spec.message,
            "toast": spec.toast,
            "severity": spec.severity,
            "persist": spec.persist,
            "hint": spec.hint,
        }
        for spec in sorted(CATALOG.values(), key=lambda item: item.code)
    ]


@router.get("/test-error/{status_code}")
async def test_error(
    status_code: int = Path(ge=100, le=599),
    toast: bool = True,
    user: Users = requires(TEST_ERROR),
) -> dict[str, Any]:
    """Provoca un error de prueba; con 500 lanza una excepción real."""
    if status_code == 500:
        raise RuntimeError("Excepción no controlada de prueba")
    if status_code >= 400:
        raise AppError(
            replace(Err.TEST_ERROR, status=status_code),
            toast=toast,
            details={"status_code": status_code},
            log_message=f"Error de prueba solicitado con status {status_code}",
        )
    return {"status": "ok", "detail": "No se generó ningún error"}
