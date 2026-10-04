# Guía para desarrolladores

Esta guía es para quien llega nuevo al proyecto. Explica cómo está organizado,
cómo funciona por dentro y dónde se trabaja. El detalle de cada pieza está en el
`steps.md` de su carpeta: aquí solo se dice a cuál ir.

**Referencia de la API.** Los endpoints, sus parámetros y ejemplos de uso están en
[`backend/API.md`](backend/API.md). Con `DEBUG=true`, `/docs` los muestra también,
cada uno con su resumen en español y su permiso.

---

## 1. Arrancar

Necesitas Python 3.14, `uv`, `bun` y un PostgreSQL 14 o superior al que conectarte. **El
servidor no crea la base de datos**: créala antes, junto con un usuario que pueda
crear tablas en ella (sección 5). Las tablas las crea el servidor mientras el
proyecto no tenga `backend/migrations/`; cuando la tiene, las gestiona aerich.

En desarrollo **no hace falta `.env`**: `backend/app/settings.py` trae valores por defecto
(`postgres://postgres:admin@localhost:5432/template` y una `SECRET_KEY` fija), que solo valen
con `DEBUG=true`. Instala las dependencias y crea la base (ajusta el usuario si el tuyo no
es `postgres`; si su clave no es `admin`, usa un `.env`):

```bash
cd backend && uv sync
createdb -U postgres template
```

Para otros valores, o en producción, se copia el ejemplo y se rellenan `DATABASE_URL` y
`SECRET_KEY` (con `DEBUG=false` el servidor **no arranca** con los de desarrollo):

```bash
cd backend && cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

El último comando imprime una clave para `SECRET_KEY` (mínimo 32 caracteres; si falta algo,
el servidor no arranca y el mensaje dice qué).

Primer usuario, que queda como `dev` (acceso total). No se crean roles solos: ese
usuario los crea a mano desde la página **Roles** y se los asigna a los demás.

```bash
cd backend && uv run python -m app.scripts.create_admin
```

**Si el proyecto ya tiene migraciones** (existe `backend/migrations/`), el servidor
no crea las tablas: en una base nueva, `uv run aerich upgrade` va **antes** de
`create_admin` y de arrancar; si no, los dos se niegan con «Este proyecto tiene
migraciones y esta base no las ha recibido». La plantilla recién clonada no trae
ninguna, así que esto no te afecta hasta que las crees (sección 5).

Servidores de desarrollo (**sin ruta**: `fastapi` encuentra la aplicación en
`[tool.fastapi]` de `pyproject.toml`):

```bash
cd backend && uv run fastapi dev
cd frontend && bun install && bun run dev
```

Abre <http://localhost:5173> y entra con el usuario que acabas de crear. La
documentación interactiva de la API está en <http://127.0.0.1:8000/docs> y solo
existe con `DEBUG=true` (`/openapi.json` igual; `/redoc` no existe nunca). Para
que el frontend apunte a otro backend: `BACKEND_URL=http://127.0.0.1:8010 bun run dev`
(en PowerShell: `$env:BACKEND_URL='http://127.0.0.1:8010'; bun run dev`).

**Dar nombre a un proyecto nuevo.** Se edita a mano en cuatro sitios: `APP_NAME` en
`backend/.env`, `APP_NAME` en `frontend/src/core/app.ts`, el `<title>` de
`frontend/index.html` y el `name` de `frontend/package.json`. El título de la API
sale de `APP_NAME`; su descripción está en `backend/app/main.py`.

De `APP_NAME` salen también **los nombres de las cookies de sesión**:
`<slug>_access` y `<slug>_refresh`. El `<slug>` es el nombre en minúsculas, con cada
tramo de caracteres que no son `a-z` ni `0-9` cambiado por un guion (`Mi Tienda` da
`mi-tienda_access`, `Template` da `template_access`, `Café` da `caf_access`, y un
nombre sin letras ni números da `app_access`). Dos consecuencias:

- Dos proyectos en `localhost` no se cierran la sesión entre sí (las cookies no
  distinguen puertos), siempre que su `APP_NAME` sea distinto. Dos proyectos que
  dejaron el `Template` de fábrica sí comparten cookies: otra razón para ponerle
  nombre.
- **Cambiar `APP_NAME` en un proyecto con usuarios cierra la sesión a todos**: las
  cookies con el nombre viejo dejan de leerse y hay que volver a entrar.

El frontend no lee ni nombra esas cookies (son `httponly`): no hay nada que cambiar
allí.

Antes de dar un cambio por terminado, todo esto debe pasar:

```bash
cd backend && uv run basedpyright
cd backend && uv run ruff check . && uv run ruff format --check .
cd frontend && bun run check
```

**Pruebas.** No hay pruebas unitarias: `pytest` y `vitest` están desinstalados. La red
de seguridad son los scripts de `backend/checks/` (humo, filtros, sesión, idempotencia,
cadena de eventos, ataque externo y que `backend/API.md` coincida con la API real), que
ejercitan el servidor **real** contra una base de pruebas; se lanzan con
`uv run python -m checks.run_all` (ver `backend/checks/README.md`). El frontend se prueba
a mano con la lista de la sección 4.

### Actualizar dependencias

Los mínimos de `backend/pyproject.toml` (`>=`) son las versiones con las que se probó
la plantilla; `uv.lock` y `frontend/bun.lock` fijan las exactas. El frontend usa Vite
7 (el paquete `vite` normal, mínimo 7.3.6); el `overrides` de
`frontend/package.json` fuerza una sola versión de `vite` y de `nanoid` en todo el
árbol, así que revísalo al actualizar. Para subir versiones:

```bash
cd backend && uv lock --upgrade && uv sync
cd frontend && bun update
```

Después, las comprobaciones de arriba y una prueba a mano: entrar, un listado con
filtros y una escritura. Si el proyecto conserva `backend/checks/` (scripts de humo,
filtros y ataque contra el servidor real; ver su `README.md`), lánzalos también,
siempre contra una base de pruebas: crean datos. Una actualización de FastAPI puede
cambiar lo que lee la comprobación de permisos al arrancar (sección 8, «No se
encontró ningún endpoint con permiso»). Guarda los dos archivos de bloqueo con el
proyecto.

### Configuración

Toda la configuración está en `backend/app/settings.py`, y `backend/.env.example`
es la lista de lo que se puede poner en `.env`. Se lee de `backend/.env` (lanza
los comandos desde `backend/`); una variable de entorno del proceso manda sobre
el archivo.

| Variable | Por defecto | Qué es |
|---|---|---|
| `DEBUG` | `true` | `true` (desarrollo): existen `/docs` y `/openapi.json`, los errores inesperados añaden el campo `debug` con la excepción, las cookies van sin `Secure` y con `SameSite=Lax`, no se envía HSTS y se admite `http://`. Con `false` (**producción, hay que ponerlo**): nada de eso, cookies `Secure` y `SameSite=Strict` |
| `APP_NAME` | `Template` | Nombre de la aplicación, título de la API y prefijo de las cookies de sesión (`<slug>_access`, `<slug>_refresh`): cambiarlo cierra las sesiones abiertas |
| `APP_VERSION` | `0.1.0` | Versión de la API (la de `/docs` y `GET /api/system/info`) |
| `DATABASE_URL` | `postgres://postgres:admin@localhost:5432/template` (solo desarrollo) | `postgres://usuario:clave@host:5432/base`. Con `DEBUG=false` hay que ponerla. Debe empezar por `postgres://` (no `postgresql://`). Si la clave tiene `@`, `/`, `:` o `#`, se codifican (`@` es `%40`) |
| `CORS_ORIGINS` | los dos de Vite en local | Lista JSON de orígenes del frontend, por ejemplo `["https://app.ejemplo.com"]`. Nunca `*`. También decide qué escrituras acepta la protección CSRF |
| `SECRET_KEY` | una clave fija de desarrollo (solo con `DEBUG=true`) | Mínimo 32 caracteres. Con `DEBUG=false` hay que ponerla. De ella salen las claves de firma (ver Seguridad) |
| `JWT_ISSUER` | `http://localhost:8000` | URL pública de la API. Va dentro de cada token y se comprueba al leerlo: cambiarla cierra las sesiones abiertas |

Con `DEBUG=false`, `JWT_ISSUER` y **todos** los `CORS_ORIGINS` deben ser
`https://`; si no, el servidor no arranca. Con `DEBUG=true` (el valor por defecto) arranca,
pero deja una advertencia en el log: documentación abierta, detalle de errores y cookies
sin `Secure`. Las dos cosas van juntas a propósito: producción se sirve por HTTPS, y una
red privada solo con `http://` tiene que quedarse en `DEBUG=true` (o poner TLS delante).

Lo demás no se configura por variable. La duración de los tokens (15 minutos el de
acceso, 7 días el de refresco) son constantes de `core/security.py`; el máximo de
sesiones y los intentos de login, de `core/services/auth.py`. `Secure` y
`SameSite` de las cookies se derivan de `DEBUG`, y sus nombres, de `APP_NAME`. Las
variables que `.env` traiga de más se ignoran.

---

## 2. Mapa del proyecto

### Backend

Dos zonas: **`core/`** es el sistema, igual en todos los proyectos y no se toca.
**Todo lo demás** es donde se construye. Cada carpeta de trabajo tiene su
`steps.md` con las instrucciones.

```
backend/app/
├── main.py                 Arma la aplicación: título, middlewares y routers
├── settings.py             Configuración (.env) y claves derivadas de SECRET_KEY
├── registry.py             Tu registro: qué modelos, rutas, middlewares y errores tiene el proyecto
├── core/                   El sistema. No se edita
│   ├── registry.py         El registro del sistema (no se toca)
│   ├── database.py         TORTOISE_ORM (la configuración de Tortoise que usan la app y aerich) y la comprobación de migraciones
│   ├── models/             Users, Role, UserSession, Event, LoginAttempt, Entity (la base de las tablas)
│   ├── schemas/            Formas de entrada y salida del sistema
│   ├── services/           Lógica del sistema: sesiones, eventos, auditoría, reglas de usuarios y roles
│   ├── routes/             Endpoints del sistema: auth, users, roles, events, system
│   ├── middlewares/        Un archivo por middleware del sistema
│   ├── context.py          Datos de la petición en curso
│   ├── errors.py           Catálogo de errores, AppError y el manejador único
│   ├── permissions.py      Registro de permisos y comprobación de rutas al arrancar
│   ├── dependencies.py     requires(): protege un endpoint con un permiso
│   ├── crud.py             Resource: los siete endpoints CRUD de un modelo, con sus filtros y orden
│   ├── openapi.py          Resumen y permiso de cada endpoint en /docs
│   ├── security.py         Contraseñas, tokens, cookies
│   └── idempotency.py      Puente entre fastapi-idempotency y el catálogo de errores
│
├── models/      steps.md   Tus tablas
├── schemas/     steps.md   Tus formas de entrada y salida (JSON)
├── routes/      steps.md   Tus endpoints y permisos
├── services/    steps.md   Tu lógica de negocio
├── errors/      steps.md   Tus errores
├── middlewares/ steps.md   Tus middlewares
└── scripts/                create_admin
```

