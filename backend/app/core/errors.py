import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from tortoise.exceptions import DoesNotExist, IntegrityError, OperationalError, ValidationError

from app.core.context import get_context, printable
from app.core.models.event import EventAction, EventCategory
from app.core.security import clear_token_cookies
from app.core.services.event_log import record
from app.settings import settings

logger = logging.getLogger("uvicorn.error")

PERSIST_LIMIT = 30
PERSIST_WINDOW_SECONDS = 60.0
_persisted: dict[tuple[str, str], tuple[float, int]] = {}


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class ErrorSpec:
    """Error del catálogo. `persist`: se guarda como evento. `hint`: nota interna."""

    code: str
    status: int
    message: str
    toast: bool = True
    severity: Severity = Severity.ERROR
    persist: bool = False
    hint: str = ""


class Err:
    """Catálogo de errores."""

    UNEXPECTED = ErrorSpec(
        "SYS_500",
        500,
        "Ha ocurrido un error inesperado en el servidor.",
        severity=Severity.CRITICAL,
        persist=True,
        hint="Excepción no controlada; el traceback queda en el contexto del evento.",
    )
    NOT_FOUND = ErrorSpec(
        "SYS_404",
        404,
        "El recurso solicitado no existe.",
        severity=Severity.WARNING,
    )
    METHOD_NOT_ALLOWED = ErrorSpec(
        "SYS_405",
        405,
        "El método utilizado no está permitido en esta ruta.",
        severity=Severity.WARNING,
    )
    DUPLICATED = ErrorSpec(
        "SYS_409",
        409,
        "Ya existe un registro con esos datos.",
        severity=Severity.WARNING,
        hint="Lo lanza Resource al comprobar los campos únicos; `fields` dice cuáles.",
    )
    RELATION_CONFLICT = ErrorSpec(
        "SYS_REL",
        409,
        "El registro está en uso por otros registros.",
        severity=Severity.WARNING,
        hint="IntegrityError de clave foránea: on_delete=RESTRICT o clave inexistente.",
    )
    CONFLICT_RETRY = ErrorSpec(
        "SYS_CONC",
        409,
        "Otra operación modificó los mismos datos a la vez. Inténtalo de nuevo.",
        severity=Severity.WARNING,
        hint="PostgreSQL abortó la transacción: bloqueo cruzado (40P01) o serialización (40001).",
    )
    RATE_LIMITED = ErrorSpec(
        "SYS_429",
        429,
        "Demasiadas peticiones. Intenta de nuevo en unos segundos.",
        severity=Severity.WARNING,
        persist=True,
    )
    DATABASE_ERROR = ErrorSpec(
        "SYS_503",
        503,
        "La base de datos no está disponible en este momento.",
        severity=Severity.CRITICAL,
        persist=True,
    )
    TEST_ERROR = ErrorSpec(
        "SYS_TEST",
        500,
        "Error de prueba generado a propósito.",
        severity=Severity.INFO,
        hint="Solo lo lanza el endpoint /system/test-error.",
    )

    VALIDATION = ErrorSpec(
        "VAL_422",
        422,
        "Los datos enviados no son válidos.",
        severity=Severity.WARNING,
    )
    RELATED_NOT_FOUND = ErrorSpec(
        "VAL_REL",
        422,
        "Uno de los registros relacionados no existe.",
        severity=Severity.WARNING,
        hint="Lo lanza Resource al comprobar las claves foráneas; `fields` dice cuáles.",
    )

    INVALID_CREDENTIALS = ErrorSpec(
        "AUT_001",
        401,
        "Usuario o contraseña incorrectos.",
        severity=Severity.WARNING,
        persist=True,
    )
    NOT_AUTHENTICATED = ErrorSpec(
        "AUT_002",
        401,
        "Necesitas iniciar sesión para continuar.",
        toast=False,
        severity=Severity.INFO,
    )
    SESSION_EXPIRED = ErrorSpec(
        "AUT_003",
        401,
        "Tu sesión ha expirado. Inicia sesión de nuevo.",
        severity=Severity.INFO,
    )
    INVALID_TOKEN = ErrorSpec(
        "AUT_004",
        401,
        "Tu sesión no es válida. Inicia sesión de nuevo.",
        severity=Severity.WARNING,
        persist=True,
    )
    SESSION_NOT_FOUND = ErrorSpec(
        "AUT_005",
        404,
        "La sesión indicada no existe.",
        severity=Severity.WARNING,
    )
    USER_INACTIVE = ErrorSpec(
        "AUT_006",
        403,
        "Tu cuenta está desactivada. Contacta con un administrador.",
        persist=True,
    )

    PERMISSION_DENIED = ErrorSpec(
        "PRM_001",
        403,
        "No tienes permisos para realizar esta acción.",
        persist=True,
    )
    DEV_ONLY = ErrorSpec(
        "PRM_002",
        403,
        "Esta acción está reservada a los desarrolladores del sistema.",
        persist=True,
    )
    ORIGIN_NOT_ALLOWED = ErrorSpec(
        "PRM_003",
        403,
        "La solicitud viene de un sitio web no autorizado.",
        persist=True,
        hint="Escritura con cabecera Origin que no es el propio servidor ni está en CORS_ORIGINS.",
    )
    PRIVILEGE_ESCALATION = ErrorSpec(
        "PRM_004",
        403,
        "No puedes conceder ni gestionar más permisos de los que tú tienes.",
        persist=True,
        hint="Un usuario que no es dev solo asigna, edita o gestiona lo que cabe en sus permisos.",
    )

    USER_NOT_FOUND = ErrorSpec(
        "USR_001",
        404,
        "El usuario solicitado no existe.",
        severity=Severity.WARNING,
    )
    CANNOT_MODIFY_SELF = ErrorSpec(
        "USR_003",
        409,
        "No puedes realizar esta acción sobre tu propia cuenta.",
        severity=Severity.WARNING,
    )
    CANNOT_ELEVATE_TO_DEV = ErrorSpec(
        "USR_004",
        403,
        "Solo un desarrollador puede otorgar o quitar el rol de desarrollador.",
        persist=True,
    )
    DEV_ACCOUNT_PROTECTED = ErrorSpec(
        "USR_005",
        403,
        "Solo un desarrollador puede modificar la cuenta de otro desarrollador.",
        persist=True,
        hint="Protege las cuentas dev de un rol con permisos de gestión de usuarios.",
    )

    ROLE_NOT_FOUND = ErrorSpec(
        "ROL_001",
        404,
        "El rol solicitado no existe.",
        severity=Severity.WARNING,
    )
    ROLE_IN_USE = ErrorSpec(
        "ROL_003",
        409,
        "No se puede eliminar un rol que aún tiene usuarios asignados.",
        severity=Severity.WARNING,
    )
    UNKNOWN_PERMISSION = ErrorSpec(
        "ROL_004",
        422,
        "El rol incluye permisos que no existen en el sistema.",
        severity=Severity.WARNING,
    )

    EVENT_NOT_FOUND = ErrorSpec(
        "EVT_001",
        404,
        "El evento solicitado no existe.",
        severity=Severity.WARNING,
    )
    RESTORE_NOT_DELETED = ErrorSpec(
        "SYS_RESTORE",
        409,
        "El registro que intentas restaurar no está eliminado.",
        severity=Severity.WARNING,
    )

    IDEMPOTENCY_IN_PROGRESS = ErrorSpec(
        "IDM_001",
        409,
        "Esta misma solicitud todavía se está procesando.",
        toast=False,
        severity=Severity.WARNING,
        hint="Llegó una copia idéntica y la original tardó más de 15 s en terminar.",
    )
    IDEMPOTENCY_KEY_REUSED = ErrorSpec(
        "IDM_002",
        422,
        "La clave de idempotencia ya se usó con otra solicitud.",
        severity=Severity.WARNING,
        hint="El cliente repitió Idempotency-Key con otro método, ruta, query o cuerpo.",
    )
    IDEMPOTENCY_KEY_INVALID = ErrorSpec(
        "IDM_003",
        422,
        "La clave de idempotencia no es válida.",
        severity=Severity.WARNING,
        hint="Idempotency-Key debe tener entre 1 y 255 caracteres.",
    )
    PAYLOAD_TOO_LARGE = ErrorSpec(
        "SYS_413",
        413,
        "La solicitud es demasiado grande.",
        severity=Severity.WARNING,
        hint="Supera el límite de BodyLimitMiddleware en main.py; ponlo también en el proxy.",
    )


