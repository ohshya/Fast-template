# Middlewares (`app/middlewares/`)

Un middleware es código que envuelve **todas** las peticiones: corre antes de
llegar a la ruta y otra vez al salir la respuesta. Sirve para lo transversal:
medir tiempos, añadir cabeceras, registrar accesos, cerrar el acceso a ratos.

Nada se carga solo: cada middleware se registra a mano en la lista `MIDDLEWARES`
de `app/registry.py`, como un objeto `starlette.middleware.Middleware(Clase,
parametro=valor)`. Se aplican en el orden en que los escribas (sección 2).

Los middlewares del sistema están en `app/core/middlewares/`, uno por archivo, se
declaran en `main.py` y no se tocan. `app/core/registry.py` es el registro del
sistema y tampoco se edita:

| Archivo | Qué hace |
|---|---|
| `security_headers.py` | Cabeceras de seguridad en cada respuesta; la API además no se guarda en cachés |
| `body_limit.py` | Rechaza con `413 SYS_413` los cuerpos de más de 1 MiB |
| `request_context.py` | Crea el `request_id` y el contexto de la petición |
| `unhandled_errors.py` | Convierte cualquier excepción sin controlar en la respuesta de error estándar |
| `origin.py` | Rechaza escrituras enviadas desde otras webs (protección CSRF) |

Además de esos, `main.py` monta CORS y la idempotencia (procesar una sola vez una
escritura repetida). Esta última no vive en el proyecto: es la librería instalable
`fastapi-idempotency` (pip), con `app/core/idempotency.py` como puente hacia el
catálogo de errores propio. Ver la sección "Solicitudes repetidas" de `GUIA.md`.

---

## 1. Crear un middleware

Un archivo por middleware, con una sola responsabilidad. Basta con definir la
clase; no hay ninguna variable especial que exportar:

```python
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class ProcessTimeMiddleware(BaseHTTPMiddleware):
    """Añade X-Process-Time-Ms a cada respuesta."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Process-Time-Ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
        return response
```

Guárdalo como `app/middlewares/process_time.py` y regístralo en `app/registry.py`:

```python
from starlette.middleware import Middleware

from app.middlewares.process_time import ProcessTimeMiddleware

MIDDLEWARES: list[Middleware] = [Middleware(ProcessTimeMiddleware)]
```

Reinicia: todas las respuestas llevan ya la cabecera nueva. Con el frontend y el
backend en el mismo origen (el proxy de Vite en desarrollo, `/api` en el mismo
dominio en producción) el navegador la ve sin más.

### Con opciones

Los parámetros se pasan a `Middleware(...)` por nombre y llegan al `__init__` de
la clase después de `app`:

```python
import logging
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.context import get_context

logger = logging.getLogger("uvicorn.error")


class SlowRequestMiddleware(BaseHTTPMiddleware):
    """Avisa en el log de las peticiones que tardan más de `limit_ms`."""

    def __init__(self, app: ASGIApp, limit_ms: int) -> None:
        super().__init__(app)
        self.limit_ms = limit_ms

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        elapsed = (time.perf_counter() - started) * 1000
        if elapsed > self.limit_ms:
            context = get_context()
            logger.warning(
                "%s %s tardó %.0f ms | usuario=%s request_id=%s",
                request.method,
                request.url.path,
                elapsed,
                context.actor_username,
                context.request_id,
            )
        return response
```

```python
MIDDLEWARES: list[Middleware] = [
    Middleware(ProcessTimeMiddleware),
    Middleware(SlowRequestMiddleware, limit_ms=500),
]
```

---

## 2. Dónde se colocan

Los tuyos van **por dentro** de todos los del sistema, justo antes de la ruta:

```
cabeceras de seguridad (security_headers)
  └─ CORS
       └─ límite de cuerpo (body_limit, 1 MiB)
            └─ request_context
                 └─ unhandled_errors
                      └─ origin
                           └─ idempotencia (librería fastapi-idempotency)
                                └─ los tuyos (MIDDLEWARES, en el orden en que los escribas)
                                     └─ la ruta
```

El primero de la lista es el más externo: recibe la petición antes y ve la
respuesta la última. Con `[Middleware(A), Middleware(B)]`, `A` envuelve a `B`.

Consecuencias:

- Cuando corre el tuyo, ya existe el contexto de la petición (`request_id`), ya
  se ha comprobado el origen y, si lees el cuerpo, no pasa de 1 MiB (uno mayor da
  `413 SYS_413`). Si lanzas `AppError(...)` desde tu `dispatch`,
  `unhandled_errors` lo convierte en la respuesta estándar.
- **Aún no se ha identificado al usuario**: el usuario se identifica en la
  dependencia `requires(...)` de cada ruta, que corre después. Para saber quién
  hizo la petición, léelo **después** de `call_next`:

```python
response = await call_next(request)
usuario = get_context().actor_username
```