Fuera de `app/`, en `backend/`: [`API.md`](backend/API.md) (referencia de los endpoints,
errores y límites; `checks/api_docs.py` comprueba que coincide con la API real), `checks/`
(scripts contra el servidor real, ver su `README.md`), `.env.example` y `pyproject.toml`.

**Nada se carga solo.** Un archivo nuevo no existe para la aplicación hasta que lo
importas en `app/registry.py`, que tiene cuatro listas:

| Quiero... | Carpeta | Lista de `app/registry.py` |
|---|---|---|
| Añadir una tabla | `app/models/` | `MODELS`: el módulo que tiene los modelos |
| Definir qué entra y sale de un endpoint | `app/schemas/` | Ninguna: lo importa la ruta |
| Añadir un endpoint o un CRUD | `app/routes/` | `ROUTERS`: el `router` de esa ruta |
| Escribir una regla de negocio | `app/services/` | Ninguna: lo importa quien la use |
| Definir un error | `app/errors/` | `ERRORS`: cada `ErrorSpec` |
| Envolver todas las peticiones (cabeceras, tiempos...) | `app/middlewares/` | `MIDDLEWARES`: `Middleware(Clase, parametro=...)` |

Con el catálogo de productos de la sección 4 (y un middleware inventado para el
ejemplo), `app/registry.py` queda así:

```python
from starlette.middleware import Middleware

from app.errors import product as product_errors
from app.middlewares.timing import TimingMiddleware
from app.models import category, product
from app.routes import product as product_routes

MODELS = [category, product]
ROUTERS = [product_routes.router]
MIDDLEWARES = [Middleware(TimingMiddleware, header="X-Process-Time")]
ERRORS = [product_errors.PRODUCT_NOT_FOUND]
```

`Middleware` es `starlette.middleware.Middleware`. Los errores de `ERRORS` los
registra `main.py`: no llames tú a `register_error`. `app/core/registry.py` es el
equivalente del sistema y `main.py` une los dos. **Añadir una funcionalidad es
crear sus archivos e importarlos en `app/registry.py`.**

Las dependencias van en una sola dirección, de arriba abajo:

```
routes  ->  services  ->  models  ->  core
schemas  ->  models
```

Los modelos no importan rutas ni servicios; los servicios no importan rutas.

Ningún directorio de `app/` lleva `__init__.py`: no aportan nada. El servidor se
descubre por `entrypoint = "app.main:app"` en `pyproject.toml`, que solo sirve
para `uv` y las herramientas: uv exige `version`, pero la versión real de la API
es `APP_VERSION`.

### Frontend

```
frontend/src/
├── index.tsx            Todas las rutas, escritas a mano (import perezoso + entrada en `routes`)
├── core/                Infraestructura. Rara vez hay que tocarla
│   ├── app.ts           Nombre de la aplicación (APP_NAME)
│   ├── api.ts           Cliente HTTP, interceptor (errores, renovar sesión, claves) y crud()
│   ├── auth.ts          Sesión y permisos del usuario; sincroniza pestañas y detecta cambios
│   ├── form.ts          createForm: valores, errores por campo, guardado y clave de idempotencia
│   ├── idempotency.md   La clave Idempotency-Key: cómo funciona en el frontend y por qué
│   ├── serverStatus.ts  Vigila la conexión con el servidor (/system/health) y avisa cuando cae
│   ├── requestLog.ts    Las últimas 150 peticiones a la API (las lee Debug → Peticiones)
│   ├── routes.ts        safeNext: a dónde se vuelve tras iniciar sesión
│   ├── notify.ts        Toasts
│   ├── limits.ts        Longitudes máximas de los campos (espejo de los `max_length` del backend)
│   └── format.ts        Fechas y valores para mostrar
├── modules/             Un archivo por módulo del backend: tipos y llamadas
├── components/
│   ├── ui.tsx           Input, PasswordInput, Modal (accesible), PageHeader, createConfirm
│   ├── layout.tsx       Menú (NAV), AppShell, ProtectedRoute, Can, NoAccess, CrashNotice
│   ├── ServerStatusGate.tsx  Tapa la aplicación con la pantalla sin conexión mientras el servidor no responde
│   ├── StatusBadge.tsx  Indicador de conexión y latencia de la barra superior
│   ├── crud.tsx         createCrudList, ListToolbar, ListTable, SortHeader, filtros, RangeFilter, Pagination, RowActions
│   ├── sessions.tsx     SessionList: las sesiones abiertas de una cuenta
│   └── history.tsx      createHistory y ChangesTable: el historial de un registro
├── pages/               Una página por archivo; cada una se registra en index.tsx
│   ├── Users.tsx        Página de referencia para un módulo CRUD
│   ├── Roles.tsx, Audit.tsx, Account.tsx, Home.tsx, Login.tsx, NotFound.tsx
│   ├── Offline.tsx      Pantalla sin conexión (la pinta ServerStatusGate)
│   └── Debug.tsx        Herramientas para desarrolladores (solo dev en el menú)
└── features/debug/      Paneles de /debug: Estado, Peticiones, Errores y Permisos
```

Los dos lados tienen `core/` para la infraestructura. El negocio del backend vive en
`models/`, `schemas/`, `routes/`, `services/` y `errors/`; el del frontend, en
`modules/`: `backend/app/routes/product.py` tiene su pareja en
`frontend/src/modules/products.ts`.
Como en el backend, nada se descubre solo: una página nueva existe cuando la importas y
la añades a `routes` en `src/index.tsx`.

---

## 3. Cómo funciona por dentro

### Arranque

Al iniciar, el servidor hace cuatro cosas, por este orden:

1. **Prepara las tablas.** Sin `backend/migrations/`, **crea las que falten**
   (`generate_schemas` de Tortoise, que equivale a `CREATE TABLE IF NOT EXISTS`):
   sirve igual en desarrollo y en producción y **no modifica tablas que ya
   existen**. Con `backend/migrations/` **no crea nada**: comprueba que la base haya
   recibido las migraciones y, si no, no arranca y pide `uv run aerich upgrade`.
   Cambiar el esquema después es cosa de las migraciones de aerich (sección 5).
2. **Verifica los permisos.** Cada endpoint de `/api` debe declarar exactamente un
   permiso propio; si no, el servidor no arranca y el mensaje dice cuál. Con
   `DEBUG=true`, además escribe en `/docs` el resumen y el permiso de cada endpoint.
3. **Asegura la cabeza de la cadena de auditoría.**
4. **Instala en la base los triggers que impiden modificar los eventos**, si
   faltan (ver "Integridad del registro de eventos", sección 3).

### Una petición de principio a fin

Los middlewares se ejecutan de fuera hacia dentro, en el orden de `main.py`:

1. **Cabeceras de seguridad** (`SecurityHeadersMiddleware`): las añade a toda
   respuesta, también a los errores.
2. **CORS.**
3. **Límite de cuerpo** (`BodyLimitMiddleware`): cuenta los bytes del cuerpo según
   llegan y responde `413 SYS_413` al pasar de 1 MiB, sin leerlo entero en memoria.
4. `request_context`: genera el `request_id` (UUIDv7), abre el contexto de la
   petición y lo devuelve en la cabecera `X-Request-ID`.
5. `unhandled_errors`: convierte cualquier excepción sin controlar en la respuesta
   de error estándar, con cabeceras CORS y `request_id`.
6. `origin`: rechaza escrituras enviadas desde otra web (CSRF).
7. `idempotency`: si esa misma escritura ya llegó, responde lo mismo sin ejecutar
   nada; si sigue en curso, espera.
8. Tus middlewares (`MIDDLEWARES` de `app/registry.py`), en el orden de la lista.
9. FastAPI ejecuta `requires(PERMISO)`: anota el permiso, autentica con la cookie
   de acceso (`<slug>_access`, ver «Seguridad»), identifica al usuario y comprueba
   si puede pasar. En las escrituras **abre una transacción**.
10. Pydantic valida el cuerpo y los parámetros con los esquemas.
11. Se ejecuta la función de la ruta. Cada `save()` sobre una `Entity` escribe su
    evento de historial dentro de la misma transacción.
12. La transacción se confirma **antes** de responder. Si algo falló, se deshace
    entera (datos y eventos) y `handle_error` responde con la forma estándar.

### Errores

Todo error sale con esta forma:

```json
{ "error": { "code": "SYS_409", "message": "Ya existe un registro con esos datos.",
             "toast": true, "severity": "warning", "request_id": "…",
             "event_id": null, "fields": { "sku": "Ya existe un registro con este valor" },
             "details": {} } }
```

En el frontend, `core/api.ts` muestra el toast cuando `toast` es `true`, renueva
la sesión si el 401 es solo un token caducado y lanza un `ApiError`. Con
`createForm`, los `fields` acaban solos junto a cada campo del formulario. Con
`DEBUG=true`, los errores inesperados añaden además `debug` con la excepción. Cómo
declarar y lanzar errores: `app/errors/steps.md`.

**Mensajes por campo.** Los de `fields` salen **en español** («Este campo es
obligatorio», «Mínimo 2 caracteres», «Identificador no válido», «La fecha necesita
zona horaria»...). Los genera `core/errors.py` a partir del tipo de error de
Pydantic; en una query, los elementos de una lista no se numeran (`role_id`, no
`role_id.0`). El mensaje de un validador propio es el de su `ValueError`. La lista de
tipos cubiertos y cómo añadir el tuyo: `app/errors/steps.md`, sección 5.

**Errores de la base de datos.** PostgreSQL responde con un código SQLSTATE y se
traduce por él:

| SQLSTATE | Qué pasó | Respuesta |
|---|---|---|
| `23505` | Valor repetido en una columna única | `409 SYS_409` (se guarda como evento) |
| `23503`, `23001` | Clave foránea: registro en uso (`NO ACTION` o `RESTRICT`) o inexistente | `409 SYS_REL` |
| `40P01`, `40001` | Bloqueo cruzado o fallo de serialización: PostgreSQL abortó la transacción | `409 SYS_CONC` (el cliente puede repetir) |
| clase `22` | Dato que la base rechaza: un byte NUL en un texto, un número fuera de rango... | `422 VAL_422` |
| otro fallo de integridad | Restricción no prevista | `500 SYS_500` |
| base no disponible | Conexión caída, error operativo | `503 SYS_503` |