def _build_catalog() -> dict[str, ErrorSpec]:
    """Errores por código; falla si un código se repite."""
    catalog: dict[str, ErrorSpec] = {}
    for name, spec in vars(Err).items():
        if not isinstance(spec, ErrorSpec):
            continue
        if spec.code in catalog:
            raise RuntimeError(f"Código de error duplicado: {spec.code} (en Err.{name})")
        catalog[spec.code] = spec
    return catalog


CATALOG: dict[str, ErrorSpec] = _build_catalog()


def register_error(spec: ErrorSpec) -> ErrorSpec:
    """Añade un error propio al catálogo. Falla si el código ya existe."""
    if spec.code in CATALOG:
        raise RuntimeError(f"Código de error duplicado: {spec.code}")
    CATALOG[spec.code] = spec
    return spec


class AppError(Exception):
    """Única excepción que se lanza a mano: `raise AppError(Err.X, fields=..., details=...)`."""

    def __init__(
        self,
        spec: ErrorSpec,
        *,
        details: dict[str, Any] | None = None,
        fields: dict[str, str] | None = None,
        log_message: str | None = None,
        toast: bool | None = None,
        persist: bool | None = None,
    ) -> None:
        self.spec = spec
        self.details = details or {}
        self.fields = fields
        self.log_message = printable(log_message or spec.message)
        self.toast = spec.toast if toast is None else toast
        self.persist = spec.persist if persist is None else persist
        super().__init__(f"{spec.code}: {self.log_message}")


