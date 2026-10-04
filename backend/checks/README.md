# Comprobaciones (`backend/checks/`)

Scripts que ejercitan el servidor **real** por HTTP (y, si hace falta, la base de
datos) y dicen si algo se rompió. La plantilla no trae pruebas de `pytest` a
propósito; estas comprobaciones son la red de seguridad mientras tanto: lánzalas
después de actualizar dependencias, de tocar `core/` o antes de un despliegue.

> **Crean datos** (roles, usuarios, eventos con nombres aleatorios) y algunas
> manipulan la base a propósito (por ejemplo, desactivan un trigger de `events`
> para comprobar que `verify` detecta la alteración). Úsalas **solo contra una base
> de desarrollo o de pruebas**, nunca contra producción.

## Cómo se lanzan

1. Una base de desarrollo con el esquema creado y un usuario dev
   (`ADMIN_USERNAME=dev ADMIN_PASSWORD=... uv run python -m app.scripts.create_admin`).
2. El servidor en marcha **con `DEBUG=true`** (usan `/openapi.json` y
   `/api/system/test-error`): `uv run fastapi dev`.
3. En otra terminal, desde `backend/`, con las variables:

| Variable | Para qué |
|---|---|
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | El usuario dev con el que inician sesión |
| `DATABASE_URL` | La misma del servidor: algunas comprobaciones preparan o alteran datos |
| `SECRET_KEY` | La misma del servidor: `attack` y `attack_session` firman tokens falsos |
| `API_URL` | Dirección del servidor (por defecto `http://127.0.0.1:8000`) |

```bash
cd backend
uv run python -m checks.run_all            # todas, en orden, con resumen
uv run python -m checks.run_all smoke chain  # solo las que nombres
uv run python -m checks.smoke              # una sola
```

`run_all` borra los intentos de login y las respuestas de idempotencia guardadas
antes de cada comprobación: el límite de login (10 intentos por usuario e IP cada 5
minutos) y la repetición automática de escrituras idénticas (10 s) son
comportamientos reales que, si no, harían fallar a la siguiente. Cada script sale con
código `0` si todo pasó y `1` si algo falló, y lista los fallos al final.

## Qué cubre cada una

| Script | Comprueba |
|---|---|
| `smoke` | Lo esencial del núcleo: sesión, roles, usuarios, permisos, CRUD, eventos, errores y escrituras simultáneas |
| `filters` | Orden (`?sort=`), rangos (`_from`/`_to`), varios valores, mensajes de validación en español y parámetros en OpenAPI de los listados |
| `login` | Límite de intentos de login (también con ráfagas simultáneas), cambio de contraseña y desactivación |
| `idempotency` | `Idempotency-Key`: repetición, claves inválidas, otra sesión, escritura con el token de acceso caducado y envíos simultáneos con la misma clave |
| `hardening` | Protección de cuentas dev, restablecer la propia contraseña, nombre tecleado en un login fallido, valores únicos y errores de concurrencia |
| `chain` | Triggers de solo añadir de `events`, `GET /api/events/verify` (entera, por periodo, por evento) y qué manipulaciones detecta |
| `attack` | Un atacante externo: tokens falsificados, CSRF por `Origin`, inyecciones, IDOR, escalada de privilegios, cuerpos enormes, fuerza bruta |
| `attack_session` | Inyección en logs, vida máxima de la sesión (30 días), cookie robada tras cerrar sesión y `X-Forwarded-For` |
| `api_docs` | Que `backend/API.md` documenta cada endpoint, permiso y código de error reales |

## Añadir una comprobación

Un archivo nuevo en `checks/` con una función `main()`, que usa `Checker` y los
ayudantes de `checks/common.py` (`dev_client()`, `client()`, `login()`, `tag()`,
`code_of()`, `fields_of()`, `query()`, `execute()`...), y se añade a `MODULES` en
`run_all.py`. Usa `tag()` en los nombres para que se pueda repetir sin choques, y una
`Idempotency-Key` distinta (o cuerpos distintos) cuando repitas una escritura.
Cuando una comprobación nazca de un fallo real, déjalo dicho en su nombre.
