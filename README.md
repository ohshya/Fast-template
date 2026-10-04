# Template — FastAPI + SolidJS

Plantilla para arrancar proyectos: sesiones con cookies, roles y permisos por
endpoint, auditoría firmada de todo lo que pasa, un único sistema de errores que
el frontend consume sin `try/catch` de más, y módulos que se declaran en un
archivo y funcionan solos.

**¿Vas a desarrollar sobre la plantilla? Lee [GUIA.md](GUIA.md).**

```
Template/
├── GUIA.md                     Cómo funciona todo y dónde se trabaja
├── backend/                    FastAPI + Tortoise ORM + PostgreSQL (uv, Python 3.14)
│   ├── .env.example            Configuración de ejemplo: se copia a .env
│   └── app/
│       ├── main.py             Arma la aplicación
│       ├── settings.py         Lee y valida la configuración (con valores de desarrollo)
│       ├── registry.py         Tu registro: modelos, rutas, middlewares y errores
│       ├── core/               El sistema: models, schemas, services, routes, middlewares. No se edita
│       ├── models/             Tus tablas                      (steps.md)
│       ├── schemas/            Tus formas de entrada y salida  (steps.md)
│       ├── routes/             Tus endpoints y permisos        (steps.md)
│       ├── services/           Tu lógica de negocio            (steps.md)
│       ├── errors/             Tus errores                     (steps.md)
│       ├── middlewares/        Tus middlewares                 (steps.md)
│       └── scripts/            create_admin
└── frontend/                   SolidJS + Tailwind 4 + daisyUI 5 (bun)
    └── src/
        ├── core/               Cliente HTTP, sesión, formularios, rutas y formato
        ├── modules/            Tipos y llamadas de cada módulo del backend
        ├── components/         UI, layout, piezas CRUD e historial
        ├── pages/              Una página por archivo; se registran a mano en index.tsx
        └── features/debug/     Paneles de /debug: Estado, Peticiones, Errores y Permisos
```

Cada carpeta de trabajo del backend lleva un `steps.md` con las instrucciones
para esa pieza: todos los tipos de campo y relaciones de un modelo, cómo validar,
cómo declarar permisos y endpoints, dónde va la lógica.

## Arrancar

Necesitas Python 3.14, `uv`, `bun` y un PostgreSQL 14 o superior con una base ya creada (el
servidor no crea la base; las tablas sí, mientras el proyecto no tenga migraciones).

```bash
cd backend && uv sync
```

**En desarrollo no hace falta `.env`**: `backend/app/settings.py` trae valores por defecto
(`postgres://postgres:admin@localhost:5432/template` y una clave fija), que solo valen con
`DEBUG=true`. Solo tienes que crear la base (ajusta usuario y clave si los tuyos son otros):

```bash
createdb -U postgres template
```

Para usar otros valores, copia `backend/.env.example` a `backend/.env` y edita
`DATABASE_URL` y `SECRET_KEY` (de al menos 32 caracteres; puedes generar una con):

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Con `DEBUG=false` (producción) el servidor no arranca si siguen los valores de
desarrollo: pon los tuyos. El repositorio no trae `.env`. El primer usuario queda como `dev`; ese usuario crea después los
roles a mano. Si el proyecto ya tiene `backend/migrations/` (la plantilla recién
clonada no), en una base nueva va antes `uv run aerich upgrade`: con migraciones, el
servidor no crea las tablas (ver [GUIA.md](GUIA.md), sección 5).

```bash
cd backend && uv run python -m app.scripts.create_admin
```

```bash
cd backend && uv run fastapi dev
```

```bash
cd frontend && bun install && bun run dev
```

El frontend llama a `/api` y Vite lo reenvía al backend: todo ocurre en el
mismo origen, sin CORS y con cookies de primera parte. Documentación de la API
en <http://127.0.0.1:8000/docs> (solo con `DEBUG=true`; `/redoc` no existe).
La referencia de los endpoints (sesión, errores, listados con filtros, auditoría, límites y recetas) está en [backend/API.md](backend/API.md).

Se ejecuta `fastapi dev` **sin ruta**: encuentra la aplicación en
`[tool.fastapi]` de `pyproject.toml`.

Para dar nombre a un proyecto nuevo se editan a mano `APP_NAME` en `backend/.env` y
en `frontend/src/core/app.ts`, el `<title>` de `frontend/index.html` y el `name` de
`frontend/package.json`. De `APP_NAME` salen también los nombres de las cookies de
sesión (`<slug>_access` y `<slug>_refresh`): dos proyectos en `localhost` con nombre
distinto no se cierran la sesión, y cambiarlo cierra las sesiones abiertas.