### Permisos

Cada endpoint declara exactamente un permiso con un número estable. Un rol es una
lista de esos números (una columna `integer[]` en PostgreSQL). Si una ruta no
declara permiso o dos rutas comparten uno, **la aplicación no arranca** y el
mensaje dice cuál.

| Alcance | Quién entra |
|---|---|
| `Scope.PUBLIC` | Cualquiera, sin sesión |
| `Scope.AUTHENTICATED` | Cualquier usuario con sesión, tenga rol o no |
| `Scope.ROLE` (por defecto) | Quien tenga ese número en su rol, o un dev |
| `Scope.DEV` | Solo usuarios `dev`; no se puede dar mediante un rol |

**Numeración.** El sistema usa de `1000` a `5999`. **Los tuyos empiezan en
`6000`**: cada recurso CRUD ocupa un bloque de 100 (`base+1` a `base+7` son sus
siete permisos CRUD y `base+11` a `base+99` sus endpoints propios).

| Bloque | Módulo |
|---|---|
| 1000 | system (`1001–1005`) |
| 2000 | auth (`2001–2008`) |
| 3000 | users (`3001–3007` CRUD, `3011–3013` propios) |
| 4000 | roles |
| 5000 | events (`5001–5005`) |
| 6000 en adelante | tus módulos |

**Cuentas dev.** Solo un dev puede editar, eliminar, restaurar, cambiar la
contraseña o cerrar las sesiones de otro dev (`403 USR_005`), y solo un dev da o
quita la marca dev (`403 USR_004`). Así un rol con permisos de gestión de usuarios
no puede hacerse con una cuenta de acceso total.

**Escalada de privilegios.** Quien no es dev solo puede conceder o gestionar
permisos que él mismo tiene; si no, `403 PRM_004`. Concretamente no puede:

- crear, editar, eliminar ni restaurar roles cuyos permisos (los actuales o los
  nuevos) no caben en los suyos;
- asignar a un usuario un rol con más permisos que los suyos;
- editar, eliminar, restaurar, restablecer la contraseña ni cerrar las sesiones de
  un usuario con más permisos que él.

### Transacciones

Toda ruta `POST`, `PUT`, `PATCH` o `DELETE` protegida con `requires(...)` es
atómica: o se guarda todo lo que hizo, o nada. No hay que escribir nada para
conseguirlo. Las rutas que deben guardar algo **aunque respondan con error** (el
login anota cada intento antes de comprobar la contraseña) usan
`requires(PERMISO, atomic=False)` y abren
sus propias transacciones. Detalle: `app/routes/steps.md`.

### Auditoría y borrado reversible

- Toda tabla que hereda de `Entity` tiene identificador UUIDv7, `created_at`,
  `updated_at`, autoría y borrado reversible.
- `Model.all()`, `Model.filter()` y las relaciones **no ven** lo eliminado;
  `Model.with_deleted()` sí.
- `item.soft_delete()` elimina, `item.restore()` restaura, `item.hard_delete()`
  borra la fila de verdad. `item.delete()` falla a propósito.
- Cada cambio queda en la tabla `events`. Cada evento lleva un número
  (`sequence`) sin huecos y firma todos sus campos encadenados con la firma del
  anterior. La cabeza de la cadena se bloquea al escribir (`SELECT ... FOR
  UPDATE`), así que varios procesos pueden escribir eventos a la vez sin huecos.
  Cómo se comprueba y cómo se protege, en "Integridad del registro de eventos".
- El historial sale de las señales de `save()`. `QuerySet.update()`,
  `QuerySet.delete()`, `bulk_create()` y las relaciones muchos a muchos **no**
  dejan historial: en tablas auditadas trabaja con el objeto.

### Integridad del registro de eventos

Tres capas, de dentro a fuera:

1. **Firma encadenada.** Cada evento lleva una firma HMAC (clave derivada `audit`)
   de todos sus campos y de la firma del evento anterior. Editar un campo o quitar
   un evento del medio rompe la cadena.
2. **Triggers de solo añadir.** Una función PL/pgSQL (`events_append_only()`) y dos
   triggers que la llaman: `events_no_change` (`UPDATE` y `DELETE`, fila a fila) y
   `events_no_truncate` (`TRUNCATE`). Viven en la base de datos, pero **se crean
   desde Python**: al arrancar (y en `create_admin`) `install_event_guards()`
   (`core/services/event_log.py`) los instala si faltan, con un bloqueo para que
   varios procesos no choquen. Desde entonces la base rechaza `UPDATE`, `DELETE` y
   `TRUNCATE` sobre `events` venga de la aplicación o de `psql`, incluso siendo el
   dueño de la tabla; el `INSERT` sigue funcionando. Necesitan PostgreSQL 14 o
   superior. Si al arrancar faltaban o estaban desactivados y ya había eventos, se
   instalan y queda un evento de aviso (`warning`): es el rastro de que alguien los
   apagó.
3. **La cabeza (`event_chain`).** Guarda el número y la firma del último evento.
   Serializa las escrituras y permite detectar que faltan los últimos.

**Comprobarlo:** `GET /api/events/verify` (permiso `events.verify`), o en la página
Auditoría: **Verificar integridad** y **Verificar en la cadena** en el detalle de un
evento. Con «Desde» o «Hasta» puestos, el primer botón pasa a llamarse **Verificar
el periodo** y usa solo esas fechas (los demás filtros no cuentan); **Limpiar
filtros** lo devuelve a la cadena entera.

| Parámetros | Qué comprueba |
|---|---|
| ninguno | Toda la cadena: firmas, huecos, enlaces y la cabeza |
| `date_from` y/o `date_to` (ISO con zona horaria) | Los eventos del periodo: la firma de cada uno, que no falten números entre ellos y que el primero enlace con el evento anterior (que queda fuera; su firma no se comprueba). Si el periodo llega al último evento, también la cabeza |
| `event_id` | Un evento: su firma y su enlace con el anterior (y la cabeza si es el último). No se combina con fechas |

`event_id` junto con fechas, o `date_from` posterior a `date_to`, dan `422 VAL_422`;
un `event_id` que no existe da `404`. La comprobación se hace sobre una instantánea
de la base (`REPEATABLE READ`, solo lectura), así que las escrituras que entren
mientras corre no producen falsos avisos. Recorre los eventos de uno en uno: en una
cadena de millones de eventos, verificarla entera tarda minutos; para el día a día,
usa periodos.

La respuesta trae `total`, `checked`, `intact`, `first_broken_id`, `detail` y
`append_only`: dice si los dos triggers existen y están activos, no si algo los ha
vaciado por dentro.

**Qué detecta cada manipulación** (comprobado contra PostgreSQL, quitando el
trigger a propósito):

| Alguien... | Lo detecta |
|---|---|
| Edita un evento | La cadena entera, un periodo que lo incluya y el propio evento. Un periodo que no lo incluye no lo ve |
| Borra uno del medio | La cadena entera, un periodo que lo rodee y el evento siguiente por sí solo |
| Borra el último | La cadena entera y cualquier periodo que llegue al final (por la cabeza). Un periodo cuyos únicos eventos fueron esos dice «No hay eventos que comprobar» |
| Borra la fila de la cabeza | La cadena entera y cualquier periodo que llegue al final |
| Inserta un evento falso (el `INSERT` sigue permitido) | Su firma no cuadra: la cadena entera y la verificación del propio evento lo detectan, también con `sequence` 0 o negativa |
| Borra el último **y** reajusta la cabeza | **Nadie**: no hace falta conocer la clave `audit` para hacerlo |

Editar, borrar y reajustar exigen antes saltarse los triggers. Desactivarlos exige
ser el dueño de la tabla o superusuario, y hay otros caminos para ese mismo perfil
que dejan `append_only` en `true` (cambiar el cuerpo de `events_append_only()`,
`session_replication_role = replica`, reescribir la tabla). Ese es el límite: con
los triggers activos, un fallo de la aplicación o una consulta a mano no pueden
tocar el registro; quien controle la base como dueño o superusuario sí, y la última
fila lo hace indetectable. Para una red privada es un nivel razonable. Si algún día
hiciera falta más, se guarda fuera de la base el resultado de
`SELECT sequence, last_hash FROM event_chain` cada cierto tiempo y se compara.

**Qué hay que hacer a mano:** nada para activarlo. Solo:

- No cambies `SECRET_KEY` (ver "Claves distintas por uso").
- La aplicación debe conectarse como **dueño de las tablas**. Probado con un usuario
  que no lo es: PostgreSQL le niega modificar `events` y tocar los triggers, pero la
  aplicación no arranca: sin migraciones, el arranque ejecuta `generate_schemas`,
  que exige ser dueño hasta para `CREATE INDEX IF NOT EXISTS`. Separar roles no está
  soportado de fábrica.
- Un script o una migración que reescriba filas de `events` falla con «El registro
  de eventos es de solo añadir»: es lo previsto, porque rompería la cadena. Las que
  solo cambian el esquema funcionan. Tampoco se pueden borrar eventos antiguos.
- Si desactivas un trigger a mano, el siguiente arranque lo reactiva y deja el
  evento de aviso; mientras tanto, `verify` avisa con `append_only: false`.

**Si la cadena se atasca.** Un evento de más en la tabla (por ejemplo, con el número
que iba a usar el siguiente) hace fallar toda escritura que deje historial, y el
error sale como un `409` engañoso. No se arregla borrando desde la aplicación:

- En desarrollo, lo más simple es tirar la base y volver a crearla (`create_admin`
  vuelve a dejar todo).
- Con datos que importan, como dueño de la base: desactiva el trigger
  (`ALTER TABLE events DISABLE TRIGGER events_no_change`), borra la fila sobrante,
  actívalo de nuevo (`ENABLE TRIGGER`) y reinicia. Si la cabeza se ha perdido o
  quedó descuadrada, `verify` lo dirá y se corrige con
  `UPDATE event_chain SET sequence = e.sequence, last_hash = e.hash FROM (SELECT sequence, hash FROM events ORDER BY sequence DESC LIMIT 1) e;`
  (es una intervención de dueño: ese `UPDATE` deja la cabeza como si nunca hubiera
  faltado nada).

### Seguridad

**Sesión.**