def _from_validation(exc: RequestValidationError) -> AppError:
    """Convierte los errores de Pydantic en un AppError con detalle por campo, en español."""
    spanish: dict[str, Callable[[dict[str, Any]], str]] = {
        "missing": lambda ctx: "Este campo es obligatorio",
        "string_type": lambda ctx: "Debe ser un texto",
        "string_too_short": lambda ctx: f"Mínimo {ctx['min_length']} caracteres",
        "string_too_long": lambda ctx: f"Máximo {ctx['max_length']} caracteres",
        "string_pattern_mismatch": lambda ctx: "Formato no válido",
        "too_short": lambda ctx: f"Mínimo {ctx['min_length']} elementos",
        "too_long": lambda ctx: f"Máximo {ctx['max_length']} elementos",
        "greater_than": lambda ctx: f"Debe ser mayor que {ctx['gt']}",
        "greater_than_equal": lambda ctx: f"Debe ser mayor o igual que {ctx['ge']}",
        "less_than": lambda ctx: f"Debe ser menor que {ctx['lt']}",
        "less_than_equal": lambda ctx: f"Debe ser menor o igual que {ctx['le']}",
        "int_type": lambda ctx: "Debe ser un número entero",
        "int_parsing": lambda ctx: "Debe ser un número entero",
        "int_from_float": lambda ctx: "Debe ser un número entero",
        "float_type": lambda ctx: "Debe ser un número",
        "float_parsing": lambda ctx: "Debe ser un número",
        "decimal_type": lambda ctx: "Debe ser un número decimal",
        "decimal_parsing": lambda ctx: "Debe ser un número decimal",
        "decimal_max_digits": lambda ctx: f"Máximo {ctx['max_digits']} dígitos",
        "decimal_max_places": lambda ctx: f"Máximo {ctx['decimal_places']} decimales",
        "decimal_whole_digits": lambda ctx: f"Máximo {ctx['whole_digits']} dígitos enteros",
        "bool_type": lambda ctx: "Debe ser verdadero o falso",
        "bool_parsing": lambda ctx: "Debe ser verdadero o falso",
        "uuid_type": lambda ctx: "Identificador no válido",
        "uuid_parsing": lambda ctx: "Identificador no válido",
        "date_type": lambda ctx: "Fecha no válida",
        "date_parsing": lambda ctx: "Fecha no válida",
        "date_from_datetime_parsing": lambda ctx: "Fecha no válida",
        "datetime_type": lambda ctx: "Fecha y hora no válidas",
        "datetime_parsing": lambda ctx: "Fecha y hora no válidas",
        "datetime_from_date_parsing": lambda ctx: "Fecha y hora no válidas",
        "time_type": lambda ctx: "Hora no válida",
        "time_parsing": lambda ctx: "Hora no válida",
        "timezone_aware": lambda ctx: "La fecha necesita zona horaria",
        "timezone_naive": lambda ctx: "La fecha no debe llevar zona horaria",
        "enum": lambda ctx: "Valor no permitido",
        "literal_error": lambda ctx: "Valor no permitido",
        "list_type": lambda ctx: "Debe ser una lista",
        "dict_type": lambda ctx: "Debe ser un objeto",
        "model_type": lambda ctx: "Debe ser un objeto",
        "model_attributes_type": lambda ctx: "Debe ser un objeto",
        "json_invalid": lambda ctx: "JSON no válido",
        "extra_forbidden": lambda ctx: "Campo no permitido",
        "url_parsing": lambda ctx: "URL no válida",
    }

    def name_of(error: Any) -> str:
        """Campo del error; en la query no se numeran los elementos de una lista."""
        parts = error["loc"][1:]
        return (
            ".".join(
                str(part)
                for part in parts
                if error["loc"][0] != "query" or not isinstance(part, int)
            )
            or "body"
        )

    fields = {
        name_of(error): spanish[error["type"]](error.get("ctx") or {})
        if error["type"] in spanish
        else error["msg"].removeprefix("Value error, ").removeprefix("Assertion failed, ")
        for error in exc.errors()
    }
    return AppError(Err.VALIDATION, fields=fields, log_message=f"Validación fallida: {fields}")