- Las cabeceras de seguridad se escriben en la capa más externa, al salir la
  respuesta: si tu middleware pone una con el mismo nombre (`X-Frame-Options`,
  `Cache-Control` en `/api`...), prevalece la del sistema.
- Una escritura que el sistema rechaza antes (origen no permitido, cuerpo de más
  de 1 MiB) o una escritura repetida que ya se atendió **no llegan** a tus
  middlewares: la respuesta sale antes.

---

## 3. Lo que ofrece el sistema

```python
from app.core.context import get_context

get_context().request_id
get_context().actor_username
get_context().ip
```

| Dato | Cuándo está |
|---|---|
| `request_id`, `method`, `path`, `ip`, `user_agent` | Siempre |
| `actor_id`, `actor_username`, `actor_role_id` | Después de que `requires(...)` identifique al usuario |
| `permission_id` | Después de `requires(...)` |

Para devolver un error uniforme desde un middleware:

```python
from app.core.errors import AppError, Err, handle_error

return await handle_error(request, AppError(Err.PERMISSION_DENIED))
```

Lanzar la excepción (`raise AppError(...)`) sale igual. Para escribir en la
auditoría, usa `record_security(...)` (`app/core/services/event_log.py`).

---

## 4. Ejemplo: modo solo lectura

Durante una migración conviene cerrar las escrituras sin apagar el servicio. Este
middleware las rechaza con un error propio, salvo las de sesión para que se pueda
seguir entrando y saliendo. El error va en `app/errors/maintenance.py`:

```python
from app.core.errors import ErrorSpec, Severity

READ_ONLY = ErrorSpec(
    "MNT_001",
    503,
    "El sistema está en mantenimiento y solo admite consultas.",
    severity=Severity.WARNING,
)
```

Y el middleware, en `app/middlewares/read_only.py`:

```python
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.context import WRITE_METHODS
from app.core.errors import AppError, handle_error
from app.errors.maintenance import READ_ONLY

SESSION_PATHS = frozenset({"/api/auth/login", "/api/auth/refresh", "/api/auth/logout"})


class ReadOnlyMiddleware(BaseHTTPMiddleware):
    """Rechaza las escrituras con 503, salvo las de sesión, mientras `enabled` sea verdadero."""

    def __init__(self, app: ASGIApp, enabled: bool) -> None:
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        writing = request.method in WRITE_METHODS and request.url.path not in SESSION_PATHS
        if self.enabled and writing:
            return await handle_error(request, AppError(READ_ONLY))
        return await call_next(request)
```

Se registran los dos en `app/registry.py`. El error va en `ERRORS`, o no saldría en
el catálogo (ver `app/errors/steps.md`); para cerrar las escrituras basta con
poner `enabled=True` y reiniciar:

```python
from app.errors import maintenance as maintenance_errors
from app.middlewares.read_only import ReadOnlyMiddleware

MIDDLEWARES: list[Middleware] = [Middleware(ReadOnlyMiddleware, enabled=False)]
ERRORS: list[ErrorSpec] = [maintenance_errors.READ_ONLY]
```

Limitar el tamaño del cuerpo y añadir cabeceras de seguridad ya lo hace el
sistema (`body_limit.py`, `security_headers.py`): no hace falta escribirlos.

---

## 5. Cuándo NO usar un middleware

| Necesitas... | Usa |
|---|---|
| Comprobar permisos de un endpoint | `requires(PERMISO)` en la ruta |
| Validar los datos de entrada | Un esquema (`app/schemas/`) |
| Una regla de negocio | Un servicio (`app/services/`) |
| Algo que solo afecta a una ruta | Una dependencia de FastAPI (`Depends`) en esa ruta |
| Guardar datos en la base de datos por cada petición | Con cuidado: cada middleware suma tiempo a **todas** las peticiones |

---

## 6. Errores frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| El middleware no hace nada | No está en `MIDDLEWARES` de `app/registry.py` | Añade `Middleware(MiClase)` |
| `TypeError: cannot unpack non-iterable type object` al arrancar | Pusiste la clase sola en la lista | Envuélvela: `Middleware(MiClase)` |
| `TypeError: ... missing 1 required positional argument` o `unexpected keyword argument` al arrancar | Los parámetros de `Middleware(Clase, ...)` no coinciden con el `__init__` de la clase | Pasa cada parámetro por nombre, tal como lo pide `__init__` |
| `get_context().actor_username` es `None` | Se leyó antes de `call_next` | Léelo después: el usuario se identifica en la ruta |
| Tu cabecera de seguridad no cambia | Las del sistema se escriben en la capa más externa | Es a propósito: no se puede sobrescribir desde un middleware propio |
| Las respuestas en streaming se cortan | `BaseHTTPMiddleware` no es ideal para streaming | Escribe el middleware como ASGI puro (como `app/core/middlewares/security_headers.py`) o evítalo en esas rutas |
| Cambiar el cuerpo de la respuesta rompe `Content-Length` | Se modificó el cuerpo sin recalcular la cabecera | Devuelve una `Response` nueva |