- Tokens JWT en cookies `httponly`: acceso de 15 minutos y refresco de 7 días, que
  rota en cada uso. Reutilizar un token de refresco ya usado cierra la sesión.
- Las cookies se llaman `<slug>_access` y `<slug>_refresh` (`template_access` y
  `template_refresh` con el `APP_NAME` de fábrica): el `<slug>` sale de `APP_NAME`
  (sección 1, «Dar nombre a un proyecto nuevo»). Cambiarlo cierra todas las
  sesiones. El frontend no las lee: el navegador las envía solo.
- Las cookies llevan `Secure` y `SameSite=Strict` en producción; en desarrollo,
  sin `Secure` y con `Lax`. Se derivan de `DEBUG`. Con `Strict`, frontend y API
  deben ser del mismo sitio: lo más simple es servir los dos bajo el mismo dominio.
- Una sesión caduca a los **30 días de abrirse**, aunque se renueve sin parar.
- Máximo 5 sesiones por usuario; al abrir la sexta se cierra la más antigua.
- En el frontend, la renovación usa un bloqueo compartido entre pestañas.
- Intentos de login en base de datos: 10 por usuario desde una IP y 50 por IP cada
  5 minutos (`429 SYS_429`). El intento se anota **antes** de comprobar la
  contraseña (un acierto lo borra), así una ráfaga de peticiones simultáneas no
  puede saltarse el límite; a cambio, cuenta también los intentos en curso: más de
  50 logins simultáneos desde una misma IP (una red grande tras NAT) reciben `429`
  aunque acierten. El cambio de contraseña (`POST /api/auth/password`) comparte el
  mismo contador. La IP se toma tal cual: con IPv6, quien controle un bloque de
  direcciones tiene un cupo por dirección (otra razón para limitar en el proxy). El
  login tarda lo mismo exista o no el usuario.
- Los nombres de usuario son solo ASCII en minúsculas: letras sin acentos,
  números, punto, guion y guion bajo, de 3 a 50 caracteres. Se normalizan a
  minúsculas también al iniciar sesión.
- Las contraseñas tienen de 8 a 128 caracteres, con al menos una letra y un
  número, y sin espacios al principio ni al final.
- **Nadie restablece su propia contraseña** con `POST /api/users/{id}/password`
  (`409 USR_003`, con `details.use` apuntando a `POST /api/auth/password`): la propia se
  cambia dando la actual, que además cuenta para el límite de intentos. Tampoco se
  eliminan, desactivan ni quitan la marca `dev` a sí mismos.
- **Las sesiones de un dev no las ve ni las cierra quien no es dev**
  (`GET` y `DELETE /api/users/{id}/sessions`, `403 USR_005`): ver sus dispositivos y
  direcciones o cerrárselas sería una forma de tocar una cuenta protegida.
- **Lo que se guarda del intento de login fallido.** El nombre que se muestra y se
  registra es el tecleado solo si tiene formato de usuario válido; si no (por ejemplo,
  una contraseña pegada en el campo de usuario), el evento dice `<inválido>`. Los saltos
  de línea y los códigos de escape no llegan nunca al registro ni a los logs.

**Cabeceras de seguridad.** `SecurityHeadersMiddleware` las pone en cada
respuesta, también en los errores:

| Cabecera | Valor | Dónde |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | Toda respuesta |
| `X-Frame-Options` | `DENY` | Toda respuesta |
| `Referrer-Policy` | `no-referrer` | Toda respuesta |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | Toda respuesta, solo con `DEBUG=false` |
| `Cache-Control` | `no-store` | Solo en `/api` |
| `Content-Security-Policy` | `default-src 'none'; frame-ancestors 'none'` | Solo en `/api` |

Son las de la API. Las de la web (el `index.html` y el JavaScript del frontend)
las pone quien la sirva.

**Límite de cuerpo.** Ninguna petición puede llevar más de 1 MiB (`413 SYS_413`).
`BodyLimitMiddleware` mira `Content-Length` y además cuenta los bytes según llegan,
así que no se salta el límite con un cuerpo por trozos. Se cambia en `main.py`.

**CSRF.** `origin` rechaza escrituras a `/api` cuya cabecera `Origin` no sea el
propio servidor ni esté en `CORS_ORIGINS` (`403 PRM_003`). Un navegador siempre
envía `Origin` en una escritura de otra web; una petición sin esa cabecera (`curl`,
un script) pasa, porque no es un ataque desde el navegador de otro usuario.

**Claves distintas por uso.** Nada se firma con `SECRET_KEY` directamente: cada uso
tiene su clave derivada, `settings.key("uso")`, para que filtrar una no comprometa
a las demás. Hoy hay cuatro: `jwt` (tokens), `password` (contraseñas), `audit` (la
cadena de eventos) y `fingerprint` (la huella de los campos secretos en el
historial, para no guardarlos en claro). Si tu código necesita firmar algo, deriva
otra con un nombre nuevo. **Cambiar `SECRET_KEY` con datos reales** cierra todas las
sesiones, deja las contraseñas guardadas sin efecto (nadie podría entrar) y hace que
la cadena de auditoría ya escrita deje de verificar: trátala como un secreto que no
se rota.

**Escalada de privilegios.** Ver Permisos: `403 PRM_004`, se guarda como evento.

**Datos que la base rechaza.** Un byte NUL o un valor fuera de rango que PostgreSQL
no acepta responde `422 VAL_422`.

**Lo que sale a logs y eventos.** Los textos que vienen del cliente (rutas,
nombres de usuario, orígenes...) se limpian antes de escribirse: los saltos de
línea y demás caracteres de control se cambian por espacios y se recortan a 300
caracteres, para que nadie falsifique líneas de log.

**Salud.** `GET /api/system/health` solo devuelve `{status, database}`.

### Solicitudes repetidas (idempotencia)

Un doble clic o un reintento de red envían la misma escritura dos veces; se
procesa una sola vez y la copia recibe la misma respuesta con la cabecera
`Idempotent-Replayed: true`.

| Modo | Cuándo dos solicitudes son la misma | Durante |
|---|---|---|
| Automático | Mismo emisor, método, ruta, query y cuerpo, **seguidas**: cualquier otra escritura del mismo emisor corta la racha | 10 s |
| Cabecera `Idempotency-Key` | Misma clave del mismo emisor; con otra solicitud responde `422 IDM_002` | 24 h |

El emisor es la sesión (su id, leído del token de acceso; no cambia aunque el
token rote al renovarse) siempre que siga abierta en la base de datos; con una
sesión cerrada, sin sesión o con el token de acceso caducado, es la IP. Así una
cookie robada y ya cerrada no recibe respuestas guardadas, y el `401` de un token
caducado no se repite al reintentar con la sesión ya renovada. Una escritura que
tarda más de 60 s renueva
su reserva cada 20 s para que no la tome una copia por error. No se guardan los
errores 5xx ni las respuestas que ponen cookies (login correcto, renovación,
logout), ni una respuesta de más de 8 MiB. Las reservas viven en la tabla
`fastapi_idempotency_requests`, así que funcionan con varios procesos.

**Los errores 4xx sí se guardan.** Dos peticiones idénticas seguidas reciben la
misma respuesta, sea correcta o un error. Por eso 12 logins idénticos con la
misma contraseña no cuentan como 12 intentos: el segundo en adelante repite la
respuesta del primero. El límite de intentos de login funciona con contraseñas
distintas.

**Una clave guardada con un 4xx también se repite:** con `Idempotency-Key`, un
error se recuerda 24 h. Un reintento con la misma clave devuelve el mismo error
aunque el problema ya esté resuelto, y con otro cuerpo da `422 IDM_002`. La clave se
cambia cuando la respuesta es definitiva. Un `401` por token de acceso ya rotado
(otra pestaña renovó justo antes) se guarda también, y el reintento idéntico del
interceptor recibiría ese mismo `401`: por eso el interceptor reenvía con la clave
derivada `<clave>:renew`.

**El frontend envía `Idempotency-Key` en los formularios.** `createForm` genera una
clave por formulario, la mantiene mientras no se sepa qué pasó con el envío (sin
respuesta, 5xx, `IDM_001`) y la cambia al editar y ante una respuesta definitiva;
`post`, `patch` y `crud()` la aceptan como último parámetro. Las demás escrituras (un
botón de eliminar, restaurar...) no la llevan: solo cuentan con el modo automático de
10 s. Las reglas y cómo darle clave a un botón están en
`frontend/src/core/idempotency.md`.

### Conexión con el servidor y sesión (frontend)

- **Una sola instancia de axios** (`core/api.ts`). Su interceptor avisa a `core/serverStatus.ts`
  de cada respuesta: cualquiera la da por buena; sin respuesta, `502/503/504`, un `5xx` que no
  trae el formato de error de la API o `SYS_503` (base de datos caída) la dan por caída.
- **`ServerStatusGate`** envuelve todas las rutas (`src/index.tsx`). Sondea `/system/health`
  (cada 15 s; caído, cada 2 s duplicando hasta 15 s; en pausa con la pestaña oculta; al volver
  la pestaña o la red del navegador, al momento). Mientras no responde, la pantalla
  `pages/Offline.tsx` tapa todo y deja la aplicación de debajo montada pero inerte, así no se
  pierde un formulario a medias.
- **Al volver el servidor**, `auth.recover()` termina lo pendiente: completa la lectura de la
  sesión si el arranque falló por falta de red (sin esto te mandaría al login con la sesión
  intacta) y envía un cierre de sesión pendiente.
- **Cerrar sesión sin conexión** deja la sesión cerrada en este equipo y apunta el cierre como
  pendiente en `localStorage` (sobrevive a recargar). Mientras esté pendiente no se lee la
  sesión, porque las cookies siguen siendo válidas en el servidor.
- **La renovación de sesión** distingue entre sesión perdida (`401/403`: vuelve al login con
  aviso) y servidor no disponible (la sesión se conserva). Un bloqueo compartido entre pestañas
  evita que dos usen a la vez el mismo token de refresco.
- **`Debug → Estado`** muestra todo esto en vivo y `Debug → Peticiones`, el registro de cada llamada.

### Textos con límite

Todo texto que entra por la ruta, la query o el cuerpo debe llevar una longitud
máxima, y toda lista, un máximo de elementos. Los límites de cada campo los decides
tú, campo por campo, y **nada lo comprueba al arrancar**: un campo sin `max_length`
acepta lo que quepa en el cuerpo (1 MiB).