def _from_http(exc: StarletteHTTPException) -> AppError:
    """Traduce los errores que genera Starlette por su cuenta."""
    known = {
        401: Err.NOT_AUTHENTICATED,
        403: Err.PERMISSION_DENIED,
        404: Err.NOT_FOUND,
        405: Err.METHOD_NOT_ALLOWED,
        422: Err.VALIDATION,
        429: Err.RATE_LIMITED,
    }
    spec = known.get(exc.status_code) or ErrorSpec(
        code=f"HTTP_{exc.status_code}",
        status=exc.status_code,
        message="No se pudo completar la solicitud.",
        severity=Severity.WARNING if exc.status_code < 500 else Severity.ERROR,
        persist=exc.status_code >= 500,
    )
    return AppError(spec, log_message=str(exc.detail))


def _from_unknown(exc: Exception) -> AppError:
    """Traduce fallos de base de datos y cualquier excepción no prevista."""
    if isinstance(exc, DoesNotExist):
        return AppError(Err.NOT_FOUND, log_message=str(exc))
    if isinstance(exc, ValidationError):
        return AppError(Err.VALIDATION, log_message=f"Validación del modelo: {exc}")
    sqlstate = getattr(exc, "sqlstate", None) or getattr(
        exc.args[0] if exc.args else None, "sqlstate", None
    )
    if sqlstate in ("40P01", "40001"):
        return AppError(Err.CONFLICT_RETRY, log_message=f"Transacción abortada: {exc}")
    if sqlstate in ("23001", "23503"):
        return AppError(Err.RELATION_CONFLICT, log_message=f"Clave foránea: {exc}")
    if sqlstate == "23505":
        return AppError(Err.DUPLICATED, log_message=f"Conflicto de unicidad: {exc}", persist=True)
    if isinstance(sqlstate, str) and sqlstate.startswith("22"):
        return AppError(Err.VALIDATION, log_message=f"Dato que PostgreSQL rechaza: {exc}")
    if isinstance(exc, IntegrityError):
        return AppError(Err.UNEXPECTED, log_message=f"IntegrityError: {exc}")
    if isinstance(exc, OperationalError):
        return AppError(Err.DATABASE_ERROR, log_message=str(exc))
    return AppError(Err.UNEXPECTED, log_message=f"{type(exc).__name__}: {exc}")