## Qué trae

- **Un solo sistema de errores.** Cualquier fallo, previsto o no, sale con la
  misma forma (`code`, `message`, `toast`, `request_id`, `fields`...). El
  interceptor del frontend muestra el aviso cuando `toast` es verdadero y
  renueva la sesión cuando el token caduca. Los errores de PostgreSQL se
  traducen por su código SQLSTATE.
- **Un permiso por endpoint.** Cada ruta declara un permiso con número estable;
  un rol es una lista de esos números y `dev` entra a todo. Si una ruta no
  declara permiso, la aplicación no arranca. Solo un dev gestiona cuentas dev, y
  quien no es dev no puede conceder ni gestionar más permisos de los que tiene.
- **Escrituras atómicas.** Cada escritura va en una transacción con sus eventos:
  si algo falla, no queda nada a medias.
- **Nada se borra.** Las tablas heredan de `Entity`: identificador UUIDv7,
  borrado reversible e historial automático en una cadena de eventos numerada y
  firmada que detecta filas editadas, borradas o quitadas del final. La base impide
  modificar los eventos (triggers instalados al arrancar) y la cadena se puede
  verificar entera, por periodo o evento a evento.
- **Registro explícito.** Nada se carga solo: un modelo, una ruta, un error o un
  middleware existen cuando los importas en `app/registry.py` (listas `MODELS`,
  `ROUTERS`, `ERRORS` y `MIDDLEWARES`). `Resource` genera los siete endpoints CRUD
  de un modelo con paginación, búsqueda, filtros (igualdad con varios valores,
  texto y rangos), orden y validación de nulos, únicos y claves foráneas.
- **Idempotencia.** Una escritura repetida (doble clic, reintento) se procesa
  una sola vez y la copia recibe la misma respuesta. También acepta la cabecera
  `Idempotency-Key`, que el frontend todavía no envía; cómo hacerlo está en
  [frontend/src/core/idempotency.md](frontend/src/core/idempotency.md).
- **Seguridad.** Tokens rotatorios en cookies `httponly` (`Secure` y
  `SameSite=Strict` en producción), sesiones que caducan a los 30 días, detección
  de tokens robados, límite de intentos de login en base de datos, defensa CSRF
  por `Origin`, límite de cuerpo de 1 MiB, cabeceras de seguridad en cada
  respuesta y una clave distinta derivada de `SECRET_KEY` para cada uso.
- **Textos con límite.** El límite de cada campo lo decides tú, en su columna y en
  su esquema (usuario 50 y contraseña 128 están en `core/schemas/validators.py`);
  el frontend los repite en `frontend/src/core/limits.ts` para sus formularios.
- **Depuración.** La página **Debug** del frontend (solo dev) provoca errores para
  ver cómo llegan y lista el catálogo de permisos.
- **PostgreSQL.** La base de datos es PostgreSQL (asyncpg). Mientras el proyecto
  no tiene `backend/migrations/`, el arranque crea las tablas que falten; con
  migraciones, el esquema es de aerich (`uv run aerich upgrade` antes de arrancar
  una base nueva) y para cambiar tablas existentes se usan sus migraciones.

## Antes de producción

`DEBUG=false` (por defecto está en `true`, para desarrollo), `SECRET_KEY` propia,
`JWT_ISSUER` y `CORS_ORIGINS` con `https://`, un usuario de PostgreSQL propio con
`statement_timeout`, y un proxy inverso con TLS delante: `fastapi run` no oculta la
cabecera `Server` (uvicorn directo con `--no-server-header` sí) ni limita peticiones
por IP, y detrás de un proxy hay que fijar `--forwarded-allow-ips`. La lista completa
de variables y los comandos de despliegue están en [GUIA.md](GUIA.md), secciones 1 y 6.

## Comprobaciones

No hay pruebas unitarias (`pytest` y `vitest` están desinstalados). Con el servidor en
marcha y una base de pruebas, `cd backend && uv run python -m checks.run_all` ejercita la
API real (humo, filtros, sesión, idempotencia, cadena de eventos, ataque externo y que
`backend/API.md` coincida con ella); ver `backend/checks/README.md`.

```bash
cd backend && uv run basedpyright
cd backend && uv run ruff check .
cd backend && uv run ruff format --check .
cd frontend && bun run check
```