No hay un archivo de constantes de longitudes: cada límite se escribe donde se
usa, en la columna del modelo y en el esquema que valida la entrada. La política
del nombre de usuario (3 a 50) y de la contraseña (8 a 128) está en
`core/schemas/validators.py`, y los tipos `Username`, `Password` y `SearchText` de
`core/schemas/types.py` ya llevan su máximo. El frontend repite los valores de texto
en `frontend/src/core/limits.ts` para poner `maxLength` a los campos: si cambias un
límite en el backend, cambia también ese archivo. El límite de las listas es solo
del backend: un rol admite hasta 2000 permisos (`core/schemas/role.py`). Los textos
largos que el sistema guarda por su cuenta (rutas, etiquetas y códigos de los
eventos, user-agent) se recortan al ancho de su columna en `events`.

### Depurar

La página **Debug** (`/debug`, solo dev en el menú) tiene dos pestañas:

- **Errores:** provoca un error con el código HTTP que elijas
  (`GET /api/system/test-error/{status}`, solo dev) para ver cómo llega al frontend,
  y lista el catálogo de errores.
- **Permisos:** lista todas las claves de permiso con su endpoint y si tu usuario
  las tiene.

### Logs

Se usa el logger de uvicorn (`uvicorn.error`). Cada error se escribe con su código,
su ruta y su `request_id`; con ese `request_id` puedes ver en **Auditoría** todo lo
que pasó en esa petición.

---

## 4. Construir una funcionalidad de principio a fin

Ejemplo: un catálogo de productos. El orden importa: cada paso usa el anterior.

| Paso | Qué | Dónde | Guía |
|---|---|---|---|
| 1 | El modelo: sus campos y relaciones | `app/models/product.py` | `app/models/steps.md` |
| 2 | Los esquemas: `ProductCreate`, `ProductUpdate`, `ProductOut` | `app/schemas/product.py` | `app/schemas/steps.md` |
| 3 | Los errores propios, si hacen falta | `app/errors/product.py` | `app/errors/steps.md` |
| 4 | La lógica de negocio, si hay reglas | `app/services/product.py` | `app/services/steps.md` |
| 5 | Los permisos y los endpoints (CRUD y propios) | `app/routes/product.py` | `app/routes/steps.md` |
| 6 | Registrarlo todo: modelos, router y errores | `app/registry.py` | sección 2 |
| 7 | Dar los permisos a los roles | Página **Roles** | |
| 8 | El cliente y la página del frontend | `frontend/src/` | abajo |

Con un modelo, tres esquemas y un `Resource` en la ruta ya tienes siete endpoints
con paginación, búsqueda, filtros (por igualdad con varios valores, por texto y por
rango de fechas o números), orden, historial, borrado reversible y permisos: qué
parámetros admite el listado se declara en el `Resource` (`app/routes/steps.md`,
sección 3, «Parámetros del listado»). Sin el paso 6 no existe nada: ni la tabla, ni
los endpoints, ni los errores. Con migraciones en el proyecto, la tabla tampoco
aparece sola: falta `aerich migrate` y `aerich upgrade` (sección 5).

**Frontend**, para el mismo módulo. El cliente, `frontend/src/modules/products.ts`:

```ts
import { crud } from "@/core/api";

export type Product = {
	id: string;
	sku: string;
	name: string;
	price: string;
	active: boolean;
	category_id: string;
	created_at: string;
	deleted_at: string | null;
};

export type ProductCreate = {
	sku: string;
	name: string;
	price: string;
	active?: boolean;
	category_id: string;
};

export const ProductsApi = crud<Product, ProductCreate>("/products");
```

Y la página `frontend/src/pages/Products.tsx`. **Las rutas se escriben a mano** en
`frontend/src/index.tsx`: un import perezoso arriba y una entrada dentro de `ProtectedRoute`
(las páginas con sesión) o fuera de ella (públicas, como el login):

```tsx
const Products = lazy(() => import("@/pages/Products"));
// ...
{ path: "/products", component: Products },
```

```tsx
import { For } from "solid-js";
import {
	FilterSelect,
	ListTable,
	ListToolbar,
	Pagination,
	RangeFilter,
	RowActions,
	SortHeader,
	createCrudList,
} from "@/components/crud";
import { createHistory } from "@/components/history";
import { Can, NoAccess } from "@/components/layout";
import { PageHeader, createConfirm } from "@/components/ui";
import { auth } from "@/core/auth";
import { formatDate } from "@/core/format";
import { ProductsApi } from "@/modules/products";

const STATES = [
	{ value: "true", label: "Activos" },
	{ value: "false", label: "Inactivos" },
];

export default function Products() {
	const list = createCrudList(ProductsApi.list, { enabled: () => auth.can("products.list") });
	const confirm = createConfirm();
	const history = createHistory();

	return (
		<Can permission="products.list" fallback={<NoAccess />}>
			<PageHeader title="Productos" />
			<ListToolbar list={list} placeholder="Buscar por SKU o nombre">
				<FilterSelect list={list} name="active" label="Todos los estados" options={STATES} />
				<RangeFilter list={list} name="created_at" label="Creado" />
			</ListToolbar>
			<ListTable
				list={list}
				columns={4}
				empty="No hay productos que mostrar."
				head={
					<>
						<SortHeader list={list} column="sku">
							SKU
						</SortHeader>
						<SortHeader list={list} column="name">
							Nombre
						</SortHeader>
						<SortHeader list={list} column="created_at">
							Creado
						</SortHeader>
						<th class="text-right">Acciones</th>
					</>
				}
			>
				<For each={list.items()}>
					{(product) => (
						<tr>
							<td>{product.sku}</td>
							<td>{product.name}</td>
							<td>{formatDate(product.created_at)}</td>
							<td>
								<RowActions
									item={product}
									label={product.sku}
									resource="products"
									api={ProductsApi}
									confirm={confirm}
									history={history}
									onChanged={list.refetch}
								/>
							</td>
						</tr>
					)}
				</For>
			</ListTable>
			<Pagination list={list} />
			<confirm.Dialog />
			<history.Dialog />
		</Can>
	);
}
```

`RowActions` muestra historial, eliminar, restaurar y borrar según los permisos
`products.*`; el botón de editar aparece si le pasas `onEdit={(item) => ...}`, y
`deleteBlocked="motivo"` deja «Eliminar» desactivado explicando por qué.

**Los parámetros del listado en el frontend.** Lo que el `Resource` declara en el backend
(`app/routes/steps.md`, sección 3) tiene su pieza en `components/crud.tsx`:

| El `Resource` declara | En la página |
|---|---|
| `search_fields` | El cuadro de búsqueda de `ListToolbar` (con espera de 300 ms; hasta 100 caracteres, o el `maxLength` que le pases) |
| `filter_fields` | `FilterSelect` (una opción), `FilterMulti` (varias a la vez: envía `?col=a&col=b`), `FilterText` (texto exacto) o `list.filter("col", valor)` desde un control propio. Un array es «uno u otro»; `""`, `undefined` y `[]` quitan el filtro |
| `text_fields` (`<col>_contains`) | `list.filter("name_contains", texto)` desde un `<input>` propio |
| `range_fields` | `RangeFilter name="created_at"` para fechas y horas (con zona horaria y los dos extremos incluidos); para números, `list.filter("price_from", "2")` |
| `sort_fields` | `SortHeader column="name"`: un clic ordena ascendente, otro descendente y el tercero devuelve el orden propio del recurso |
| `ordering` | El orden mientras no se elija columna |

`createCrudList(fetchPage, opciones)` admite `size` (filas por página, hasta 100), `sort`
(orden inicial), `trash: false` (recursos sin borrado reversible: no envía `deleted` ni
muestra «Ver eliminados»; lo usa Auditoría) y `enabled` (mientras devuelva `false` no pide
nada: úsalo cuando el usuario no tiene el permiso). Devuelve, además de `items()`,
`total()` y `page()`: `loading()`, `error()` (por qué falló la última petición;
`ListTable` lo enseña con un botón «Reintentar»), `refetch`, `filters()`, `sort()`,
`activeFilters()` y `clearFilters()` (el botón «Limpiar filtros» de `ListToolbar`). Cambiar
la búsqueda, un filtro, el orden o «Ver eliminados» vuelve a la página 1; si borras la
última fila de la última página, la lista retrocede sola.

**Formularios.** `createForm` guarda los valores, los errores por campo (`fields` de la
API) y la clave de idempotencia, y `submit` entrega esa clave para pasarla a la llamada:

```tsx
const form = createForm({ sku: "", name: "" });

async function save(event: SubmitEvent) {
	event.preventDefault();
	const saved = await form.submit(async (values, key) => {
		const product = await ProductsApi.create(values, key);
		notify.success(`Producto ${product.sku} creado`);
	});
	if (saved) list.refetch();
}
```

La clave se mantiene si no se sabe qué pasó (sin respuesta, 5xx) y cambia al editar un
campo o al recibir una respuesta definitiva, así que un reintento no duplica el registro
(`frontend/src/core/idempotency.md`). Los campos con error se pintan con `Input`
(`error={form.errors().sku}`), que además enlaza etiqueta, ayuda y error para los lectores
de pantalla. Si el formulario va en un `Modal`, el botón de guardar lleva
`type="submit" form="id-del-formulario"`: el modal se cierra con Escape, mantiene el foco
dentro y lo devuelve al botón que lo abrió. Para el patrón completo (alta y edición en el
mismo modal, desplegable de roles, contraseña), copia `pages/Users.tsx`.

Para que la página aparezca además en el menú, añade una entrada a `NAV` en
`components/layout.tsx`:

```ts
{ href: "/products", label: "Productos", permission: "products.list" },
```

`when: () => ...` añade una condición extra (Debug lo usa para mostrarse solo a un dev con
el servidor en modo desarrollo).

**Permisos en el frontend.** La clave es la misma que en el backend:

```tsx
<Can permission="products.create" fallback={<span>Sin acceso</span>}>
	<button type="button" class="btn">Nuevo</button>
</Can>
```

```ts
if (auth.can("products.update")) { ... }
```

La pestaña `/debug` → Permisos lista todas las claves con su endpoint. Reglas que conviene
copiar de `Users.tsx` y `Roles.tsx`:

- **Pide solo lo que puedes ver.** Un dato de apoyo (la lista de roles para un selector) se
  pide únicamente si el usuario tiene su permiso
  (`createResource(() => auth.can("roles.list"), ...)`): si no, cada visita provocaría un
  `403`. `listAll` trae todas las filas de un listado, de 100 en 100, para rellenar un selector.
- **No ofrezcas lo que el servidor va a rechazar.** Quien no es dev solo concede los
  permisos que tiene (`auth.canGrant(id)`), no gestiona cuentas dev ni roles con permisos que
  no tiene, y nadie se elimina, se desactiva ni se restablece la contraseña a sí mismo (la
  propia se cambia en «Mi cuenta»). Esas acciones se ocultan o se desactivan con su motivo.