def normalize(exc: Exception) -> tuple[AppError, bool]:
    """Convierte cualquier excepción en AppError; el bool dice si fue imprevista."""
    while isinstance(exc, ExceptionGroup) and len(exc.exceptions) == 1:
        exc = exc.exceptions[0]
    if isinstance(exc, AppError):
        return exc, False
    if isinstance(exc, RequestValidationError):
        return _from_validation(exc), False
    if isinstance(exc, StarletteHTTPException):
        return _from_http(exc), False
    return _from_unknown(exc), True


def _may_persist(ip: str, code: str) -> bool:
    """Limita los eventos de error por IP y código: nadie puede llenar el registro a peticiones."""
    now = monotonic()
    if len(_persisted) > 10_000:
        for key, (started, _) in list(_persisted.items()):
            if now - started > PERSIST_WINDOW_SECONDS:
                del _persisted[key]
    started, count = _persisted.get((ip, code), (now, 0))
    if now - started > PERSIST_WINDOW_SECONDS:
        started, count = now, 0
    _persisted[(ip, code)] = (started, count + 1)
    if count == PERSIST_LIMIT:
        logger.warning("Se dejan de guardar eventos %s de %s: demasiados en poco tiempo", code, ip)
    return count < PERSIST_LIMIT


async def handle_error(request: Request, exc: Exception) -> JSONResponse:
    """Punto único por el que salen todos los errores de la API."""
    error, unexpected = normalize(exc)
    spec = error.spec
    context = get_context()

    logger.log(
        logging.getLevelNamesMapping()[spec.severity.upper()],
        "%s %s -> %s %s | %s | request_id=%s",
        request.method,
        context.path,
        spec.status,
        spec.code,
        error.log_message,
        context.request_id,
        exc_info=exc if spec is Err.UNEXPECTED else None,
    )

    event_id: str | None = None
    if error.persist and _may_persist(context.ip, spec.code):
        detalle: dict[str, Any] = {"details": error.details}
        if error.fields:
            detalle["fields"] = error.fields
        if unexpected:
            detalle["exception"] = printable(f"{type(exc).__name__}: {exc}")
        seguridad = spec.status in (401, 403)
        try:
            event = await record(
                EventCategory.SECURITY if seguridad else EventCategory.ERROR,
                EventAction.ACCESS_DENIED if seguridad else EventAction.ERROR,
                error.log_message,
                severity=str(spec.severity),
                error_code=spec.code,
                status_code=spec.status,
                context_data=detalle,
            )
            event_id = str(event.id)
        except Exception:
            logger.exception("No se pudo guardar el evento del error %s", spec.code)

    payload: dict[str, Any] = {
        "code": spec.code,
        "message": spec.message,
        "toast": error.toast,
        "severity": str(spec.severity),
        "request_id": context.request_id,
        "event_id": event_id,
        "fields": error.fields,
        "details": error.details,
    }
    if settings.debug and unexpected:
        payload["debug"] = f"{type(exc).__name__}: {exc}"

    response = JSONResponse(status_code=spec.status, content={"error": payload})
    if getattr(request.state, "clear_auth_cookies", False):
        clear_token_cookies(response)
    return response