- **Si el permiso cambia con la sesión abierta**, un `403` (`PRM_001`, `PRM_002`) o volver a
  la pestaña después de un minuto vuelven a leer `/auth/me`: el menú y los botones se ajustan
  solos. Si la sesión se pierde (caduca, se cierra desde otro sitio, la cuenta se desactiva),
  se vuelve al login con un aviso y, tras entrar, a la página donde estabas; cerrar sesión en
  una pestaña la cierra en todas.
- **Los fallos del navegador** (no los de la API, que avisa el interceptor) salen como aviso
  con `reportError(error)`; una página que falla al pintarse muestra un aviso con «Reintentar»
  y «Recargar», sin tirar el menú.

**Probar el frontend a mano** (no hay `vitest`): con `bun run check` y `bun run build` en
verde, el backend en marcha y una base de pruebas:

1. Entrar con un dev y con un usuario de rol limitado (sin `events.list`): el menú, los
   botones y las rutas deben ceñirse a su rol y no debe salir ningún aviso de `403`.
2. Un listado: ordenar por cada columna, filtrar por varias opciones a la vez, un rango de
   fechas (también con «hasta» anterior a «desde»), buscar y pulsar «Limpiar filtros».
3. Crear con datos inválidos (los errores salen bajo cada campo, en español) y luego con
   datos válidos; editar; eliminar, restaurar y borrar definitivamente; ver el historial.
4. Con la sesión abierta, cerrarla desde otro sitio (`DELETE /api/users/{id}/sessions`) y
   hacer cualquier cosa: debe llevar al login con el aviso y volver a la página al entrar.
5. En dos pestañas, cerrar sesión en una: la otra sale sola.
6. Apagar el backend: aparece la pantalla «Sin conexión con el servidor» (la aplicación de
   debajo se conserva, un formulario a medias incluido) y reintenta sola; al encenderlo, se
   quita y sigues donde estabas. Con el backend apagado, cerrar sesión deja el cierre pendiente
   (aviso en el login e insignia en la barra) y se envía al volver la conexión, aunque recargues.
7. Entrar en **Debug** (dev con `DEBUG=true`): Estado (conexión, cuenta, políticas, navegador),
   Peticiones (cada llamada con su estado, duración, clave y `request_id`), Errores y Permisos.
8. Con el teclado: Tab recorre un modal sin salirse de él, Escape lo cierra y el foco vuelve
   al botón que lo abrió.

---

## 5. Base de datos y migraciones

La base de datos es **PostgreSQL**, con el driver asyncpg a través de Tortoise. No
hay otra: SQLite se eliminó por completo.

```
DATABASE_URL=postgres://usuario:clave@host:5432/base
```

La URL debe empezar por `postgres://` y, si la clave tiene `@`, `/`, `:` o `#`,
se codifican. Si la base no está en la misma máquina, añade `?ssl=true` al final
para cifrar la conexión.

**Crear la base.** El servidor no la crea: las tablas, según el caso, las crea él o
aerich (más abajo). Como administrador de PostgreSQL:

```sql
CREATE USER app WITH PASSWORD '<clave>';
CREATE DATABASE template OWNER app;
```

**Tipos nativos.** Se usan los de PostgreSQL: `uuid` para los identificadores,
`jsonb` para los cambios, instantáneas y contexto de los eventos, `timestamptz`
para todas las fechas (siempre UTC), `bytea` para los cuerpos que guarda la
idempotencia e `integer[]` para los permisos de un rol. Puedes usar los tuyos
(`ArrayField` de `tortoise.contrib.postgres.fields`, por ejemplo).

**Quién crea las tablas.** Depende de una sola cosa: si existe la carpeta
`backend/migrations/`.

| El proyecto... | Al arrancar el servidor (y en `create_admin`) |
|---|---|
| **No tiene** `backend/migrations/` (la plantilla recién clonada) | Crea las tablas que falten y no altera ninguna existente |
| **Tiene** `backend/migrations/` | **No crea ni altera nada**: el esquema es de aerich. Comprueba que la base haya recibido migraciones y, si no, no arranca |

Sin migraciones, una columna nueva en un modelo cuya tabla ya existe **no llega a la
base**. Con migraciones, **todo** cambio de esquema (una tabla, una columna, un
índice) pasa por aerich y el servidor no lo hace por ti. Cuando la base no ha
recibido ninguna migración, el servidor y `create_admin` se niegan a arrancar con:

```
RuntimeError: Este proyecto tiene migraciones y esta base no las ha recibido: ejecuta `uv run aerich upgrade` antes de arrancar.
```

La comprobación mira que la tabla `aerich` exista y tenga alguna migración aplicada.
**No detecta una migración nueva sin aplicar**: el servidor arranca y la API
responde `503 SYS_503` en lo que falte. Tras recibir migraciones nuevas (las subió
un compañero, por ejemplo), `uv run aerich upgrade`.

**Migraciones.** Se hacen con aerich, configurado en `pyproject.toml` para usar
`app.core.database.TORTOISE_ORM`. Como cualquier comando de la aplicación, lee
`backend/.env`.

```bash
cd backend && uv run aerich init-migrations
cd backend && uv run aerich upgrade
cd backend && uv run aerich migrate --name productos
cd backend && uv run aerich upgrade
```

**Preparar una base: tres situaciones.**

1. **Proyecto nuevo, sin migraciones** (la plantilla recién clonada). Base vacía,
   `create_admin` y arrancar: el servidor crea las tablas. Mientras desarrollas y los
   datos no importen, borrar la tabla (o recrear la base) y reiniciar también sirve.
   Para empezar a usar migraciones se lanzan, **una sola vez**, los dos primeros
   comandos de arriba: `init-migrations` crea `backend/migrations/` con la
   migración inicial (el estado actual de los modelos) y el primer `upgrade` la
   marca como aplicada (no toca nada: las tablas ya las creó el arranque). **Sin ese
   primer `upgrade`, `migrate` falla con un `TypeError` y el servidor no arranca.**
   Desde ahí manda la situación 2.
2. **Proyecto con migraciones, base nueva** (un compañero que clona, otro entorno,
   un servidor). El servidor no crea nada, así que el orden es este: crear la base
   vacía y su usuario (arriba), `aerich upgrade`, `create_admin` y arrancar. Con
   `create_admin` o el servidor primero, salta el error de arriba. Los triggers de
   `events` no van en las migraciones: los instala el primer arranque o
   `create_admin`.

   ```bash
   cd backend && uv run aerich upgrade
   cd backend && uv run python -m app.scripts.create_admin
   cd backend && uv run fastapi dev
   ```
3. **Reiniciar una base de desarrollo** (los datos no importan). Con el servidor
   parado (con conexiones abiertas, `DROP DATABASE` falla), se tira la base y se
   vuelve a crear; después, la situación 2. Se pierde todo, la cadena de eventos
   incluida; `create_admin` la deja otra vez lista.

   ```sql
   DROP DATABASE template;
   CREATE DATABASE template OWNER app;
   ```

   ```bash
   cd backend && uv run aerich upgrade
   cd backend && uv run python -m app.scripts.create_admin
   ```

   Sin migraciones, basta con `create_admin`.

**Cuando los modelos cambian, con migraciones.** Un `migrate` por cada cambio y un
`upgrade` en cada despliegue. Lee siempre el archivo que genera `migrate` en
`backend/migrations/` antes de aplicarlo.

- **Un modelo o una columna nuevos.** `aerich migrate --name productos` y
  `aerich upgrade`. El servidor no crea la tabla ni la columna por ti: sin el
  `upgrade`, la API responde `503 SYS_503`.
- **Una columna obligatoria en una tabla con datos.** Una columna sin `null=True` ni
  `default` (`NOT NULL`) no se puede añadir a una tabla que ya tiene filas: las
  existentes quedarían sin valor y PostgreSQL rechaza el cambio. Se hace en tres
  pasos: añádela como `null=True` (o con un `default=`) y migra; rellena las filas
  existentes (un script o un `UPDATE` a mano, que no deja historial); quita el
  `null=True`, vuelve a migrar y aplica.
- **Renombrar o quitar un campo.** Al renombrar, `aerich migrate` **pregunta por
  consola** si es un renombrado: si respondes que no, entiende «borra la columna
  vieja y crea otra vacía» y los datos de la vieja se pierden. Quitar un campo (o un
  modelo) borra su columna (o su tabla) **con todos sus datos**. Antes de un borrado,
  una copia con `pg_dump`.
- **Muchos a muchos.** La tabla intermedia (`through=...`) la crea la misma
  migración que genera `aerich migrate`: no hay que hacer nada aparte.

**Las migraciones se guardan con el proyecto.** La plantilla todavía no trae ninguna,
y aerich no se ejecuta solo: es cosa tuya lanzarlo.

**Varios procesos.** Con PostgreSQL se puede servir con varios workers: los
intentos de login, las reservas de idempotencia y la cadena de eventos viven en la
base, no en memoria. Solo el límite de eventos de error por IP (30 por minuto, ver
Convenciones) se cuenta en memoria, por proceso.

**Copia de seguridad.** Con las herramientas de PostgreSQL, por ejemplo
`pg_dump -Fc base > copia.dump`, o las copias automáticas de tu proveedor.

---

## 6. Despliegue

Sin contenedores. Necesitas **Python 3.14** (con una versión anterior el proyecto
no funciona), un PostgreSQL 14 o superior y un proxy inverso con TLS delante.

### Variables de entorno

En `backend/.env` o en el entorno del servicio. Las que cambian en producción:

| Variable | Valor |
|---|---|
| `DEBUG` | `false`: apaga `/docs` y `/openapi.json`, oculta el detalle de los errores inesperados, pone las cookies `Secure` y `SameSite=Strict` y activa HSTS |
| `DATABASE_URL` | `postgres://app:<clave>@host:5432/base`, con la clave codificada |
| `SECRET_KEY` | Propia y de 32 caracteres o más (comando en la sección 1). Cambiarla con datos reales rompe sesiones, contraseñas y auditoría |
| `CORS_ORIGINS` | La dirección pública del frontend, por ejemplo `["https://app.ejemplo.com"]`. Todo `https://`, nunca `*` |
| `JWT_ISSUER` | La URL pública de la API con `https://` |
| `APP_NAME`, `APP_VERSION` | El nombre y la versión de tu proyecto. El nombre da también el de las cookies de sesión (`<slug>_access`, `<slug>_refresh`): cambiarlo con usuarios dentro cierra todas las sesiones |

### Instalar

Con `uv`:

```bash
cd backend && uv sync --no-dev
```

`--no-dev` deja fuera las herramientas de desarrollo (`ruff`, `basedpyright`). Un
`uv run` a secas las **vuelve a instalar**, así que en el servidor todos los
comandos van con `uv run --no-dev`, como los de abajo.

Sin `uv` en el servidor, se genera una lista de dependencias en una máquina que sí
lo tenga y se instala con pip:

```bash
cd backend && uv export --format requirements-txt --no-dev --no-emit-project -o requirements.txt
python3.14 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

`requirements.txt` sale de `uv.lock`; **regenéralo cada vez que cambien las
dependencias**. Sin `uv`, lo demás se ejecuta con el entorno virtual (por
ejemplo `.venv/bin/fastapi run ...`) en lugar de `uv run`.

### Preparar la base y el primer usuario

```bash
cd backend
uv run --no-dev aerich upgrade
ADMIN_USERNAME=admin ADMIN_PASSWORD='<contraseña>' uv run --no-dev python -m app.scripts.create_admin
```

- `aerich upgrade` aplica las migraciones pendientes; solo si el proyecto ya las
  tiene (sección 5), y se ejecuta en cada despliegue. Con migraciones es
  **obligatorio y va antes de `create_admin` y de arrancar**: en una base nueva el
  servidor no crea las tablas y se niega a arrancar.
- `create_admin` con `ADMIN_USERNAME` y `ADMIN_PASSWORD` no pregunta nada y no
  duplica el usuario si ya existe: se puede repetir sin miedo. Sin migraciones, también
  crea las tablas que falten; ejecútalo antes de lanzar varios workers, para que no
  compitan por crearlas en el primer arranque. Con migraciones, comprueba como el
  servidor que la base las haya recibido.
- Recomendaciones para la base: usa un usuario propio de esa base, sin
  superusuario y sin acceso a otras. Debe ser **dueño de las tablas** (las crea el
  arranque, o aerich si hay migraciones; el arranque instala además los triggers de
  `events`, y aerich las cambia). Usa PostgreSQL 14 o superior. Y fija un
  `statement_timeout` para que una consulta atascada no ocupe conexiones para
  siempre:

```sql
ALTER DATABASE template SET statement_timeout = '30s';
```

### Lanzar

```bash
cd backend
uv run --no-dev fastapi run --host 127.0.0.1 --port 8000 --workers 4 --forwarded-allow-ips 127.0.0.1
```

`fastapi run` busca la aplicación en `pyproject.toml`. En el ejemplo, la IP de
`--forwarded-allow-ips` es la del proxy (aquí, la misma máquina). Opciones que
importan:

| Opción | Qué hace |
|---|---|
| `--host` | Dirección de escucha. **Por defecto `0.0.0.0`**: con el proxy en la misma máquina, pon `127.0.0.1` |
| `--port` | Puerto (8000 por defecto) |
| `--workers` | Número de procesos |
| `--proxy-headers` / `--no-proxy-headers` | Confiar o no en `X-Forwarded-For` y `X-Forwarded-Proto` (activo por defecto) |
| `--forwarded-allow-ips` | Direcciones de las que se aceptan esas cabeceras (por defecto solo `127.0.0.1`; también sirve la variable `FORWARDED_ALLOW_IPS`) |

**Nunca expongas uvicorn directamente a internet.** Ponle delante un proxy inverso.
Si el proxy no está en la misma máquina (otro servidor, un contenedor, un
balanceador), **fija `--forwarded-allow-ips` a su IP**: si no, el límite de
intentos de login, la idempotencia sin sesión y la auditoría verían la IP del
proxy para todos, y todos los usuarios compartirían el mismo cupo de 50 intentos
de login cada 5 minutos. No uses `*` salvo que el servidor solo sea alcanzable
desde el proxy: cualquiera podría falsear su IP.

**Ocultar la cabecera `Server`.** uvicorn envía siempre `server: uvicorn` (sin
versión) y `fastapi run` no tiene opción para quitarla. Lanzando uvicorn
directamente, con las mismas opciones, sí (comprobado con la aplicación real):

```bash
cd backend
uv run --no-dev uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4 --forwarded-allow-ips 127.0.0.1 --no-server-header
```

Desde el código de la aplicación no se puede: si una respuesta añade su propia
cabecera `Server`, uvicorn envía las dos.

**En Windows, `--workers` mayor que 1 no es fiable.** Con uvicorn 0.52.4 y Python
3.14, con 3 workers una parte de las conexiones se queda a veces sin respuesta,
incluso con una aplicación mínima de cinco líneas (3 rondas de 12; con un solo
worker, 0 de 12). En Linux no se ha comprobado: pruébalo en el sistema de
despliegue antes de fiarte.

### El proxy inverso

`fastapi run` no limita las peticiones por IP. Eso es trabajo del proxy:

| El proxy debe | Por qué |
|---|---|
| Terminar TLS (HTTPS) | Las cookies son `Secure` y la API envía HSTS: sin HTTPS no hay sesión |
| Reenviar `X-Forwarded-For` y `X-Forwarded-Proto` | Para que la API vea la IP real del cliente |
| Ocultar la cabecera `Server` (si no lanzas uvicorn con `--no-server-header`) | Revela que detrás hay uvicorn; sin versión, es un dato menor |
| Limitar peticiones por IP | Solo el login y el cambio de contraseña tienen límite propio; el resto de endpoints no |
| Limitar el tamaño del cuerpo (1 MiB) | La API ya corta en 1 MiB, pero es mejor que ni llegue |
| Servir el frontend y reenviar `/api` al backend **en el mismo dominio** | Cookies de primera parte, sin CORS y compatibles con `SameSite=Strict` |

### Frontend

```bash
cd frontend && bun install --frozen-lockfile && bun run build
```

Genera `frontend/dist/`. Sírvelo con cualquier servidor web y haz que reenvíe
`/api` al backend (`http://127.0.0.1:8000`) **en el mismo dominio**. Las rutas del
frontend (`/users`, `/roles`...) deben devolver `index.html`. Las cabeceras de
seguridad de esas páginas (por ejemplo una `Content-Security-Policy`) las pone el
servidor que las sirve: la API solo las pone en sus propias respuestas.

### Comprobar que está vivo

`GET /api/system/health` responde `200` con `{"status": "up", "database": "up"}`,
o `503` si la base de datos no contesta. No devuelve nada más.

### Lo que la plantilla no hace por ti

- **No hay límite general de peticiones**, solo el del login y el cambio de
  contraseña. Ponlo en el proxy.
- **Solo los formularios envían `Idempotency-Key`**: un botón de eliminar o restaurar
  repetido pasados 10 segundos se procesa otra vez (sección 3; cómo darle clave, en
  `frontend/src/core/idempotency.md`).
- **Las migraciones no se aplican solas**: `uv run --no-dev aerich upgrade` en cada
  despliegue. La plantilla todavía no trae ninguna: hasta que crees
  `backend/migrations/`, el servidor crea las tablas por su cuenta (sección 5).
- **No hay pruebas unitarias** (`pytest`, `vitest`): solo `backend/checks/` contra el servidor real y la lista manual del frontend (sección 4).
- **Los logs son texto plano**, del logger de uvicorn.
- **CORS admite `GET`, `POST`, `PUT`, `PATCH`, `DELETE` y `OPTIONS`** (en `main.py`).
  Con el frontend en el mismo dominio no influye; si tu API necesita otro método,
  añádelo a `allow_methods`.

---

## 7. Convenciones

- **Sin comentarios en el código.** Lo que haga falta explicar va en un docstring
  de una línea o en un `steps.md`.
- **Guion bajo delante** (`_values`, `_diff`) = privado del módulo. No lo importes
  desde otro archivo.
- **Configuración vs. constantes.** Lo que cambia entre entornos va en `Settings`
  (`app/settings.py` y `.env`). Las decisiones del sistema (duración de los tokens,
  longitud mínima de contraseña, máximo de sesiones) son constantes junto al código
  que las usa.
- **Claves:** nunca uses `SECRET_KEY` directamente; deriva una por uso con
  `settings.key("uso")`.
- **Versión:** la de la API es `APP_VERSION` (`.env`); la del frontend, la de
  `frontend/package.json`. El `version` de `backend/pyproject.toml` solo lo exige
  `uv`.
- **UTC siempre** en el backend. Las fechas que envía el frontend van en ISO con
  zona horaria (`toUtcIso` para los `datetime-local`); dar formato a fechas es
  cosa del frontend (`core/format.ts`).
- **Modelos:** heredan de `Entity`, llevan `class Meta(Entity.Meta)` con su
  `table`, tienen nombres de clase únicos en todo el proyecto y su módulo está en
  `MODELS` de `app/registry.py`.
- **Claves foráneas:** declara también el atributo `<campo>_id` con su tipo.
- **Decimales:** `PlainDecimal` en los esquemas de salida.
- **Escrituras:** nunca `QuerySet.update()` en tablas auditadas; carga el objeto y
  usa `save()`.
- **Errores:** siempre `AppError`, nunca `HTTPException`. Los propios son
  `ErrorSpec` en la lista `ERRORS`, sin llamar a `register_error`.
- **Mensajes en español:** todo lo que ve el usuario va en español. Los errores por
  campo de Pydantic ya los traduce `core/errors.py`; el de un validador propio es el
  de su `ValueError`, así que escríbelo en español.
- **Textos:** todo `str` de entrada con `max_length` (tipos `Username`, `Password` y
  `SearchText` en `core/schemas/types.py`, o `Field(max_length=n)`) y toda
  lista con su máximo. Nada lo comprueba al arrancar: es cosa tuya.
- **Nombres de usuario:** solo ASCII en minúsculas; usa `validate_username` de
  `core/schemas/validators.py`.
- **Rutas exactas:** la API no redirige la barra final (`redirect_slashes=False`).
  Una colección se llama con barra (`/api/roles/`) y el resto sin ella
  (`/api/roles/{id}`); `/api/roles` da `404`. Así no hay redirecciones que reflejen la
  cabecera `Host`.
- **Eventos de error:** un error `persist` se guarda como evento hasta 30 veces por IP y
  código cada minuto; pasado el límite solo queda en el log, para que nadie llene
  el registro a peticiones.
- **Contraseñas:** `await hash_password(...)` y `await verify_password(...)`. bcrypt
  tarda cientos de milisegundos y se ejecuta fuera del bucle de eventos.
- **Tipos de retorno de generadores:** `AsyncGenerator[X]`, no `AsyncIterator[X]`
  (basedpyright avisa).

---

## 8. Cuando algo falla

| Síntoma | Causa | Solución |
|---|---|---|
| `fastapi dev app/main.py` falla con `No module named 'app'` | Con ruta explícita, el CLI no encuentra el paquete (no hay `__init__.py`) | Ejecuta `uv run fastapi dev` sin ruta |
| La app no arranca: `DATABASE_URL es obligatoria y debe empezar por postgres://` | La URL usa otro esquema (`postgresql://`, `sqlite://`) | Usa `postgres://usuario:clave@host:5432/base` en `.env` |
| La app no arranca: `SECRET_KEY es obligatoria y debe tener al menos 32 caracteres` | Clave vacía o corta | Genera una con `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| La app no arranca: `Con DEBUG=false hay que poner tu propia DATABASE_URL` (o `SECRET_KEY`) | Producción con los valores de desarrollo de `app/settings.py` | Ponlos en `.env` o en el entorno |
| `connection refused` o `database "template" does not exist` al arrancar con los valores de desarrollo | El servicio de PostgreSQL no corre o falta la base | Arranca el servicio y crea la base: `createdb -U postgres template` |
| La app no arranca: `Con DEBUG=false JWT_ISSUER y CORS_ORIGINS deben usar https://` | Producción con un origen `http://` | Pon `https://` en `JWT_ISSUER` y en todos los `CORS_ORIGINS` |
| La app no arranca: `CORS_ORIGINS no admite *` | Las cookies viajan con credenciales | Lista los orígenes uno a uno |
| La app no arranca con un error de conexión o dice que la base no existe | La base o el usuario no existen, o la URL está mal | Crea la base y el usuario (sección 5); si la clave tiene `@ / : #`, codifícala |
| La app no arranca: `must be owner of table ...` (en español, `debe ser dueño de la tabla ...`) | El usuario de la base no es dueño de las tablas (el arranque crea índices y triggers) | Usa el usuario que las creó, o hazlo dueño (`ALTER TABLE ... OWNER TO ...`) |
| La app no arranca: `permission denied for schema public` (`permiso denegado al esquema public`) | El usuario no puede crear objetos en el esquema | Hazlo dueño de la base (`ALTER DATABASE ... OWNER TO ...`) o dale `GRANT CREATE ON SCHEMA public` |
| La app no arranca con un error de sintaxis en `CREATE OR REPLACE TRIGGER` | PostgreSQL anterior a 14 | Actualiza PostgreSQL |
| Un script o migración falla con `El registro de eventos es de solo añadir` | Intenta modificar, borrar o vaciar `events` | Es lo previsto: no se reescribe la auditoría |
| Auditoría avisa: «la base ya no impide modificar los eventos» (`append_only: false`), tenga o no rota la cadena | Alguien desactivó o quitó un trigger de `events` (`events_no_change` o `events_no_truncate`) | Reinicia la aplicación (lo reactiva y deja un evento de aviso) y averigua quién lo hizo |
| La app (o `create_admin`) no arranca: `Este proyecto tiene migraciones y esta base no las ha recibido` | Existe `backend/migrations/`, así que el servidor no crea las tablas, y esta base no tiene ninguna migración aplicada | `cd backend && uv run aerich upgrade` y vuelve a lanzar (sección 5) |
| La app no arranca: `Rutas mal declaradas: ... no declara permiso` | Un endpoint sin `requires(...)` | Añade `actor: Users = requires(PERMISO)` a su firma |
| La app no arranca: `No se encontró ningún endpoint con permiso` | La comprobación de permisos lee la estructura interna de las rutas de FastAPI y una actualización la cambió | Vuelve a la versión de `fastapi` de `uv.lock` (`uv sync`) hasta adaptar `core/permissions.py` |
| La app no arranca: `Resource.sort_fields: 'x' debe ser una columna de ... y un campo de ...` (o `filter_fields`, `text_fields`, `range_fields`) | Un campo del listado no es columna del modelo o no está en `out_schema` | `app/routes/steps.md`, sección 3, «Qué se comprueba al arrancar» |
| `El permiso 6001 (...) ya lo usa ...` | Dos permisos con el mismo número | Usa otro número dentro del bloque de tu módulo |
| `RuntimeError: Código de error duplicado` | Dos errores con el mismo código, o un error en `ERRORS` que además llama a `register_error` | Un código por error y solo la lista `ERRORS` |
| Mis endpoints dan 404 | El `router` no está en `ROUTERS` de `app/registry.py` | Impórtalo y añádelo |
| `relation "..." does not exist` (la API responde `503 SYS_503`) | El módulo del modelo no está en `MODELS`, o el proyecto tiene migraciones y falta la del modelo nuevo | Añádelo en `app/registry.py` y reinicia; con migraciones, `aerich migrate` y `aerich upgrade` |
| `ConfigurationError: No model with name 'X'...` | Una relación apunta a un modelo que no existe o no está registrado | Escribe `"models.<NombreDeLaClase>"` y comprueba `MODELS` |
| `422 VAL_422` al llamar a `/api/x/algo` | Una ruta propia declarada después de `mount()` | Declara las rutas propias antes de `mount()` |
| `422 VAL_422` con un dato que parece válido (un `\u0000` en un texto, un entero enorme) | PostgreSQL lo rechaza (SQLSTATE de clase 22) | Corrige el dato y ponle límites en el esquema |
| `409 SYS_409` al crear | Campo `unique` repetido, quizá en un registro eliminado | Restaura el registro o usa otro valor |
| `409 SYS_REL` al borrar | Hay registros que apuntan a este (`on_delete=NO_ACTION` o `RESTRICT`) | Bórralos antes o cambia el `on_delete` |
| `422 VAL_REL` | La clave foránea apunta a un registro inexistente o eliminado | Revisa el identificador; al restaurar, restaura antes el relacionado |
| `429 SYS_429` al iniciar sesión o cambiar la contraseña | 10 intentos por usuario e IP o 50 por IP en 5 minutos | Espera lo que indica `retry_after_seconds`. Si le pasa a todo el mundo, la API ve la IP del proxy: `--forwarded-allow-ips` |
| `403 USR_004` | Alguien que no es dev intentó dar o quitar la marca dev | Lo hace un dev |
| `403 USR_005` | Un usuario que no es dev intentó modificar una cuenta dev | Lo hace un dev |
| `403 PRM_003` | Escritura desde un origen que no está en `CORS_ORIGINS` | Añade la dirección del frontend |
| `403 PRM_004` | Un usuario que no es dev intentó conceder o gestionar permisos que él no tiene (un rol, o un usuario, con más permisos que los suyos) | Lo hace quien tenga esos permisos, o un dev |
| `413 SYS_413` | El cuerpo de la petición supera 1 MiB (`BodyLimitMiddleware`) | Envía menos datos; el límite se cambia en `main.py` y también en el proxy |
| `422` en fechas de `/api/events/` o `/api/events/verify` | Fecha sin zona horaria | Envíala con `toUtcIso` o con `Z` al final |
| `422 VAL_422` en un listado (`sort`, `created_at_from`, `role_id`...) | Un parámetro mal escrito o no permitido: el mensaje, en español, dice cuál y por qué | Parámetros y errores de cada uno: `app/routes/steps.md`, sección 3, «Parámetros del listado» |
| Un filtro de un listado no hace nada y no da error | El recurso no declara ese parámetro: se ignora | Decláralo en `filter_fields`, `text_fields` o `range_fields` del `Resource` |
| El precio llega como `"2E+1"` | `Decimal` normalizado en un esquema de salida | Usa `PlainDecimal` |
| Una escritura repetida devuelve lo mismo y no hace nada | Idempotencia (`Idempotent-Replayed: true`) | Envía otra `Idempotency-Key`, haz otra escritura antes o espera 10 s |
| 12 logins fallidos seguidos no bloquean | Las respuestas 4xx idénticas se repiten, no cuentan como intentos | El límite cuenta contraseñas distintas |
| `409 IDM_001` | La copia llegó con la original en curso y esta tardó más de 15 s | Espera a la primera |
| `422 IDM_002` | La misma `Idempotency-Key` con otra ruta o cuerpo | Genera una clave nueva por operación |
| Un cambio no se guardó aunque la ruta llegó al final | La ruta lanzó un error después y la transacción se deshizo | Revisa el error con su `request_id` |
| Un cambio no aparece en el historial | Se hizo con `update()`, `bulk_create()` o en muchos a muchos | Usa el objeto y `save()` |
| Un rol no ve un módulo nuevo | Los roles existentes no reciben permisos nuevos solos | Asígnalos en **Roles** |
| `RuntimeError: usa soft_delete()` | Se llamó a `item.delete()` | Usa `soft_delete()` o `hard_delete()` |
| Una columna nueva no existe en la base | Sin migraciones, el arranque solo crea las tablas que faltan, no altera las existentes; con migraciones, no crea nada | Aplica una migración de aerich: `aerich migrate` y `aerich upgrade` (sección 5) |
| El `upgrade` de una migración falla al añadir una columna obligatoria | La tabla ya tiene filas y la columna es `NOT NULL` sin valor | Añádela con `null=True` o con `default`, rellena las filas y vuelve a migrar (sección 5) |
| Tras cambiar `APP_NAME`, todos tienen que volver a entrar | Las cookies de sesión se llaman `<slug>_access` y `<slug>_refresh`: con otro nombre, las viejas no se leen | Es lo esperado; vuelve a iniciar sesión (o vuelve a poner el `APP_NAME` anterior) |
| Dos proyectos en `localhost` se cierran la sesión el uno al otro | Tienen el mismo `APP_NAME`, así que comparten cookies (no distinguen puertos) | Pon un `APP_NAME` distinto en cada uno (sección 1) |
| Tras cambiar `SECRET_KEY` nadie entra y Auditoría marca la cadena como rota | Las contraseñas y la firma de los eventos dependen de esa clave | Vuelve a poner la clave anterior |
| En producción el login funciona pero al recargar vuelve al login | Las cookies son `Secure` y `SameSite=Strict`: sin HTTPS, o con la API en otro sitio, no viajan | Sirve todo por HTTPS y el frontend y `/api` en el mismo dominio |
| `/docs` da 404 | `DEBUG=false`: la documentación solo existe en desarrollo (`/redoc` nunca existe) | Actívala en tu `.env` local |
| El frontend no encuentra una página | El archivo no está en `src/pages/` o no exporta `default` | Revisa nombre y `export default function` |

Cualquier error de la API trae `request_id`: búscalo en los logs o en **Auditoría**
para ver todo lo que pasó en esa petición.
