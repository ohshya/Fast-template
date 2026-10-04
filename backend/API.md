# API del backend

Referencia para quien tiene que **usar** el backend (el frontend, un script, otro servicio) sin
leer su código: cómo entrar, qué se puede llamar, qué devuelve cada cosa, qué errores esperar y
qué límites hay. Está comprobada contra el código y contra un servidor local en marcha; los
ejemplos de respuesta son capturas reales (se recortan con `…`). Los identificadores, las fechas
y los sufijos aleatorios (como `bb73c`) cambian en cada ejecución. Tres ejemplos no se pudieron
capturar (el `429`, el `VAL_REL` y un elemento de historial de una edición): se construyen a
partir del código y van marcados.

1. [Introducción](#1-introducción)
2. [Autenticación y sesión](#2-autenticación-y-sesión)
3. [Formato de errores](#3-formato-de-errores)
4. [Listados (Resource)](#4-listados-resource)
5. [Escrituras](#5-escrituras)
6. [Permisos](#6-permisos)
7. [Auditoría](#7-auditoría)
8. [Referencia de endpoints](#8-referencia-de-endpoints)
9. [Recetas](#9-recetas)
10. [Resumen de límites](#10-resumen-de-límites)

---

## 1. Introducción

### 1.1 Dónde está

| Qué | Dirección |
|---|---|
| La API | `/api`. En desarrollo: `http://127.0.0.1:8000/api` (`uv run fastapi dev` desde `backend/`) |
| Documentación interactiva (Swagger UI) | `/docs` |
| Esquema OpenAPI en JSON | `/openapi.json` |

`/docs` y `/openapi.json` existen **solo con `DEBUG=true`**; con `DEBUG=false` dan `404`. `/redoc`
no existe nunca. Con el frontend en marcha, Vite reenvía `/api` al backend: el frontend llama a
`/api/...` en su mismo origen, sin CORS y con cookies de primera parte.

### 1.2 Formato

- **JSON en UTF-8** en las dos direcciones. Toda petición con cuerpo lleva
  `Content-Type: application/json`: sin esa cabecera el cuerpo no se interpreta y la respuesta es
  `422 VAL_422` con `fields: {"body": "Debe ser un objeto"}`. Con `curl`, `-d` solo no basta:
  hay que añadir `-H "Content-Type: application/json"`.
- **Ids: UUIDv7** en texto (`01a0f5b4-e792-773b-ad8f-568ca3c83784`). Llevan la fecha de creación
  dentro, así que ordenar por id es ordenar por creación.
- **Fechas: ISO 8601 en UTC con `Z`** y microsegundos (`2026-10-01T04:24:28.646031Z`). En los
  parámetros de la URL las fechas deben llevar zona horaria (`Z` o `+02:00`; el `+` se escribe
  `%2B` en una URL). Dentro de `changes` y `snapshot` (el JSON del historial) las fechas salen
  como `2026-10-01T04:24:29.686860+00:00`.
- **Booleanos** en la URL: `true` o `false`.
- **Textos en español**: mensajes de error, de validación y `detail` de las acciones.
- **La barra final importa.** La API no redirige (`redirect_slashes=False`): la colección se
  llama **con** barra y todo lo demás **sin** ella. Una barra de más o de menos da
  `404 SYS_404`.

| Correcto | Da `404 SYS_404` |
|---|---|
| `/api/users/` | `/api/users` |
| `/api/users/{id}` | `/api/users/{id}/` |
| `/api/auth/me` | `/api/auth/me/` |
| `/api/events/stats` | `/api/events/stats/` |

- **Autenticación solo por cookie.** La API no lee `Authorization: Bearer`; ver
  [sección 2](#2-autenticación-y-sesión).
- **Sin límite general de peticiones.** Solo el login y el cambio de contraseña tienen límite de
  intentos. Limitar por IP es cosa del proxy inverso.

### 1.3 Qué enseña `/docs`

Con `DEBUG=true`, cada endpoint de `/api` aparece en `/docs` con:

- **Resumen** (`summary`): la descripción de su permiso, en español (`Listar roles`,
  `Cerrar la sesión actual`).
- **Descripción**: el docstring de la función, si lo tiene, y al final una línea fija
  `Permiso: users.list (id 3001). Acceso: usuarios cuyo rol lo incluya (y los dev).`
- **`x-permission`**: extensión de OpenAPI con `{"id": 3001, "key": "users.list", "scope": "role"}`.
  `scope` es `public`, `authenticated`, `role` o `dev` (ver [sección 6](#6-permisos)).
- Parámetros de ruta, de query y de cuerpo con tipos y límites; y los esquemas de respuesta.

Los textos de `Acceso` son cuatro: *público, sin sesión*; *cualquier usuario con sesión*;
*usuarios cuyo rol lo incluya (y los dev)*; *solo usuarios dev*.

Para listar todos los endpoints con su permiso desde un script:

```python
import httpx

spec = httpx.get("http://127.0.0.1:8000/openapi.json").json()
for path, operations in spec["paths"].items():
    for method, operation in operations.items():
        print(f"{method.upper():6} {path:45} {operation['x-permission']['key']}")
```

```text
POST   /api/auth/login                               auth.login
POST   /api/auth/refresh                             auth.refresh
POST   /api/auth/logout                              auth.logout
GET    /api/auth/me                                  auth.me
…
```

### 1.4 Cómo se relaciona con el resto de la documentación

| Documento | Para qué sirve |
|---|---|
| Este (`backend/API.md`) | **Usar** la API: flujos, formatos, errores, límites, recetas. Está escrito a mano |
| `/docs` | Referencia viva, generada del código: siempre al día y permite probar peticiones. Si difiere de este documento, manda `/docs` |
| `backend/app/*/steps.md` | **Escribir** endpoints propios: modelos, esquemas, rutas, servicios, errores, middlewares |
| `GUIA.md` | Cómo funciona todo por dentro, despliegue y solución de problemas |
| `frontend/src/core/idempotency.md` | Cómo enviar la cabecera `Idempotency-Key` desde el frontend |

### 1.5 Mapa de la API

| Grupo | Prefijo | Endpoints | Ids de permiso |
|---|---|---|---|
| Sistema | `/api/system` | 5 | 1001–1005 |
| Sesión | `/api/auth` | 8 | 2001–2008 |
| Usuarios | `/api/users` | 10 | 3001–3007 y 3011–3013 |
| Roles | `/api/roles` | 7 | 4001–4007 |
| Auditoría | `/api/events` | 5 | 5001–5005 |

Son 35 endpoints, reunidos en la [sección 8](#8-referencia-de-endpoints). Los módulos propios de
cada proyecto usan ids desde el `6000`, cuelgan también de `/api` y salen con el mismo formato
de errores, listados y permisos.

### 1.6 Convención de los ejemplos

Los ejemplos de shell usan estas variables y un *cookie jar* de `curl`:

```bash
API=http://127.0.0.1:8000/api
JAR=jar.txt
```

En PowerShell, `curl` es un alias de otra cosa: usa `curl.exe` (o Git Bash). Las variables se
escriben `$API = "http://127.0.0.1:8000/api"` y las de entorno, `$env:NOMBRE = "valor"`.

---

## 2. Autenticación y sesión

### 2.1 Cómo viaja la sesión

La sesión viaja en **dos cookies `httpOnly`** que pone el servidor al iniciar sesión. El cliente
solo tiene que guardarlas y reenviarlas: un navegador lo hace con `credentials: "include"`
(`withCredentials` en axios) y `curl` con un cookie jar. El frontend nunca las lee ni las escribe.

| Cookie | Contiene | Dura | Atributos |
|---|---|---|---|
| `<slug>_access` | Token de acceso (JWT) | 15 minutos (`Max-Age=900`) | `HttpOnly; Path=/` |
| `<slug>_refresh` | Token de refresco (JWT) | 7 días (`Max-Age=604800`) | `HttpOnly; Path=/` |

Además, con `DEBUG=true` llevan `SameSite=Lax` y sin `Secure`; con `DEBUG=false`,
`SameSite=Strict` y `Secure` (frontend y API deben servirse bajo el mismo dominio y por https).

El `<slug>` se deriva de `APP_NAME`: minúsculas, cada tramo de caracteres que no son `a-z` ni `0-9`
pasa a un guion, sin guiones en los extremos, y `app` si no queda nada. Con el `APP_NAME=Template`
del `.env.example` son `template_access` y `template_refresh`; `APP_NAME="Mi Proyecto"` daría
`mi-proyecto_access`. Así dos proyectos en el mismo dominio no se pisan las cookies.

Esto es lo que el servidor envía al iniciar sesión (captura real; el valor del token se omite):

```text
set-cookie: template_access=<valor>; HttpOnly; Max-Age=900; Path=/; SameSite=lax
set-cookie: template_refresh=<valor>; HttpOnly; Max-Age=604800; Path=/; SameSite=lax
```

### 2.2 El flujo

```text
POST /api/auth/login      200  + las dos cookies            (cuerpo: el perfil, igual que /auth/me)
GET  /api/...             200  con las cookies
        … a los 15 minutos el acceso caduca …
GET  /api/...             401  AUT_002 (el navegador ya no envía la cookie caducada)
POST /api/auth/refresh    200  + dos cookies nuevas         → repetir la petición que falló
POST /api/auth/logout     200  + cookies borradas
```

Regla para un cliente: ante un `401` de cualquier ruta **que no sea** login, refresh o logout,
llamar **una vez** a `/auth/refresh` y repetir la petición; si el refresh también falla, la
sesión terminó y hay que volver a pedir login. Los refrescos deben hacerse **de uno en uno**
(entre pestañas o procesos también): ver la reutilización en el apartado 2.4.

### 2.3 Cuánto dura todo

| Qué | Valor | Detalle |
|---|---|---|
| Token de acceso | 15 minutos | Se vuelve a emitir en cada `/auth/refresh` |
| Token de refresco | 7 días | **Rota** en cada uso: el anterior deja de valer |
| Vida absoluta de la sesión | 30 días desde que se abrió | Aunque se renueve sin parar; al cumplirse, `401 AUT_003` y hay que iniciar sesión otra vez |
| Sesiones abiertas por usuario | 5 | Al abrir la sexta se cierra la que lleva más tiempo sin actividad |
| Actividad de la sesión | Se anota como mucho cada 60 s | Es el `last_activity` de `GET /auth/sessions` |
| Intentos de login | 10 por usuario e IP, 50 por IP, cada 5 minutos | Ver 2.7 |

`GET /api/system/info` devuelve los valores vigentes de casi todos ellos
(`access_expire_minutes`, `refresh_expire_days`, `max_sessions_per_user`, `password_min_length`,
`login_attempts`, `login_attempts_per_ip`, `login_window_seconds`).

### 2.4 Renovación, rotación y reutilización

`POST /api/auth/refresh` no lleva cuerpo: usa la cookie de refresco y responde
`{"detail": "Sesión renovada"}` con **dos cookies nuevas**.

- Cada renovación sustituye los dos tokens. El token de refresco anterior y el de acceso
  anterior **dejan de valer de inmediato** (un acceso ya rotado da `401 AUT_004`). Por eso una
  petición que salió con el acceso viejo mientras otra pestaña renovaba recibe `401`, y el
  cliente la repite tras renovar.
- **Reutilización.** Presentar un token de refresco que ya se usó (un robo, o dos pestañas o
  procesos renovando a la vez con la misma cookie) **cierra la sesión entera**: el servidor
  anota un evento de seguridad de gravedad `critical`, responde `401 AUT_004` y borra las
  cookies. Hay que volver a iniciar sesión. Cuando dos renovaciones llegan a la vez, solo una
  gana y la otra cierra la sesión: serializa los refrescos.
- **Cualquier fallo de `/auth/refresh` borra las cookies** en la propia respuesta
  (`Set-Cookie` con `Max-Age=0`).
- La sesión caduca a los 7 días sin renovarse, o a los 30 desde que se abrió, lo que ocurra antes.
- Al abrir una sexta sesión se cierra la más antigua (la de `last_activity` más antiguo); sus
  tokens dan `401 AUT_004` desde ese momento.
- `POST /api/auth/logout` cierra la sesión y borra las cookies. Eliminar a un usuario o
  restablecerle la contraseña cierra **todas** sus sesiones; cambiársela él mismo cierra las
  demás. Desactivarlo (`is_active: false`) no las cierra, pero desde ese momento cada petición suya
  recibe `403 AUT_006`.

### 2.5 Los `401` y `403` de sesión

| Código | HTTP | Cuándo | Qué hace el cliente |
|---|---|---|---|
| `AUT_001` | 401 | Usuario o contraseña incorrectos (solo en login) | Muestra el error. Cada fallo cuenta para el límite de intentos |
| `AUT_002` | 401 | No llegó cookie de acceso: nunca hubo sesión, se cerró, o el navegador descartó la cookie caducada | Un `/auth/refresh`; si falla, login |
| `AUT_003` | 401 | Token caducado, o sesión caducada (7 días sin renovar, 30 desde que se abrió). Un navegador no llega a enviar un acceso caducado: se ve al reenviar a mano una cookie vieja | Igual |
| `AUT_004` | 401 | Token no válido: firma, emisor o tipo incorrectos; acceso ya rotado; sesión cerrada o revocada; usuario eliminado; refresco reutilizado | Un `/auth/refresh`; si también da `AUT_004`, login |
| `AUT_006` | 403 | La cuenta está desactivada (`is_active: false`), en login o con una sesión abierta | Mostrar el mensaje; renovar no sirve |

`AUT_001`, `AUT_004` y `AUT_006` se guardan como evento de auditoría (llevan `event_id`).

### 2.6 Protección CSRF por `Origin`

Toda **escritura** (`POST`, `PUT`, `PATCH`, `DELETE`) bajo `/api` pasa por esta comprobación,
solo si la petición trae cabecera `Origin`:

| Petición | Resultado |
|---|---|
| Sin cabecera `Origin` (`curl`, un script, otro servidor) | Pasa: no es un ataque desde el navegador de otro usuario |
| `Origin` igual al propio servidor (mismo host y puerto que la cabecera `Host`) | Pasa |
| `Origin` incluido en `CORS_ORIGINS` (por defecto `http://localhost:5173` y `http://127.0.0.1:5173`) | Pasa |
| Cualquier otro `Origin`, que es lo que envía un navegador desde otra web | `403 PRM_003`, con `details.origin`, y queda como evento de seguridad |

Un navegador envía siempre `Origin` en una escritura entre sitios, por eso la comprobación lo
detiene. Las lecturas (`GET`) no se comprueban aquí. Captura real:

```bash
curl -s -X POST $API/auth/logout -H "Origin: https://sitio-malicioso.example"
```

```json
{
  "error": {
    "code": "PRM_003",
    "message": "La solicitud viene de un sitio web no autorizado.",
    "toast": true,
    "severity": "error",
    "request_id": "01a0f5b4-fab9-77e3-a29e-293f58007fc1",
    "event_id": "01a0f5b4-fabe-75f4-be2d-581ccf8695b0",
    "fields": null,
    "details": { "origin": "https://sitio-malicioso.example" }
  }
}
```

Un script no debe enviar `Origin` salvo que sea uno de los permitidos. Desde un navegador que
sirve el frontend en otro origen, ese origen tiene que estar en `CORS_ORIGINS`.

### 2.7 Límite de intentos de login

El intento se anota **antes** de comprobar la contraseña, en la base de datos:

| Contador | Máximo | Ventana |
|---|---|---|
| Usuario (en minúsculas) desde una misma IP | 10 | 5 minutos (300 s) deslizantes |
| Cualquier usuario desde una misma IP | 50 | 5 minutos |

- El intento número 11 (o el 51) recibe `429 SYS_429` y **no se cuenta**. Un login correcto
  borra los intentos de ese usuario e IP.
- `details.retry_after_seconds` dice cuántos segundos faltan para que salga de la ventana el
  intento más antiguo (mínimo 1). **No hay cabecera `Retry-After`.**
- `POST /api/auth/password` comparte el mismo contador (con el usuario de la sesión).
- El contador cuenta también los intentos en curso: más de 50 logins simultáneos desde una
  misma IP reciben `429` aunque acierten. Detrás de un proxy hay que fijar
  `--forwarded-allow-ips`; si no, todos los clientes comparten la IP del proxy.
- Dos logins idénticos y seguidos con una contraseña equivocada no cuentan como dos intentos: el
  segundo recibe la respuesta guardada del primero ([5.9](#59-solicitudes-repetidas-e-idempotency-key)).
- El login tarda lo mismo exista o no el usuario.

Respuesta (**construida a partir del código**; el recorrido de capturas no llegó al límite):

```json
{
  "error": {
    "code": "SYS_429",
    "message": "Demasiadas peticiones. Intenta de nuevo en unos segundos.",
    "toast": true,
    "severity": "warning",
    "request_id": "…",
    "event_id": "…",
    "fields": null,
    "details": { "retry_after_seconds": 212 }
  }
}
```

### 2.8 Reglas de usuario y contraseña

**Nombre de usuario** (al crear y al editar):

- De 3 a 50 caracteres, tras quitar espacios de los extremos.
- Solo ASCII: letras sin acentos, números, punto (`.`), guion (`-`) y guion bajo (`_`).
- Se guarda **en minúsculas**: `Ana` y `ana` son la misma cuenta. Al iniciar sesión se normaliza
  igual (sin espacios en los extremos y en minúsculas), pero el login **no** aplica estas reglas:
  un nombre raro da `401 AUT_001`, no `422`.
- Es único **también entre los usuarios eliminados**.

**Contraseña** (al crear usuario, restablecer, y como `new_password` al cambiarla):

- De 8 a 128 caracteres.
- Sin espacios al principio ni al final (los de dentro valen).
- Al menos una letra y al menos un número.
- Al **iniciar sesión** solo se exige un máximo de 128: una política más estricta en el futuro no
  deja fuera a quien ya tiene contraseña.

| Fallo | Mensaje en `fields` |
|---|---|
| Menos de 3 caracteres (usuario) | `Debe tener al menos 3 caracteres` |
| Más de 50 caracteres (usuario) | `Máximo 50 caracteres` |
| Caracteres no permitidos (usuario) | `Solo letras sin acentos, números, punto, guion y guion bajo` |
| Menos de 8 caracteres (contraseña) | `Debe tener al menos 8 caracteres` |
| Más de 128 caracteres (contraseña) | `Máximo 128 caracteres` |
| Espacios en los extremos | `No puede empezar ni terminar con espacios` |
| Sin número | `Debe incluir al menos un número` |
| Sin letra | `Debe incluir al menos una letra` |

### 2.9 Primer contacto con `curl`

Necesitas un usuario `dev`. Se crea una sola vez con el script, con la base ya creada y
configurada en `backend/.env`. Si el proyecto ya tiene `backend/migrations/`, antes hay que
ejecutar `uv run aerich upgrade`: con migraciones, el servidor no crea las tablas por su cuenta.

```bash
cd backend
ADMIN_USERNAME=dev ADMIN_PASSWORD=Dev12345 uv run python -m app.scripts.create_admin
uv run fastapi dev
```

Y con el servidor en marcha, la secuencia completa (`-c` guarda las cookies, `-b` las envía;
`-i` enseña las cabeceras):

```bash
API=http://127.0.0.1:8000/api
JAR=jar.txt

curl -i -c $JAR -X POST $API/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"dev","password":"Dev12345"}'
```

```text
HTTP/1.1 200 OK
content-type: application/json
x-request-id: 01a0f5b4-e573-7030-82c2-e311cc244952
set-cookie: template_access=<valor>; HttpOnly; Max-Age=900; Path=/; SameSite=lax
set-cookie: template_refresh=<valor>; HttpOnly; Max-Age=604800; Path=/; SameSite=lax

{"id":"01a0f5b4-6173-7230-bf04-04b1172df60c","username":"dev","is_active":true,"dev":true,"role_id":null,"role_name":null,"permissions":[1004,3001,…],"permission_keys":["system.errors","users.list",…],"last_login_at":"2026-10-01T04:24:28.646031Z"}
```

```bash
curl -s -b $JAR $API/auth/me
```

```json
{
  "id": "01a0f5b4-6173-7230-bf04-04b1172df60c",
  "username": "dev",
  "is_active": true,
  "dev": true,
  "role_id": null,
  "role_name": null,
  "permissions": [1004, 3001, "…"],
  "permission_keys": ["system.errors", "users.list", "…"],
  "last_login_at": "2026-10-01T04:24:28.646031Z"
}
```

```bash
curl -s -b $JAR -c $JAR -X POST $API/auth/refresh
```

```json
{ "detail": "Sesión renovada" }
```

```bash
curl -s -b $JAR -c $JAR -X POST $API/auth/logout
```

```json
{ "detail": "Sesión cerrada" }
```

Tras el logout el servidor borra las cookies (`Max-Age=0`), `curl` las quita del jar y la
siguiente llamada ya no lleva sesión:

```bash
curl -s -b $JAR $API/auth/me
```

```json
{
  "error": {
    "code": "AUT_002",
    "message": "Necesitas iniciar sesión para continuar.",
    "toast": false,
    "severity": "info",
    "request_id": "01a0f5b4-fa97-776f-8500-4c4b3e344090",
    "event_id": null,
    "fields": null,
    "details": {}
  }
}
```

Si te equivocas de contraseña, la respuesta es `401 AUT_001` y, **sin cookies**:

```json
{
  "error": {
    "code": "AUT_001",
    "message": "Usuario o contraseña incorrectos.",
    "toast": true,
    "severity": "warning",
    "request_id": "01a0f5b4-e3dd-7510-a2b2-e65e5f2e9e17",
    "event_id": "01a0f5b4-e564-772b-8fe1-a29ad986bab8",
    "fields": null,
    "details": { "username": "dev" }
  }
}
```

---

## 3. Formato de errores

### 3.1 La forma

**Todo** error de `/api` sale con la misma forma, sea previsto o no (validación, permisos, una
ruta que no existe, un cuerpo demasiado grande, un fallo interno):

```json
{
  "error": {
    "code": "SYS_409",
    "message": "Ya existe un registro con esos datos.",
    "toast": true,
    "severity": "warning",
    "request_id": "01a0f5b4-e82b-728d-8418-eeb0b5dc5ba9",
    "event_id": null,
    "fields": { "name": "Ya existe un registro con este valor" },
    "details": {}
  }
}
```

| Campo | Tipo | Significado |
|---|---|---|
| `code` | texto | Código estable (`PREFIJO_NNN`). **Es lo que el código debe comparar**, no el mensaje |
| `message` | texto | Texto en español para mostrar a la persona. Es fijo para cada código |
| `toast` | booleano | Sugerencia para la interfaz: `true`, mostrar un aviso emergente; `false`, el propio formulario o pantalla ya lo muestra (por ejemplo `AUT_002` o `IDM_001`) |
| `severity` | texto | `info`, `warning`, `error` o `critical` |
| `request_id` | texto | Id (UUIDv7) de esta petición. Es el mismo que trae la cabecera `X-Request-ID` |
| `event_id` | texto o `null` | Id del evento de auditoría donde el servidor dejó constancia del error. `null` si ese error no se guarda |
| `fields` | objeto o `null` | Mensaje por campo (`{"campo": "mensaje"}`). Solo en errores de validación, de duplicados, de relaciones y de permisos de un rol |
| `details` | objeto | Datos extra según el código. Siempre es un objeto (`{}` si no hay) |
| `debug` | texto | Solo con `DEBUG=true` y en errores inesperados (`500`): `TipoDeExcepción: mensaje`. Nunca en producción |

Qué lleva `details` en cada caso:

| Código | `details` |
|---|---|
| `AUT_001` | `{"username": "dev"}`: el nombre que se envió |
| `PRM_001`, `PRM_002` | `{"permission": "events.list"}`: la clave del permiso que falta |
| `PRM_003` | `{"origin": "https://…"}` |
| `PRM_004` | `{"permissions": [3001, 3002]}`: los ids de permiso que sobran |
| `USR_005` | `{"user_id": "…"}` |
| `ROL_003` | `{"role_id": "…"}` |
| `ROL_004` | `{"unknown": [999999]}` |
| `SYS_429` | `{"retry_after_seconds": 212}` |
| `SYS_TEST` | `{"status_code": 418}` |
| `EVT_001` | `{"event_id": "…"}` |
| `404` de un registro (`USR_001`, `ROL_001`, `SYS_404` de un recurso) y `SYS_RESTORE` | `{"id": "…"}` |

### 3.2 Orden de las comprobaciones

Una petición pasa por estas puertas, y el error que sale es el de la primera que falla:

1. `Origin` no permitido en una escritura (`403 PRM_003`).
2. Idempotencia y tamaño del cuerpo: clave inválida o reutilizada (`IDM_003`, `IDM_002`), cuerpo
   mayor de 1 MiB (`413 SYS_413`) y copia de una solicitud que sigue en proceso (`IDM_001`).
3. Sesión y permiso del endpoint (`401` y `403`).
4. Validación del formato de la petición (`422 VAL_422`).
5. Reglas del recurso: `404`, unicidad `409`, claves foráneas `422 VAL_REL`, reglas de negocio
   (`PRM_004`, `USR_003`, `ROL_003`…).

Por eso un usuario sin permiso recibe `403` aunque su cuerpo o sus parámetros tengan errores. La
única excepción es un JSON mal formado, que se lee antes de comprobar nada y da `422` aunque no
haya sesión.

### 3.3 `X-Request-ID` y cómo encontrar un evento

Todas las respuestas, correctas o no, llevan la cabecera `X-Request-ID`. Es un UUIDv7 que genera
**el servidor** (un `X-Request-ID` enviado por el cliente se ignora). Es el mismo valor que
`error.request_id`, aparece en el log del servidor y queda grabado en **todos los eventos que esa
petición produce**. Para ver qué hizo una petición concreta:

```bash
curl -s -b $JAR -G $API/events/ --data-urlencode "request_id=01a0f5b4-f903-76ac-8759-01b7375ff426"
```

Si el error trae `event_id`, el evento exacto se lee con `GET /api/events/{event_id}`.
`event_id` es `null` cuando ese código no se guarda (ver la tabla siguiente) o cuando se alcanzó
el tope de **30 eventos de error por IP y código cada 60 segundos**, para que nadie llene el
registro a base de peticiones. En una respuesta repetida por idempotencia, `X-Request-ID` es el de
la petición nueva, pero `request_id` y `event_id` del cuerpo son los de la original.

### 3.4 Códigos de error

Salen de `core/errors.py`. La lista viva, con los errores propios de tu proyecto incluidos, la da
`GET /api/system/errors`. La columna *Evento* indica si se guarda en la auditoría.

| HTTP | Código | Cuándo se produce | `toast` | Evento |
|---|---|---|---|---|
| 401 | `AUT_001` | Login con usuario o contraseña incorrectos | sí | sí |
| 401 | `AUT_002` | No llegó cookie de sesión | no | no |
| 401 | `AUT_003` | Token o sesión caducados | sí | no |
| 401 | `AUT_004` | Token no válido, ya rotado, sesión revocada, usuario eliminado o refresco reutilizado | sí | sí |
| 403 | `AUT_006` | Cuenta desactivada | sí | sí |
| 403 | `PRM_001` | Falta el permiso del endpoint | sí | sí |
| 403 | `PRM_002` | Endpoint reservado a usuarios dev | sí | sí |
| 403 | `PRM_003` | Escritura con `Origin` no permitido (CSRF) | sí | sí |
| 403 | `PRM_004` | Conceder o gestionar más permisos de los que se tienen | sí | sí |
| 403 | `USR_004` | Quien no es dev toca la marca `dev` de una cuenta | sí | sí |
| 403 | `USR_005` | Quien no es dev modifica la cuenta de otro dev | sí | sí |
| 404 | `SYS_404` | Ruta inexistente (barra final de más o de menos incluida) o recurso sin error propio | sí | no |
| 404 | `AUT_005` | La sesión indicada no existe o no es tuya | sí | no |
| 404 | `USR_001` | El usuario no existe (o está eliminado, en las acciones que exigen uno vivo) | sí | no |
| 404 | `ROL_001` | El rol no existe (o está eliminado, en las acciones que exigen uno vivo) | sí | no |
| 404 | `EVT_001` | El evento no existe | sí | no |
| 405 | `SYS_405` | Método no permitido en esa ruta | sí | no |
| 409 | `SYS_409` | Valor único repetido, también entre eliminados; `fields` dice cuál. Si lo descubre la base en una carrera entre dos peticiones, llega sin `fields` y se guarda | sí | no |
| 409 | `SYS_REL` | Clave foránea: el registro está en uso por otros | sí | no |
| 409 | `SYS_CONC` | PostgreSQL abortó la transacción por un bloqueo cruzado o de serialización (`40P01`, `40001`): el cliente puede repetir la escritura | sí | no |
| 409 | `USR_003` | Acción sobre la propia cuenta: eliminarse, desactivarse o quitarse `dev` | sí | no |
| 409 | `ROL_003` | Eliminar un rol que aún tiene usuarios | sí | no |
| 409 | `SYS_RESTORE` | Restaurar algo que no está eliminado (sirve para todos los recursos) | sí | no |
| 409 | `IDM_001` | Copia idéntica mientras la original sigue procesándose, tras esperar 15 s | no | no |
| 413 | `SYS_413` | Cuerpo de más de 1 MiB | sí | no |
| 422 | `VAL_422` | Validación; `fields` dice qué campos | sí | no |
| 422 | `VAL_REL` | Una clave foránea apunta a un registro que no existe o está eliminado | sí | no |
| 422 | `ROL_004` | El rol incluye permisos que no existen o que no se pueden asignar | sí | no |
| 422 | `IDM_002` | `Idempotency-Key` ya usada con otro método, ruta, query o cuerpo | sí | no |
| 422 | `IDM_003` | `Idempotency-Key` vacía o de más de 255 caracteres | sí | no |
| 429 | `SYS_429` | Demasiados intentos de login o de cambio de contraseña | sí | sí |
| 500 | `SYS_500` | Excepción no controlada | sí | sí |
| 500 | `SYS_TEST` | Solo `GET /api/system/test-error/{status}` (con el estado que se pida) | según `?toast=` | no |
| 503 | `SYS_503` | La base de datos no está disponible | sí | sí |
| otro | `HTTP_<estado>` | Un error HTTP que genera la propia librería y no está en el catálogo (por ejemplo `400` por un cuerpo ilegible) | sí | solo si es 5xx |

Los números que faltan en la serie (`USR_002`, `ROL_002`) no existen. `SYS_REL` es la traducción
de un fallo de clave foránea de PostgreSQL: las rutas estándar de usuarios y roles comprueban
antes sus relaciones (`ROL_003`, `VAL_REL`), así que casi solo aparece con tablas propias que
declaran `on_delete=RESTRICT`, o si dos peticiones simultáneas se pisan.

### 3.5 Errores de validación (`422 VAL_422`)

`fields` trae un mensaje en español por cada campo que falló. El nombre del campo sigue estas
reglas:

| Dónde falla | Clave en `fields` | Ejemplo |
|---|---|---|
| Un campo del cuerpo | El nombre | `name` |
| Un elemento de una lista del cuerpo | `lista.posición`, desde 0 | `permissions.0` |
| Un campo anidado | La ruta con puntos | `datos.precio` |
| Un parámetro de la URL | El nombre | `size`, `sort`, `created_at_from` |
| Un elemento de un filtro de varios valores | El nombre, **sin posición** | `role_id` (no `role_id.0`) |
| Un parámetro de la ruta | El nombre del parámetro | `item_id`, `event_id`, `session_id` |
| El cuerpo entero (falta, o no es un objeto) | `body` | |
| JSON mal formado | La posición del fallo, como texto | `"1"` |

Si un mismo campo falla por dos motivos, solo llega un mensaje. Los mensajes más habituales:

| Situación | Mensaje |
|---|---|
| Falta un campo obligatorio | `Este campo es obligatorio` |
| Texto demasiado corto o largo | `Mínimo 2 caracteres`, `Máximo 100 caracteres` |
| Lista demasiado corta o larga | `Mínimo 1 elementos`, `Máximo 2000 elementos` |
| Tipo equivocado | `Debe ser un texto`, `Debe ser un número entero`, `Debe ser un número`, `Debe ser un número decimal`, `Debe ser verdadero o falso`, `Debe ser una lista`, `Debe ser un objeto` |
| Límites numéricos | `Debe ser mayor que 0`, `Debe ser mayor o igual que 1`, `Debe ser menor que 10`, `Debe ser menor o igual que 100` |
| No es un UUID | `Identificador no válido` |
| Fechas | `Fecha no válida`, `Fecha y hora no válidas`, `Hora no válida` |
| Fecha sin zona horaria (o con ella, si no debe) | `La fecha necesita zona horaria`, `La fecha no debe llevar zona horaria` |
| Valor fuera de una lista cerrada (un enum) | `Valor no permitido` |
| Decimales | `Máximo 10 dígitos`, `Máximo 2 decimales`, `Máximo 8 dígitos enteros` |
| Formato | `Formato no válido`, `URL no válida`, `JSON no válido`, `Campo no permitido` |
| Campo obligatorio enviado como `null` | `No puede quedar vacío` |
| Valor único ya existente (`SYS_409`) | `Ya existe un registro con este valor` |
| Relación inexistente (`VAL_REL`) | `El registro relacionado no existe` |
| Columna de orden no permitida | `Columnas permitidas (máximo 4): name, created_at, updated_at` |
| Rango al revés | `Debe ser igual o posterior al inicio` |
| Reglas de usuario y contraseña | Ver [2.8](#28-reglas-de-usuario-y-contraseña) |

Cualquier otro mensaje que genere una regla propia llega tal cual, sin el prefijo técnico.

### 3.6 Ejemplos reales

**401** sin sesión (`GET /api/auth/me` sin cookies):

```json
{
  "error": {
    "code": "AUT_002",
    "message": "Necesitas iniciar sesión para continuar.",
    "toast": false,
    "severity": "info",
    "request_id": "01a0f5b4-e3d4-72e1-914b-6f4947fe0711",
    "event_id": null,
    "fields": null,
    "details": {}
  }
}
```

**403 `PRM_001`**: un usuario cuyo rol no incluye `events.list` llama a `GET /api/events/`. Es un
error que se guarda: trae `event_id`.

```json
{
  "error": {
    "code": "PRM_001",
    "message": "No tienes permisos para realizar esta acción.",
    "toast": true,
    "severity": "error",
    "request_id": "01a0f5b4-f172-7671-ad8c-b70bf3f7acc5",
    "event_id": "01a0f5b4-f17f-7166-a79a-859698c147a1",
    "fields": null,
    "details": { "permission": "events.list" }
  }
}
```

**404** (`GET /api/no-existe`); `405` tiene la misma forma con `SYS_405`
(`PUT /api/system/health`):

```json
{
  "error": {
    "code": "SYS_404",
    "message": "El recurso solicitado no existe.",
    "toast": true,
    "severity": "warning",
    "request_id": "01a0f5b4-faa0-7004-8469-8bb2fb986e81",
    "event_id": null,
    "fields": null,
    "details": {}
  }
}
```

**409 `SYS_409`**: crear un rol con un nombre que ya existe. `fields` dice qué campo choca:

```json
{
  "error": {
    "code": "SYS_409",
    "message": "Ya existe un registro con esos datos.",
    "toast": true,
    "severity": "warning",
    "request_id": "01a0f5b4-e82b-728d-8418-eeb0b5dc5ba9",
    "event_id": null,
    "fields": { "name": "Ya existe un registro con este valor" },
    "details": {}
  }
}
```

**422 `VAL_422`**: nombre de rol demasiado corto (`POST /api/roles/` con `{"name": "a"}`), y una
contraseña débil al crear un usuario:

```json
{
  "error": {
    "code": "VAL_422",
    "message": "Los datos enviados no son válidos.",
    "toast": true,
    "severity": "warning",
    "request_id": "01a0f5b4-e808-7314-a773-ef3197a3c507",
    "event_id": null,
    "fields": { "name": "Mínimo 2 caracteres" },
    "details": {}
  }
}
```

```json
{
  "error": {
    "code": "VAL_422",
    "message": "Los datos enviados no son válidos.",
    "toast": true,
    "severity": "warning",
    "request_id": "01a0f5b4-ed04-7388-86e1-952c078252bd",
    "event_id": null,
    "fields": { "password": "Debe tener al menos 8 caracteres" },
    "details": {}
  }
}
```

**422 `VAL_REL`** (**construido a partir del código**): crear o editar un usuario con un `role_id`
que no existe o está eliminado:

```json
{
  "error": {
    "code": "VAL_REL",
    "message": "Uno de los registros relacionados no existe.",
    "toast": true,
    "severity": "warning",
    "request_id": "…",
    "event_id": null,
    "fields": { "role_id": "El registro relacionado no existe" },
    "details": {}
  }
}
```

**422 `ROL_004`**: un rol con un permiso que no existe. `fields.permissions` y `details.unknown` lo
dicen:

```json
{
  "error": {
    "code": "ROL_004",
    "message": "El rol incluye permisos que no existen en el sistema.",
    "toast": true,
    "severity": "warning",
    "request_id": "01a0f5b4-e7e4-71b1-8732-80e782ebf087",
    "event_id": null,
    "fields": { "permissions": "Identificadores no asignables: [999999]" },
    "details": { "unknown": [999999] }
  }
}
```

**429** con `details.retry_after_seconds`: ver [2.7](#27-límite-de-intentos-de-login).

El frontend inventa un código propio, `NET_000`, cuando no hay respuesta del servidor; el backend
nunca lo envía.

---

## 4. Listados (Resource)

Todos los listados de recursos (`GET /api/users/`, `GET /api/roles/`, y los de cualquier módulo
propio que use `Resource`) comparten parámetros, formato y errores.

### 4.1 La respuesta paginada

```json
{ "items": [ … ], "total": 2, "page": 1, "size": 10, "pages": 1 }
```

| Campo | Significado |
|---|---|
| `items` | Las filas de **esta** página, con la forma del recurso |
| `total` | Cuántas filas cumplen los filtros en total (no solo las de la página) |
| `page` | La página pedida |
| `size` | El tamaño de página aplicado |
| `pages` | `ceil(total / size)`. Es `0` si no hay ninguna fila |

Una página fuera de rango no es un error: responde `200` con `items: []`. El historial de un
registro y el listado de eventos usan el mismo formato.

### 4.2 Parámetros comunes

| Parámetro | Tipo | Por defecto | Límites | Qué hace |
|---|---|---|---|---|
| `page` | entero | `1` | `≥ 1` | Número de página |
| `size` | entero | `50` | de `1` a `100` | Filas por página |
| `search` | texto | sin búsqueda | `≤ 100` caracteres | Busca el texto **contenido**, sin distinguir mayúsculas, en las columnas de búsqueda del recurso (basta con que coincida una) |
| `deleted` | booleano | `false` | | `false`: solo los registros vivos. `true`: **solo los eliminados** (para ver ambos, dos llamadas) |
| `sort` | texto | el orden propio del recurso | `≤ 200` caracteres, máximo 4 columnas | Columnas de orden, separadas por comas; `-` delante = descendente |

Además, **cada recurso declara** qué más admite: filtros por igualdad, filtros de texto, rangos y
columnas de orden. No hay ninguno implícito: un parámetro no declarado se **ignora** sin avisar.
Lo que admite cada uno se ve en `/docs` (en el `GET /` del recurso) y en las tablas de la
[sección 8](#8-referencia-de-endpoints) para Usuarios y Roles.

### 4.3 Filtros por igualdad, con varios valores

Se escriben como `?columna=valor`. **Repetir el parámetro** equivale a «uno u otro» (`IN`):

```text
?role_id=A&role_id=B          role_id es A o B
?is_active=true               solo activos
?role_id=A&is_active=true     role_id es A  Y  está activo
```

- Dentro de un mismo filtro, los valores se suman (`OR`); entre filtros distintos, se restringe
  (`AND`); y todo se combina también con `search`, los rangos y `deleted`.
- La coincidencia es **exacta**: en columnas de texto distingue mayúsculas, y cada valor admite
  hasta 100 caracteres.
- Un valor con el tipo equivocado da `422` con el nombre del filtro (sin posición):
  `role_id=abc` → `fields.role_id: "Identificador no válido"`.
- Con estos filtros no se puede pedir «sin rol» (`role_id` nulo): no hay forma de expresarlo.

### 4.4 Filtros de texto: `<columna>_contains`

Si el recurso los declara, `?name_contains=agua` filtra las filas cuya columna *contiene* el texto,
sin distinguir mayúsculas (hasta 100 caracteres). **Ni `users` ni `roles` los declaran**: ahí se
usa `search`.

### 4.5 Rangos: `<columna>_from` y `<columna>_to`

Si el recurso los declara para una columna, admiten los dos extremos, **incluidos**, y cada uno
por separado:

```text
?created_at_from=2026-01-01T00:00:00Z               desde esa fecha, sin tope
?created_at_to=2026-12-31T23:59:59Z                 hasta esa fecha
?created_at_from=2026-01-01T00:00:00Z&created_at_to=2026-12-31T23:59:59Z
```

| Tipo de la columna | Formato |
|---|---|
| Fecha y hora | ISO 8601 **con zona horaria**: `2026-01-01T00:00:00Z` o `2026-01-01T00:00:00%2B02:00` (el `+` se escribe `%2B`). Sin zona, `422 La fecha necesita zona horaria` |
| Fecha (sin hora) | `AAAA-MM-DD` |
| Número, decimal | El número tal cual (`?price_from=2&price_to=4`) |

Si `_from` es posterior a `_to`, `422` con `fields.<columna>_to`: `Debe ser igual o posterior al
inicio`. En `curl`, `-G --data-urlencode "created_at_from=2026-01-01T00:00:00Z"` se encarga de
escribir los `:` y los `+` en la URL.

### 4.6 Orden: `sort`

- Una o varias columnas separadas por comas, de izquierda a derecha por prioridad. `-` delante
  = descendente: `sort=-created_at,username`. Los espacios alrededor y los trozos vacíos se
  ignoran.
- Máximo **4** columnas, y solo las que el recurso declara. Si no, `422` con `fields.sort`:
  `Columnas permitidas (máximo 4): name, created_at, updated_at`.
- **Desempate:** con `sort`, la API añade siempre `id` ascendente al final. Así el orden es
  total y estable: la misma consulta devuelve las filas en el mismo orden y la paginación no
  repite ni se salta filas mientras los datos no cambien.
- **Sin `sort`**: el orden propio del recurso (`ordering`). Por defecto, `-id`: lo más reciente
  primero. `users` ordena por `username` y `roles` por `name`, que son únicos.
- La paginación es por desplazamiento: si entre dos páginas se crean o eliminan filas, puede
  repetirse o saltarse alguna.
- En PostgreSQL los nulos van al final en orden ascendente y al principio en descendente:
  con `sort=-last_login_at`, los usuarios que nunca entraron salen primero.

### 4.7 Ejemplos reales

Roles buscados por texto, los más nuevos primero, creados desde 2026 y de 10 en 10 (captura real
de `GET /api/roles/?search=bb73c&sort=-created_at&created_at_from=2026-01-01T00%3A00%3A00Z&size=10`):

```bash
curl -s -b $JAR -G $API/roles/ \
  --data-urlencode "search=bb73c" \
  --data-urlencode "sort=-created_at" \
  --data-urlencode "created_at_from=2026-01-01T00:00:00Z" \
  --data-urlencode "size=10"
```

```json
{
  "items": [
    {
      "id": "01a0f5b4-e7ba-729b-a290-a6a3feacfe03",
      "name": "Compras bb73c",
      "description": "",
      "permissions": [],
      "users_count": 0,
      "created_at": "2026-10-01T04:24:28.858989Z",
      "updated_at": "2026-10-01T04:24:28.859016Z",
      "deleted_at": null
    },
    {
      "id": "01a0f5b4-e792-773b-ad8f-568ca3c83784",
      "name": "Vendedor bb73c",
      "description": "Ventas",
      "permissions": [3001, 4001],
      "users_count": 0,
      "created_at": "2026-10-01T04:24:28.818754Z",
      "updated_at": "2026-10-01T04:24:28.818780Z",
      "deleted_at": null
    }
  ],
  "total": 2,
  "page": 1,
  "size": 10,
  "pages": 1
}
```

Usuarios de un rol, solo activos, por nombre (`GET /api/users/?role_id=…&is_active=true&sort=username&search=bb73c`);
fíjate en `size: 50`, el valor por defecto:

```bash
curl -s -b $JAR -G $API/users/ \
  --data-urlencode "role_id=01a0f5b4-e792-773b-ad8f-568ca3c83784" \
  --data-urlencode "is_active=true" \
  --data-urlencode "sort=username" \
  --data-urlencode "search=bb73c"
```

```json
{
  "items": [
    {
      "id": "01a0f5b4-eaf5-7052-8359-7266c87f472a",
      "username": "anabb73c",
      "is_active": true,
      "dev": false,
      "role_id": "01a0f5b4-e792-773b-ad8f-568ca3c83784",
      "role_name": "Vendedor bb73c",
      "created_at": "2026-10-01T04:24:29.686860Z",
      "updated_at": "2026-10-01T04:24:29.686887Z",
      "deleted_at": null,
      "last_login_at": null
    }
  ],
  "total": 1,
  "page": 1,
  "size": 50,
  "pages": 1
}
```

Para **varios roles**, se repite el parámetro; aquí, los usuarios de cualquiera de dos roles:

```bash
curl -s -b $JAR -G $API/users/ \
  --data-urlencode "role_id=01a0f5b4-e792-773b-ad8f-568ca3c83784" \
  --data-urlencode "role_id=01a0f5b4-e7ba-729b-a290-a6a3feacfe03"
```

Un rango sobre el último acceso (`last_login_at_from` y `last_login_at_to`; los usuarios que nunca
entraron tienen `last_login_at: null` y no cumplen ningún rango):

```bash
curl -s -b $JAR -G $API/users/ \
  --data-urlencode "last_login_at_from=2026-01-01T00:00:00Z" \
  --data-urlencode "last_login_at_to=2030-01-01T00:00:00Z"
```

```json
{
  "items": [
    {
      "id": "01a0f5b4-6173-7230-bf04-04b1172df60c",
      "username": "dev",
      "is_active": true,
      "dev": true,
      "role_id": null,
      "role_name": null,
      "created_at": "2026-10-01T04:23:54.484809Z",
      "updated_at": "2026-10-01T04:24:28.648103Z",
      "deleted_at": null,
      "last_login_at": "2026-10-01T04:24:28.646031Z"
    }
  ],
  "total": 1,
  "page": 1,
  "size": 50,
  "pages": 1
}
```

Los usuarios eliminados (`deleted=true`; `deleted_at` viene con fecha). Los eliminados no salen
sin ese parámetro:

```bash
curl -s -b $JAR -G $API/users/ --data-urlencode "deleted=true" --data-urlencode "search=bb73c"
```

```json
{
  "items": [
    {
      "id": "01a0f5b4-eaf5-7052-8359-7266c87f472a",
      "username": "anabb73c",
      "is_active": true,
      "dev": false,
      "role_id": "01a0f5b4-e792-773b-ad8f-568ca3c83784",
      "role_name": "Vendedor bb73c",
      "created_at": "2026-10-01T04:24:29.686860Z",
      "updated_at": "2026-10-01T04:24:33.136221Z",
      "deleted_at": "2026-10-01T04:24:33.134047Z",
      "last_login_at": "2026-10-01T04:24:31.324583Z"
    }
  ],
  "total": 1,
  "page": 1,
  "size": 50,
  "pages": 1
}
```

### 4.8 Errores de validación en un listado

| Qué se envía | `fields` |
|---|---|
| `sort` con una columna no permitida (o más de 4) | `sort`: `Columnas permitidas (máximo 4): name, created_at, updated_at` |
| `size` fuera de 1–100 | `size`: `Debe ser menor o igual que 100` o `Debe ser mayor o igual que 1` |
| `page` menor que 1 | `page`: `Debe ser mayor o igual que 1` |
| `page` o `size` que no son números | `Debe ser un número entero` |
| `search` de más de 100 caracteres | `search`: `Máximo 100 caracteres` |
| Fecha sin zona horaria | `created_at_from`: `La fecha necesita zona horaria` |
| Fecha ilegible | `Fecha y hora no válidas` |
| Rango al revés | `created_at_to`: `Debe ser igual o posterior al inicio` |
| Identificador mal escrito en un filtro | `role_id`: `Identificador no válido` |
| Booleano mal escrito | `is_active`: `Debe ser verdadero o falso` |

Captura real de un `sort` no permitido (`GET /api/roles/?sort=permissions`):

```json
{
  "error": {
    "code": "VAL_422",
    "message": "Los datos enviados no son válidos.",
    "toast": true,
    "severity": "warning",
    "request_id": "01a0f5b4-e87b-778a-90f6-7ad4586c6370",
    "event_id": null,
    "fields": { "sort": "Columnas permitidas (máximo 4): name, created_at, updated_at" },
    "details": {}
  }
}
```

---

## 5. Escrituras

### 5.1 Los siete endpoints de un recurso

Todo recurso hecho con `Resource` (usuarios, roles y los módulos propios) expone los mismos
siete endpoints. Sus permisos son `<recurso>.list`, `.read`, `.create`, `.update`, `.delete`,
`.restore` y `.hard_delete`, con ids correlativos (`base+1` a `base+7`).

| Endpoint | Permiso | Éxito | Qué hace |
|---|---|---|---|
| `GET /api/<recurso>/` | `list` | `200` | Listado paginado ([sección 4](#4-listados-resource)) |
| `GET /api/<recurso>/{id}` | `read` | `200` | Detalle. **También devuelve eliminados** (con `deleted_at`) |
| `POST /api/<recurso>/` | `create` | **`201`** | Alta. Devuelve el registro |
| `PATCH /api/<recurso>/{id}` | `update` | `200` | Cambios parciales. Devuelve el registro |
| `DELETE /api/<recurso>/{id}` | `delete` | `200` | Eliminación **reversible**. Devuelve `{"detail": "…"}` |
| `POST /api/<recurso>/{id}/restore` | `restore` | `200` | Restaura un eliminado. Devuelve el registro |
| `DELETE /api/<recurso>/{id}/hard` | `hard_delete` | `200` | Borrado **definitivo**, solo dev. Devuelve `{"detail": "…"}` |

Las acciones que no devuelven un registro responden `{"detail": "texto"}` (llamado `Message` en
`/docs`).

### 5.2 Crear (`POST`)

Responde **`201`** con el registro completo. Los campos que no se envían toman su valor por
defecto. Antes de guardar, la API comprueba por este orden: formato (`422 VAL_422`), campos
obligatorios enviados como `null` (`422`), reglas del recurso, **unicidad** (`409 SYS_409`) y
**claves foráneas** (`422 VAL_REL`).

```bash
curl -s -b $JAR -X POST $API/roles/ \
  -H "Content-Type: application/json" \
  -d '{"name":"Vendedor bb73c","description":"Ventas","permissions":[3001,4001]}'
```

```json
{
  "id": "01a0f5b4-e792-773b-ad8f-568ca3c83784",
  "name": "Vendedor bb73c",
  "description": "Ventas",
  "permissions": [3001, 4001],
  "users_count": 0,
  "created_at": "2026-10-01T04:24:28.818754Z",
  "updated_at": "2026-10-01T04:24:28.818780Z",
  "deleted_at": null
}
```

### 5.3 Editar (`PATCH`)

- **Parcial:** solo cambian los campos que vienen en el cuerpo. Los que faltan no se tocan. Un
  campo que el recurso no conoce se **ignora** sin avisar.
- **`null` significa «poner a nulo»**, no «no tocar». En una columna que admite nulos
  (`role_id` de un usuario) la deja vacía; en una obligatoria (`name`, `username`, `is_active`…)
  da `422` con `fields: {"name": "No puede quedar vacío"}`.
- Un cuerpo `{}` es válido: no cambia nada y no deja evento.
- Si el valor enviado es el mismo que ya había, la API responde `200` y **no deja evento**
  (`updated_at` sí se renueva).
- Solo se editan registros **vivos**: uno eliminado da `404` (restáuralo antes).
- Los campos únicos y las claves foráneas se vuelven a comprobar (`409`, `422 VAL_REL`).

```bash
curl -s -b $JAR -X PATCH $API/roles/01a0f5b4-e792-773b-ad8f-568ca3c83784 \
  -H "Content-Type: application/json" \
  -d '{"description":"Equipo de ventas"}'
```

```json
{
  "id": "01a0f5b4-e792-773b-ad8f-568ca3c83784",
  "name": "Vendedor bb73c",
  "description": "Equipo de ventas",
  "permissions": [3001, 4001],
  "users_count": 0,
  "created_at": "2026-10-01T04:24:28.818754Z",
  "updated_at": "2026-10-01T04:24:29.114793Z",
  "deleted_at": null
}
```

### 5.4 Eliminar, restaurar y borrar definitivamente

- **`DELETE /{id}`** no borra la fila: marca `deleted_at` y `deleted_by_id`. Desde entonces el
  registro desaparece de los listados (sale con `?deleted=true`), de `PATCH` y de `DELETE`
  (`404`), pero `GET /{id}` lo sigue devolviendo con `deleted_at` relleno. Responde
  `{"detail": "<etiqueta> eliminado"}`, donde la etiqueta es el nombre del usuario o del rol (el
  id si el recurso no tiene).

  ```json
  { "detail": "anabb73c eliminado" }
  ```

  Un usuario eliminado pierde todas sus sesiones. Un rol con usuarios vivos no se elimina
  (`409 ROL_003`).
- **`POST /{id}/restore`** devuelve el registro vivo. Si no estaba eliminado, `409 SYS_RESTORE`; si
  alguna de sus claves foráneas apunta ahora a algo eliminado, `422 VAL_REL`.

  ```json
  {
    "error": {
      "code": "SYS_RESTORE",
      "message": "El registro que intentas restaurar no está eliminado.",
      "toast": true,
      "severity": "warning",
      "request_id": "01a0f5b4-f8da-7592-95e6-3ee93659a420",
      "event_id": null,
      "fields": null,
      "details": { "id": "01a0f5b4-eaf5-7052-8359-7266c87f472a" }
    }
  }
  ```
- **`DELETE /{id}/hard`** borra la fila de verdad y **no se puede deshacer**. Es solo para
  usuarios dev (a otros, `403 PRM_002`). Sirve tanto con registros vivos como eliminados, deja un
  evento `hard_delete` con el último estado del registro y responde
  `{"detail": "<etiqueta> borrado definitivamente"}`.

### 5.5 Conflictos de unicidad: `409 SYS_409`

Los campos únicos (el `username` de un usuario, el `name` de un rol) se comprueban **también
contra los registros eliminados**. Un nombre de usuario eliminado sigue ocupado hasta que se
borra definitivamente. `fields` dice qué campo choca. La captura del apartado 3.6 muestra un
rol duplicado; este es un usuario duplicado:

```json
{
  "error": {
    "code": "SYS_409",
    "message": "Ya existe un registro con esos datos.",
    "toast": true,
    "severity": "warning",
    "request_id": "01a0f5b4-eb12-7228-b28b-aea6a30d8586",
    "event_id": null,
    "fields": { "username": "Ya existe un registro con este valor" },
    "details": {}
  }
}
```

### 5.6 Claves foráneas: `422 VAL_REL`

Al crear, editar y restaurar, cada clave foránea (el `role_id` de un usuario) debe apuntar a un
registro **vivo**. Si no existe o está eliminado, `422 VAL_REL` y `fields` nombra el campo
(`{"role_id": "El registro relacionado no existe"}`; el cuerpo completo está en el apartado 3.6).

### 5.7 Atomicidad

Toda escritura (`POST`, `PUT`, `PATCH`, `DELETE`) es **una sola transacción** que incluye los
eventos del historial: o queda todo guardado, o no queda nada. La respuesta de éxito sale después
de confirmar. Si algo falla, incluso en el último paso, se deshace todo.

Las excepciones están pensadas: `POST /auth/login`, `POST /auth/refresh` y
`POST /auth/password` guardan cosas **aunque respondan con error** (el intento de login, el cierre
de la sesión de un token robado) y manejan sus propias transacciones. Los `GET` no abren
transacción.

### 5.8 Límite de cuerpo

Ninguna petición puede llevar más de **1 MiB** (1 048 576 bytes): si pasa, `413 SYS_413`. Se
detecta con la cabecera `Content-Length` y, además, contando los bytes según llegan: no se
esquiva con un cuerpo por trozos. Pon el mismo límite en el proxy inverso.

### 5.9 Solicitudes repetidas e `Idempotency-Key`

Un doble clic o un reintento de red envían la misma escritura dos veces. La API la ejecuta **una
sola vez** y devuelve la misma respuesta a la copia, con la cabecera `Idempotent-Replayed: true`.
Solo afecta a `POST`, `PUT`, `PATCH` y `DELETE` bajo `/api`; en un `GET` se ignora.

| Modo | Cuándo | Qué es «la misma solicitud» | Dura |
|---|---|---|---|
| Automático | Siempre que **no** envíes `Idempotency-Key` | Mismo emisor, método, ruta, query y cuerpo, **seguidas**: otra escritura distinta del mismo emisor corta la racha | 10 s desde que termina la primera |
| Con clave | Envías `Idempotency-Key: <texto>` | La misma clave del mismo emisor. Con otro método, ruta, query o cuerpo, `422 IDM_002` | 24 horas |

- **La clave** es un texto de **1 a 255 caracteres** que identifica una intención del usuario
  («guardar este formulario»), no una petición. Vacía o de más de 255, `422 IDM_003`. Una clave
  buena es un UUID o 16 bytes aleatorios en hexadecimal. Quien envía clave **pierde el modo
  automático**: la clave pasa a ser su única protección.
- **El emisor** es la sesión (su id, leído del token de acceso; no cambia aunque el token rote)
  mientras siga abierta; con una sesión cerrada, sin sesión o con el acceso caducado, es la IP.
  La misma clave desde otra sesión no tiene relación con la primera.
- **Qué se guarda y qué no.** Se guardan las respuestas correctas **y las `4xx`** (una clave
  repetida devuelve el mismo error durante 24 h, aunque el problema ya esté resuelto). **No** se
  guardan los `5xx`, las respuestas que ponen cookies (login correcto, renovación, logout) ni las
  de más de 8 MiB.
- **La copia recibe** el mismo estado, cuerpo y cabeceras que la original (salvo `Set-Cookie`,
  `Content-Length` y las de conexión), más `Idempotent-Replayed: true`. `X-Request-ID` es el de la
  petición nueva; `request_id` y `event_id` dentro de un error repetido son los de la original.
- **Si la original sigue en proceso**, la copia espera hasta **15 s** su resultado; pasado ese
  tiempo, `409 IDM_001` (`toast: false`). La reserva de una escritura lenta se renueva sola cada
  20 s, así que no la toma una copia por error.
- Las reservas viven en la tabla `fastapi_idempotency_requests`: funcionan con varios procesos.

| Código | HTTP | Significa | Qué hacer |
|---|---|---|---|
| `IDM_001` | 409 | La copia idéntica llegó y la original aún no terminó (tras 15 s de espera) | Repetir con **la misma** clave más tarde |
| `IDM_002` | 422 | Esa clave ya se usó con otro método, ruta, query o cuerpo | Una clave nueva para la nueva intención |
| `IDM_003` | 422 | La cabecera está vacía o pasa de 255 caracteres | Una clave de 1 a 255 caracteres |

Cuándo mantener la clave y cuándo cambiarla al reintentar:

| Qué pasó | Clave del siguiente intento |
|---|---|
| No hubo respuesta (fallo de red) o un `5xx` | **La misma**: si llegó, devuelve la respuesta guardada; si no, se ejecuta por primera vez |
| `409 IDM_001` | **La misma**, tras esperar |
| Éxito | Nueva para la siguiente acción |
| Cualquier otro `4xx` (422, 409, 403, 404, 429…) | **Nueva**: el servidor recuerda ese error 24 h con esa clave |
| El usuario cambia los datos | Nueva |

Captura real: crear un rol con clave, y repetir la petición idéntica.

```bash
curl -i -b $JAR -X POST $API/roles/ \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: clave-bb73c" \
  -d '{"name":"Compras bb73c","permissions":[]}'
```

La primera vez, `201` y estas cabeceras:

```text
content-type: application/json
x-request-id: 01a0f5b4-e7a8-7513-999c-0d9f09a05b6b
cache-control: no-store
```

La segunda, el mismo `201` y el mismo cuerpo, sin crear nada, con `idempotent-replayed` y un
`x-request-id` nuevo:

```text
content-type: application/json
idempotent-replayed: true
x-request-id: 01a0f5b4-e7d2-712b-8ef3-27e9852aaa48
cache-control: no-store
```

```json
{
  "id": "01a0f5b4-e7ba-729b-a290-a6a3feacfe03",
  "name": "Compras bb73c",
  "description": "",
  "permissions": [],
  "users_count": 0,
  "created_at": "2026-10-01T04:24:28.858989Z",
  "updated_at": "2026-10-01T04:24:28.859016Z",
  "deleted_at": null
}
```

Consecuencias al **probar a mano o desde un script**: dos peticiones idénticas y seguidas desde la
misma sesión dan la misma respuesta; para repetir una con los mismos datos, espera 10 s o cambia
algo. Lo mismo vale para un login fallido con la misma contraseña: el segundo intento idéntico
recibe la respuesta guardada del primero y no suma al límite de intentos. Cómo generar la clave
desde el frontend, cuándo mantenerla y cuándo cambiarla está en
[`frontend/src/core/idempotency.md`](../frontend/src/core/idempotency.md).

### 5.10 El rastro de auditoría de toda escritura

Cada escritura sobre un recurso deja su evento en la cadena de auditoría, **dentro de la misma
transacción** que el cambio:

| Escritura | Evento (`category` / `action`) | Contenido |
|---|---|---|
| Crear | `domain` / `create` | `snapshot` con el estado completo; `changes` es `null` |
| Editar | `domain` / `update` | `changes` con `{campo: {"before": …, "after": …}}`; `snapshot` con el estado resultante |
| Eliminar | `domain` / `delete` | `changes` con `deleted_at` y `deleted_by_id` |
| Restaurar | `domain` / `restore` | `changes` con `deleted_at` y `deleted_by_id` |
| Borrar definitivamente | `domain` / `hard_delete` (gravedad `warning`) | `snapshot` con el último estado de la fila |

Cada evento lleva quién lo hizo (`actor_*`), sobre qué (`entity_type`, `entity_id`,
`entity_label`), por qué endpoint (`permission_id`, `method`, `path`), desde dónde (`ip`,
`user_agent`) y el `request_id` de la petición. Las contraseñas **nunca** se guardan: en
`changes` y `snapshot` aparecen como una huella (`hmac:1a33fbce0d90c84a`). El último acceso
de un usuario (`last_login_at`) no se registra como cambio. Una edición que no cambia nada no
deja evento.

Los eventos de seguridad (login, logout, sesiones cerradas, cambios de contraseña, accesos
denegados) los escriben las rutas de sesión, y los errores que se guardan, el manejador de
errores; ver la [sección 7](#7-auditoría).

---

## 6. Permisos

### 6.1 El modelo

Un **permiso** es un número estable con nombre, que identifica a un endpoint y a la vez es la
llave que lo abre. Cada endpoint de `/api` declara **exactamente uno**, y dos endpoints no pueden
compartirlo: si no, el servidor no arranca.

| Campo | Qué es |
|---|---|
| `id` | Entero estable (`3001`) |
| `key` | Clave legible, `<recurso>.<acción>` (`users.list`) |
| `group` | Agrupación para pantallas (`Usuarios`) |
| `description` | Texto en español (`Listar usuarios`); es el resumen del endpoint en `/docs` |
| `scope` | Quién puede entrar (tabla siguiente) |

| `scope` | Quién entra | ¿Se puede dar a un rol? |
|---|---|---|
| `public` | Cualquiera, sin sesión | No |
| `authenticated` | Cualquier usuario con sesión, tenga rol o no | No |
| `role` | Quien tenga el id en su rol, y los dev | **Sí** |
| `dev` | Solo usuarios dev | No |

- **Un rol es una lista de ids** (`permissions`, una lista de enteros, máximo 2000). Solo
  pueden ir ids de alcance `role`; otros dan `422 ROL_004`. Se guardan ordenados y sin repetidos.
- **Un usuario tiene un solo rol** (`role_id`, que puede ser `null`). Sin rol, solo entra a los
  endpoints `public` y `authenticated`.
- **`dev: true` es el superusuario:** pasa todas las comprobaciones, incluidos los endpoints
  `dev`, y puede conceder cualquier permiso asignable.
- **Los ids** `1000`–`5999` son del sistema; los de tus módulos empiezan en `6000`. Cada recurso
  CRUD ocupa un bloque de 100: `base+1` a `base+7` son sus siete permisos y `base+11` a `base+99`
  sus endpoints propios.
- **Un permiso nuevo no lo tiene ningún rol** hasta que alguien lo marca.
- `GET /api/auth/me` devuelve `permissions` (ids) y `permission_keys` con los permisos de alcance
  `role` que el usuario tiene (todos, si es dev). Los `public`, `authenticated` y `dev` nunca
  aparecen en esa lista; `dev: true` es la marca del superusuario.

### 6.2 Cómo se decide si pasas

1. ¿Eres dev? Pasas.
2. El endpoint es `public` o `authenticated`: pasas (el segundo exige haber iniciado sesión).
3. El endpoint es `dev`: no pasas.
4. El endpoint es `role`: pasas si su id está en la lista de permisos de tu rol.

### 6.3 `401` frente a `403`

| Código | HTTP | Significa |
|---|---|---|
| `AUT_002`, `AUT_003`, `AUT_004` | 401 | No sabemos quién eres: sin sesión, caducada o inválida. Renueva o inicia sesión |
| `AUT_006` | 403 | Sabemos quién eres, pero la cuenta está desactivada |
| `PRM_001` | 403 | Tu rol no incluye el permiso. `details.permission` dice cuál |
| `PRM_002` | 403 | El endpoint es solo para dev |
| `PRM_003` | 403 | Escritura desde un origen no permitido (CSRF) |
| `PRM_004` | 403 | Intentas conceder o gestionar más permisos de los que tienes |
| `USR_004`, `USR_005` | 403 | Reglas de cuentas dev (ver 6.4) |

Los `403` se guardan como evento de seguridad. Cambiar el rol de un usuario o los permisos de un
rol surte efecto en la **siguiente petición**: el permiso se lee de la base cada vez.

### 6.4 Quién puede conceder qué

Quien **no es dev** solo puede conceder o gestionar permisos que **él mismo tiene**. Cuando no se
cumple, `403 PRM_004` y `details.permissions` trae los ids que le sobran. Además, solo un dev
toca a otro dev.

| Operación | Regla | Error |
|---|---|---|
| Crear un rol | Todos los ids de `permissions` están en el rol de quien lo crea | `PRM_004` |
| Editar un rol | El rol **tal como está** cabe en los permisos de quien edita, y también los `permissions` nuevos si los envía | `PRM_004` |
| Eliminar o restaurar un rol | Los permisos del rol caben en los de quien actúa | `PRM_004` |
| Crear un usuario con `role_id` | Los permisos de ese rol caben en los de quien lo crea | `PRM_004` |
| Cambiar el `role_id` de un usuario | Igual: el rol nuevo cabe en los de quien edita | `PRM_004` |
| Crear con `dev: true`, o enviar `dev` (true **o** false) al editar | Solo un dev | `403 USR_004` |
| Editar, eliminar, restaurar, restablecer la contraseña o cerrar las sesiones de un usuario que es dev | Solo un dev | `403 USR_005` |
| Hacer lo mismo con un usuario que tiene **más permisos** que quien actúa | Prohibido | `PRM_004` |
| Eliminarse a sí mismo, desactivarse o quitarse la marca `dev` | Nadie lo puede hacer | `409 USR_003` |

Así, un rol con permisos de gestión de usuarios no puede hacerse con una cuenta de acceso total ni
subirse los privilegios. Las lecturas (listar usuarios, ver las sesiones de otro) no pasan por
estas comprobaciones.

### 6.5 El catálogo: `GET /api/system/permissions`

Lista **todos** los permisos del sistema, ordenados por id, con un indicador de si quien pregunta
puede usar cada uno. Es de alcance `authenticated`: cualquier usuario con sesión lo ve. Sirve para
pintar la pantalla de roles y la de permisos de depuración.

| Campo | Significado |
|---|---|
| `id`, `key`, `group`, `description`, `scope` | Los del modelo |
| `assignable` | `true` si se puede marcar en un rol (solo alcance `role`) |
| `endpoint` | El endpoint que lo usa, en la forma `GET /api/system/health` (`null` si ninguno) |
| `granted` | Si **quien pregunta** puede usarlo ahora (un dev, todos) |

```bash
curl -s -b $JAR $API/system/permissions
```

```json
[
  {
    "id": 1001,
    "key": "system.health",
    "group": "Sistema",
    "description": "Consultar el estado del servidor",
    "scope": "public",
    "assignable": false,
    "endpoint": "GET /api/system/health",
    "granted": true
  },
  {
    "id": 1002,
    "key": "system.info",
    "group": "Sistema",
    "description": "Ver información básica de la API",
    "scope": "authenticated",
    "assignable": false,
    "endpoint": "GET /api/system/info",
    "granted": true
  },
  "…"
]
```

---

## 7. Auditoría

Todo lo que cambia datos, abre o cierra sesiones, es rechazado por seguridad o falla de forma
grave queda en el **registro de eventos**: una cadena numerada y firmada que **solo se añade**
(la base de datos rechaza `UPDATE`, `DELETE` y `TRUNCATE` sobre ella). Se consulta con cinco
endpoints del grupo `/api/events`.

### 7.1 Qué contiene un evento

| Campo | Tipo | Significado |
|---|---|---|
| `id` | uuid | UUIDv7 del evento; lleva la fecha dentro |
| `sequence` | entero | Número correlativo y **sin huecos** de la cadena (1, 2, 3…) |
| `created_at` | fecha | Calculada a partir del id, con precisión de milisegundos |
| `category` | enum | `domain`, `security`, `error` o `system` |
| `action` | enum | `create`, `update`, `delete`, `restore`, `hard_delete`, `login`, `logout`, `session_revoked`, `password_change`, `access_denied`, `error` o `system` |
| `severity` | texto | `info`, `warning`, `error` o `critical` |
| `message` | texto | Frase legible: `dev creó 'ana84a14' en users` |
| `actor_id`, `actor_username` | uuid, texto | Quién lo hizo. `null` si fue el sistema o no había sesión |
| `actor_role_id` | uuid | El rol que el actor **tenía en ese momento** |
| `entity_type` | texto | La **tabla** del registro afectado: `users`, `roles`, `user_sessions`… |
| `entity_id` | texto | El id del registro afectado (texto, hasta 50 caracteres) |
| `entity_label` | texto | Nombre legible (el `username`, el `name`) |
| `changes` | objeto | En ediciones, eliminaciones y restauraciones: `{campo: {"before": …, "after": …}}`. En altas y borrados definitivos, `null` |
| `error_code`, `status_code` | texto, entero | Solo en eventos de error: el código y el estado HTTP |
| `permission_id` | entero | El permiso del endpoint donde ocurrió |
| `method`, `path`, `request_id`, `ip` | texto | La petición que lo causó. Lo escrito por un script (`create_admin`) lleva `request_id: "-"` e `ip: "script"` |

El **detalle** (`GET /events/{id}` y el historial) añade:

| Campo | Significado |
|---|---|
| `snapshot` | El estado completo del registro tras el cambio (en el borrado definitivo, el que tenía). Los secretos como huella |
| `context` | Datos extra: en un error guardado, `details`, `fields` y, si fue inesperado, la excepción |
| `user_agent` | Del cliente |
| `prev_hash`, `hash` | Firma del evento anterior y de este (así se encadenan) |
| `is_intact` | `true` si la firma del evento coincide con su contenido |

| Categoría | Acciones | Quién la escribe |
|---|---|---|
| `domain` | `create`, `update`, `delete`, `restore`, `hard_delete` | Cada guardado de un recurso (usuarios, roles y los tuyos) |
| `security` | `login`, `logout`, `session_revoked`, `password_change`, `access_denied` | Las rutas de sesión y contraseñas, y los errores `401`/`403` que se guardan |
| `error` | `error` | Los demás errores que se guardan: `429`, `5xx` y los `409` que descubre la base de datos |
| `system` | `system` | Scripts y arranque (`create_admin`, reinstalar los triggers) |

### 7.2 Listar eventos: `GET /api/events/`

Necesita `events.list`. Devuelve una página de eventos **sin** `snapshot`, `context`, ni firmas.
Todos los filtros son opcionales y se combinan con «y»:

| Parámetro | Tipo | Límite | Cómo filtra |
|---|---|---|---|
| `category` | enum | | Exacto: `domain`, `security`, `error`, `system` |
| `action` | enum | | Exacto (las doce acciones) |
| `severity` | texto | ≤ 10 | Exacto: `info`, `warning`, `error`, `critical` |
| `actor_id` | uuid | | Exacto |
| `actor_username` | texto | ≤ 50 | **Contiene**, sin distinguir mayúsculas |
| `role_id` | uuid | | Rol que el actor tenía **cuando ocurrió** el evento |
| `current_role_id` | uuid | | Rol que el actor tiene **ahora** (incluye usuarios eliminados) |
| `entity_type` | texto | ≤ 50 | Exacto; es el nombre de la **tabla**: `users`, `roles` |
| `entity_id` | texto | ≤ 50 | Exacto |
| `error_code` | texto | ≤ 20 | Exacto (`PRM_001`) |
| `request_id` | texto | ≤ 36 | Exacto: todo lo que produjo una petición |
| `permission_id` | entero | | Exacto: los eventos nacidos en el endpoint de ese permiso |
| `method` | texto | ≤ 10 | Exacto; se pasa a mayúsculas |
| `path` | texto | ≤ 255 | **Contiene** |
| `ip` | texto | ≤ 45 | **Contiene** |
| `search` | texto | ≤ 255 | **Contiene**, en el `message` |
| `date_from`, `date_to` | fecha con zona | | Desde y hasta, extremos incluidos (a la milésima). Sin zona horaria, `422` |
| `only_changes` | booleano | | `true`: solo eventos con `changes` (ediciones, eliminaciones, restauraciones) |
| `order` | `recent` u `oldest` | `recent` | `recent`: los más nuevos primero. `oldest`: los más antiguos primero |
| `page`, `size` | enteros | `1` y `50` (máx. 100) | Como en la [sección 4](#4-listados-resource) |

No existe `sort`: el orden es siempre por id (que es por fecha), con `order`. Un valor fuera de
los enums (`category=foo`) da `422` con `Valor no permitido`. Captura real
(`GET /api/events/?category=domain&entity_type=users&order=oldest&size=3`, recortada a dos
elementos; el segundo muestra un evento nacido de una petición):

```bash
curl -s -b $JAR -G $API/events/ \
  --data-urlencode "category=domain" \
  --data-urlencode "entity_type=users" \
  --data-urlencode "order=oldest" \
  --data-urlencode "size=3"
```

```json
{
  "items": [
    {
      "id": "01a0f5b4-619c-7109-b4cb-931353142f6d",
      "sequence": 1,
      "created_at": "2026-10-01T04:23:54.524000Z",
      "category": "domain",
      "action": "create",
      "severity": "info",
      "message": "El sistema creó 'dev' en users",
      "actor_id": null,
      "actor_username": null,
      "actor_role_id": null,
      "entity_type": "users",
      "entity_id": "01a0f5b4-6173-7230-bf04-04b1172df60c",
      "entity_label": "dev",
      "changes": null,
      "error_code": null,
      "status_code": null,
      "permission_id": null,
      "method": null,
      "path": null,
      "request_id": "-",
      "ip": "script"
    },
    {
      "id": "01a0f5b4-89f7-75df-8a22-086c9042f013",
      "sequence": 8,
      "created_at": "2026-10-01T04:24:04.855000Z",
      "category": "domain",
      "action": "create",
      "severity": "info",
      "message": "dev creó 'ana84a14' en users",
      "actor_id": "01a0f5b4-6173-7230-bf04-04b1172df60c",
      "actor_username": "dev",
      "actor_role_id": null,
      "entity_type": "users",
      "entity_id": "01a0f5b4-89f3-7094-861f-75115f44ba22",
      "entity_label": "ana84a14",
      "changes": null,
      "error_code": null,
      "status_code": null,
      "permission_id": 3003,
      "method": "POST",
      "path": "/api/users/",
      "request_id": "01a0f5b4-8826-73c2-a6c6-663303ac9422",
      "ip": "127.0.0.1"
    },
    "…"
  ],
  "total": 13,
  "page": 1,
  "size": 3,
  "pages": 5
}
```

### 7.3 Detalle de un evento: `GET /api/events/{event_id}`

Necesita `events.read`. Devuelve el evento completo, con `snapshot`, `context`, `user_agent`,
firmas e `is_intact`. Un id que no existe da `404 EVT_001`. Captura real de un borrado
definitivo (el `password` del `snapshot` es una huella, nunca la contraseña):

```json
{
  "id": "01a0f5b4-f919-74ae-ade9-581d3ee08887",
  "sequence": 42,
  "created_at": "2026-10-01T04:24:33.305000Z",
  "category": "domain",
  "action": "hard_delete",
  "severity": "warning",
  "message": "dev borró definitivamente 'anabb73c' en users",
  "actor_id": "01a0f5b4-6173-7230-bf04-04b1172df60c",
  "actor_username": "dev",
  "actor_role_id": null,
  "entity_type": "users",
  "entity_id": "01a0f5b4-eaf5-7052-8359-7266c87f472a",
  "entity_label": "anabb73c",
  "changes": null,
  "error_code": null,
  "status_code": null,
  "permission_id": 3007,
  "method": "DELETE",
  "path": "/api/users/01a0f5b4-eaf5-7052-8359-7266c87f472a/hard",
  "request_id": "01a0f5b4-f903-76ac-8759-01b7375ff426",
  "ip": "127.0.0.1",
  "snapshot": {
    "id": "01a0f5b4-eaf5-7052-8359-7266c87f472a",
    "dev": false,
    "role_id": "01a0f5b4-e792-773b-ad8f-568ca3c83784",
    "password": "hmac:1a33fbce0d90c84a",
    "username": "anabb73c",
    "is_active": true,
    "created_at": "2026-10-01T04:24:29.686860+00:00",
    "deleted_at": null,
    "created_by_id": "01a0f5b4-6173-7230-bf04-04b1172df60c",
    "deleted_by_id": null
  },
  "context": null,
  "user_agent": "python-httpx/0.28.1",
  "prev_hash": "2b13f2cc4e87515451e733b261be586c48c3c8ca543801f58daa5afa081426e8",
  "hash": "3bc29300aac41a573253e7235905a2a363e9a48808f6e53ad46099fc2fcad30d",
  "is_intact": true
}
```

### 7.4 Historial de un registro: `GET /api/events/history/{entity_type}/{entity_id}`

Necesita `events.history`. Devuelve **todos los eventos de un registro**, los **más antiguos
primero**, paginados y con el formato del detalle (con `changes`, `snapshot` y firmas). Sirve para
saber quién cambió qué, y cuándo, en un usuario, un rol o cualquier registro de tu proyecto.

- `entity_type` es el **nombre de la tabla** (`users`, `roles`), no el de la clase (`Role`). Ambos
  parámetros admiten hasta 50 caracteres.
- Un `entity_type` o un `entity_id` que no existen **no son un error**: devuelven una página vacía.

```bash
curl -s -b $JAR "$API/events/history/roles/01a0f5b4-e792-773b-ad8f-568ca3c83784?size=100"
```

Cada elemento tiene la forma del detalle de la sección 7.3. Este es el elemento de una edición
(**construido a partir del código y de la captura de `PATCH` del apartado 5.3**, con `…` donde el
contenido es el mismo que en 7.3):

```json
{
  "id": "…",
  "sequence": 12,
  "created_at": "…",
  "category": "domain",
  "action": "update",
  "severity": "info",
  "message": "dev modificó 'Vendedor bb73c' en roles",
  "actor_username": "dev",
  "entity_type": "roles",
  "entity_id": "01a0f5b4-e792-773b-ad8f-568ca3c83784",
  "entity_label": "Vendedor bb73c",
  "changes": { "description": { "before": "Ventas", "after": "Equipo de ventas" } },
  "permission_id": 4004,
  "method": "PATCH",
  "path": "/api/roles/01a0f5b4-e792-773b-ad8f-568ca3c83784",
  "snapshot": { "…": "estado completo del rol tras el cambio" },
  "prev_hash": "…",
  "hash": "…",
  "is_intact": true
}
```

Y esta es la trampa más común, capturada de verdad: con `Role` (la clase) en lugar de `roles` (la
tabla) la respuesta es una página vacía, no un `404`:

```bash
curl -s -b $JAR "$API/events/history/Role/01a0f5b4-e792-773b-ad8f-568ca3c83784?size=3"
```

```json
{ "items": [], "total": 0, "page": 1, "size": 3, "pages": 0 }
```

### 7.5 Estadísticas: `GET /api/events/stats`

Necesita `events.stats`. Totales de todo el registro por categoría, acción y gravedad:

```json
{
  "total": 42,
  "by_category": { "system": 1, "security": 21, "domain": 20 },
  "by_action": {
    "login": 4, "restore": 2, "password_change": 4, "access_denied": 9, "system": 1,
    "logout": 1, "delete": 3, "session_revoked": 3, "update": 6, "create": 7, "hard_delete": 2
  },
  "by_severity": { "warning": 14, "info": 25, "error": 3 },
  "last_event_at": "2026-10-01T04:24:33.305000Z"
}
```

Solo salen las claves que tienen eventos. `last_event_at` es `null` si el registro está vacío.

### 7.6 Verificar la integridad: `GET /api/events/verify`

Necesita `events.verify`. Comprueba que nadie ha editado, borrado ni insertado eventos a escondidas.
Tiene tres modos:

| Parámetros | Qué comprueba |
|---|---|
| Ninguno | **Toda la cadena**: la firma de cada evento, que los números no tengan huecos, que cada evento enlace con el anterior y la cabeza de la cadena (número y firma del último evento) |
| `date_from` y/o `date_to` (con zona horaria) | **Un periodo**: la firma de cada evento del periodo, que no falten números entre ellos y que el primero enlace con el evento anterior (que queda fuera: su firma no se comprueba). Si el periodo llega al último evento, también la cabeza |
| `event_id` | **Un evento**: su firma y su enlace con el anterior (y la cabeza si es el último) |

`event_id` no se combina con fechas. Respuesta:

| Campo | Significado |
|---|---|
| `total` | Cuántos eventos abarca lo que se verificó |
| `checked` | Cuántos comprobó (se detiene en el primer problema) |
| `intact` | `true` si todo es correcto |
| `first_broken_id` | El primer evento que falla; `null` si todo es correcto |
| `detail` | Frase en español con el resultado |
| `append_only` | `true` si la base de datos tiene activos los dos triggers que rechazan `UPDATE`, `DELETE` y `TRUNCATE` sobre `events`. No dice si alguien los vació por dentro |

Toda la cadena (`GET /api/events/verify`):

```json
{
  "total": 42,
  "checked": 42,
  "intact": true,
  "first_broken_id": null,
  "detail": "La cadena de eventos está intacta. Eventos comprobados: 42.",
  "append_only": true
}
```

Un evento (`GET /api/events/verify?event_id=01a0f5b4-f919-74ae-ade9-581d3ee08887`):

```json
{
  "total": 1,
  "checked": 1,
  "intact": true,
  "first_broken_id": null,
  "detail": "Firmas y enlaces correctos. Eventos comprobados: 1.",
  "append_only": true
}
```

Un periodo (`?date_from=2026-01-01T00:00:00Z&date_to=2030-01-01T00:00:00Z`):

```json
{
  "total": 42,
  "checked": 42,
  "intact": true,
  "first_broken_id": null,
  "detail": "Firmas y enlaces correctos. Eventos comprobados: 42.",
  "append_only": true
}
```

Errores propios:

| Situación | Respuesta |
|---|---|
| `event_id` junto con fechas | `422`, `fields.event_id`: `No se combina con un periodo` |
| `date_from` posterior a `date_to` | `422`, `fields.date_to`: `Debe ser posterior a date_from` |
| `event_id` que no existe | `404 EVT_001` |
| Fecha sin zona horaria | `422`, `La fecha necesita zona horaria` |

Captura real del primer caso (`?event_id=…&date_from=2026-01-01T00:00:00Z`):

```json
{
  "error": {
    "code": "VAL_422",
    "message": "Los datos enviados no son válidos.",
    "toast": true,
    "severity": "warning",
    "request_id": "01a0f5b4-fa13-7557-afc9-f8463cf06024",
    "event_id": null,
    "fields": { "event_id": "No se combina con un periodo" },
    "details": {}
  }
}
```

Cuando algo falla, `intact` es `false`, `first_broken_id` señala el evento y `detail` explica el
motivo con una de estas frases:

| `detail` | Qué pasó |
|---|---|
| `El evento <id> no coincide con su firma.` | Se editó un campo del evento |
| `La cadena se rompe antes del evento <id>: falta algún registro.` | Falta un evento del medio, o un número no es correlativo |
| `La cabeza de la cadena (N) no coincide con el último evento guardado (M): faltan eventos al final o la cabeza fue alterada.` | Faltan los últimos eventos |
| `Falta la cabeza de la cadena de eventos.` | Se borró la fila de la cabeza |
| `No hay eventos que comprobar.` | Un periodo sin eventos (es correcto) |

Cómo funciona por dentro, lo que conviene saber:

- La comprobación se hace sobre una **instantánea de la base** (solo lectura): las escrituras que
  entren mientras corre no producen falsos avisos.
- Recorre los eventos de uno en uno (en bloques de 1000). Verificar **toda** una cadena de
  millones de eventos tarda minutos: para el día a día, usa periodos.
- Un periodo que no incluye un evento alterado no lo ve; solo la cadena entera o un periodo que lo
  rodea lo detectan. El límite de lo que detecta (quien controle la base como dueño o superusuario
  y reajuste la cabeza a la vez) está explicado en `GUIA.md`, «Integridad del registro de eventos».

---

## 8. Referencia de endpoints

Son 35 endpoints. De cada uno: su permiso (`clave` · id), quién entra, qué hace, parámetros,
cuerpo, respuesta y errores **propios**. Hay errores que pueden salir de casi cualquier endpoint y
no se repiten en cada uno:

| Situación | Aplica a | Respuesta |
|---|---|---|
| Sin sesión, caducada o inválida | Todo endpoint salvo los públicos | `401` `AUT_002`, `AUT_003` o `AUT_004` |
| Cuenta desactivada | Ídem | `403 AUT_006` |
| Falta el permiso | Endpoints de alcance `role` / `dev` | `403 PRM_001` / `403 PRM_002` |
| Escritura desde un origen no permitido | Toda escritura | `403 PRM_003` |
| Cuerpo de más de 1 MiB o clave de idempotencia mala | Toda escritura | `413 SYS_413`, `422 IDM_002`, `422 IDM_003`, `409 IDM_001` |
| El id de la ruta no es un UUID | Endpoints con id en la ruta | `422`, `fields.<parámetro>`: `Identificador no válido` |
| Cuerpo o parámetros mal formados | Endpoints con cuerpo o parámetros | `422 VAL_422` con `fields` |

En las tablas, *Acceso* es `público`, `con sesión` (alcance `authenticated`), `rol` (hace falta el
permiso en el rol; los dev entran siempre) o `dev`.

### 8.1 Sesión: `/api/auth`

| Endpoint | Permiso | Acceso | Qué hace |
|---|---|---|---|
| `POST /api/auth/login` | `auth.login` · 2001 | público | Abre sesión y deja las cookies |
| `POST /api/auth/refresh` | `auth.refresh` · 2002 | público | Renueva los tokens |
| `POST /api/auth/logout` | `auth.logout` · 2003 | con sesión | Cierra la sesión actual |
| `GET /api/auth/me` | `auth.me` · 2004 | con sesión | Perfil y permisos del usuario |
| `GET /api/auth/sessions` | `auth.sessions.list` · 2005 | con sesión | Mis sesiones abiertas |
| `POST /api/auth/sessions/revoke-others` | `auth.sessions.revoke_others` · 2007 | con sesión | Cierra mis demás sesiones |
| `DELETE /api/auth/sessions/{session_id}` | `auth.sessions.revoke` · 2006 | con sesión | Cierra una sesión mía |
| `POST /api/auth/password` | `auth.password.change` · 2008 | con sesión | Cambia mi contraseña |

`login` y `refresh` son públicos porque sirven para tener sesión; autentican con las credenciales y
con la cookie de refresco, respectivamente.

**Perfil (`MeOut`)**, que devuelven `login` y `me`:

| Campo | Tipo | Significado |
|---|---|---|
| `id`, `username` | uuid, texto | El usuario |
| `is_active`, `dev` | booleano | Cuenta activa; superusuario |
| `role_id`, `role_name` | uuid y texto, o `null` | Su rol |
| `permissions` | lista de enteros | Ids de los permisos de alcance `role` que tiene (todos, si es dev) |
| `permission_keys` | lista de textos | Las mismas claves legibles (`users.list`) |
| `last_login_at` | fecha o `null` | Último inicio de sesión |

**Sesión (`SessionOut`)**, que devuelven `sessions`:

| Campo | Significado |
|---|---|
| `id` | Id de la sesión |
| `device` | Navegador y versión · sistema · tipo (`Escritorio`, `Móvil` o `Tablet`), sacado del user-agent; `Desconocido` si no hay. Un cliente que no se reconoce, como el `python-httpx` de las capturas, sale como `Other  · Other · Escritorio` |
| `ip_address` | IP desde la que se abrió |
| `created_at`, `last_activity`, `expires_at` | Cuándo se abrió, última actividad (se anota como mucho cada 60 s) y cuándo caduca el refresco |
| `is_current` | `true` en la sesión de la cookie que hace la petición |

#### `POST /api/auth/login`

- **Cuerpo:** `username` (texto, obligatorio, ≤ 50; se normaliza a minúsculas sin espacios en los
  extremos) y `password` (texto, obligatorio, ≤ 128).
- **Respuesta `200`:** el perfil (`MeOut`) y **dos `Set-Cookie`**. Registra el inicio de sesión
  como evento y anota la fecha en `last_login_at`.
- **Errores:** `401 AUT_001` (usuario inexistente o contraseña incorrecta), `403 AUT_006` (cuenta
  desactivada, y la contraseña era correcta), `429 SYS_429` ([2.7](#27-límite-de-intentos-de-login)),
  `422 VAL_422` (falta un campo o pasa del máximo).

#### `POST /api/auth/refresh`

- **Sin cuerpo.** Usa la cookie de refresco.
- **Respuesta `200`:** `{"detail": "Sesión renovada"}` y **dos `Set-Cookie` nuevos**.
- **Errores:** `401` `AUT_002` (sin cookie de refresco), `AUT_003` (caducado), `AUT_004` (no
  válido, sesión cerrada o refresco **reutilizado**, que además cierra la sesión), `403 AUT_006`.
  Cualquiera de ellos borra las cookies. Ver [2.4](#24-renovación-rotación-y-reutilización).

#### `POST /api/auth/logout`

- **Sin cuerpo.** Cierra la sesión de la cookie y la borra.
- **Respuesta `200`:** `{"detail": "Sesión cerrada"}` con las cookies borradas.

#### `GET /api/auth/me`

- **Sin parámetros.** Respuesta `200`: el perfil (`MeOut`). Es la forma de saber si hay sesión y
  qué puede hacer el usuario (ver el ejemplo del apartado 2.9).

#### `GET /api/auth/sessions`

- **Sin parámetros ni paginación.** Respuesta `200`: una **lista** de `SessionOut`, de la más
  reciente a la más antigua por `last_activity`. Solo las sesiones abiertas (máximo 5).

```json
[
  {
    "id": "01a0f5b4-e6e2-742d-8fe7-22c27538c9ab",
    "device": "Other  · Other · Escritorio",
    "ip_address": "127.0.0.1",
    "created_at": "2026-10-01T04:24:28.644651Z",
    "last_activity": "2026-10-01T04:24:28.643481Z",
    "expires_at": "2026-10-08T04:24:28.643283Z",
    "is_current": true
  }
]
```

#### `POST /api/auth/sessions/revoke-others`

- **Sin cuerpo.** Cierra todas mis sesiones menos la actual.
- **Respuesta `200`:** `{"detail": "Se cerraron N sesiones"}` (`N` puede ser 0).

#### `DELETE /api/auth/sessions/{session_id}`

- **Ruta:** `session_id`, uuid de una sesión **propia**. Respuesta `200`:
  `{"detail": "Sesión cerrada"}`. Si es la sesión actual, la respuesta también borra las cookies.
- **Errores:** `404 AUT_005` (no existe, o es de otro usuario).

#### `POST /api/auth/password`

- **Cuerpo:** `current_password` (texto, obligatorio, ≤ 128) y `new_password` (texto, obligatorio;
  [reglas de contraseña](#28-reglas-de-usuario-y-contraseña)).
- **Respuesta `200`:** `{"detail": "Contraseña actualizada"}`. Cierra **las demás** sesiones del
  usuario (la actual sigue) y deja un evento de seguridad.
- **Errores:** `422 VAL_422` con `fields.current_password: "La contraseña actual no es
  correcta"` (**no** es un `401`: la sesión es válida) o con las reglas de la nueva; `429 SYS_429`
  (comparte el contador del login).

```json
{
  "error": {
    "code": "VAL_422",
    "message": "Los datos enviados no son válidos.",
    "toast": true,
    "severity": "warning",
    "request_id": "01a0f5b4-f188-7123-924a-c4a7165a0c57",
    "event_id": null,
    "fields": { "current_password": "La contraseña actual no es correcta" },
    "details": {}
  }
}
```

### 8.2 Usuarios: `/api/users`

| Endpoint | Permiso | Acceso | Qué hace |
|---|---|---|---|
| `GET /api/users/` | `users.list` · 3001 | rol | Lista usuarios, con filtros |
| `GET /api/users/{item_id}` | `users.read` · 3002 | rol | Detalle (también eliminados) |
| `POST /api/users/` | `users.create` · 3003 | rol | Crea un usuario |
| `PATCH /api/users/{item_id}` | `users.update` · 3004 | rol | Edita parcialmente |
| `DELETE /api/users/{item_id}` | `users.delete` · 3005 | rol | Elimina (reversible) |
| `POST /api/users/{item_id}/restore` | `users.restore` · 3006 | rol | Restaura |
| `DELETE /api/users/{item_id}/hard` | `users.hard_delete` · 3007 | dev | Borra definitivamente |
| `POST /api/users/{item_id}/password` | `users.password.reset` · 3011 | rol | Restablece la contraseña de otro |
| `GET /api/users/{item_id}/sessions` | `users.sessions.list` · 3012 | rol | Sesiones abiertas de un usuario |
| `DELETE /api/users/{item_id}/sessions` | `users.sessions.revoke` · 3013 | rol | Cierra todas sus sesiones |

**Usuario (`UserOut`)**: `id`, `username`, `is_active`, `dev`, `role_id` (uuid o `null`),
`role_name` (texto o `null`; sale aunque el rol esté eliminado), `created_at`, `updated_at`,
`deleted_at` (fecha o `null`) y `last_login_at` (fecha o `null`). La contraseña **nunca** sale.

**Qué admite el listado `GET /api/users/`** (ver [sección 4](#4-listados-resource)):

| Capacidad | Parámetros |
|---|---|
| `search` | `username` |
| Filtros por igualdad, de varios valores | `is_active` (booleano), `dev` (booleano), `role_id` (uuid) |
| Filtros de texto (`_contains`) | Ninguno |
| Rangos (fecha y hora con zona) | `created_at_from` / `created_at_to`, `last_login_at_from` / `last_login_at_to` |
| `sort` | `username`, `is_active`, `created_at`, `last_login_at` |
| Orden por defecto | `username` ascendente |

#### `GET /api/users/`

Respuesta `200`: una página de `UserOut` ([ejemplos reales en 4.7](#47-ejemplos-reales)). Errores:
los de [4.8](#48-errores-de-validación-en-un-listado).

#### `GET /api/users/{item_id}`

Respuesta `200`: `UserOut`, **también si está eliminado** (con `deleted_at`). `404 USR_001` si el
id no existe.

#### `POST /api/users/`

| Campo | Tipo | Obligatorio | Reglas |
|---|---|---|---|
| `username` | texto | sí | 3–50, ASCII en minúsculas con `.`, `-`, `_`; único, también entre eliminados ([2.8](#28-reglas-de-usuario-y-contraseña)) |
| `password` | texto | sí | 8–128, con letra y número, sin espacios en los extremos |
| `role_id` | uuid o `null` | no (`null`) | Un rol vivo; sus permisos deben caber en los de quien crea (`PRM_004`) |
| `is_active` | booleano | no (`true`) | |
| `dev` | booleano | no (`false`) | `true` solo lo puede dar un dev (`USR_004`) |

Respuesta **`201`**: `UserOut`. Errores: `422 VAL_422` (campos), `409 SYS_409` (`fields.username`),
`422 VAL_REL` (`fields.role_id`), `403 USR_004`, `403 PRM_004`.

```bash
curl -s -b $JAR -X POST $API/users/ \
  -H "Content-Type: application/json" \
  -d '{"username":"anabb73c","password":"Secreta123","role_id":"01a0f5b4-e792-773b-ad8f-568ca3c83784"}'
```

```json
{
  "id": "01a0f5b4-eaf5-7052-8359-7266c87f472a",
  "username": "anabb73c",
  "is_active": true,
  "dev": false,
  "role_id": "01a0f5b4-e792-773b-ad8f-568ca3c83784",
  "role_name": "Vendedor bb73c",
  "created_at": "2026-10-01T04:24:29.686860Z",
  "updated_at": "2026-10-01T04:24:29.686887Z",
  "deleted_at": null,
  "last_login_at": null
}
```

#### `PATCH /api/users/{item_id}`

Todos los campos son opcionales: `username`, `role_id`, `is_active` y `dev`, con las mismas reglas
que al crear. Se aplica lo de [5.3](#53-editar-patch): `role_id: null` le **quita el rol**;
`username`, `is_active` y `dev` no admiten `null`. La contraseña **no** se cambia aquí.
Respuesta `200`: `UserOut`.

Errores propios: `404 USR_001` (no existe, o está eliminado), `403 USR_005` (el usuario es dev y
quien edita no), `403 PRM_004` (el usuario o el rol nuevo tienen permisos que quien edita no
tiene), `403 USR_004` (envía `dev` sin ser dev), `409 USR_003` (se desactiva o se quita `dev` a
sí mismo), `409 SYS_409`, `422 VAL_REL`, `422 VAL_422`.

#### `DELETE /api/users/{item_id}`

Eliminación reversible. Cierra **todas las sesiones** del usuario. Respuesta `200`:
`{"detail": "<username> eliminado"}`. Errores: `404 USR_001`, `409 USR_003` (a sí mismo),
`403 USR_005`, `403 PRM_004`.

#### `POST /api/users/{item_id}/restore`

Respuesta `200`: `UserOut` ya sin `deleted_at`. Errores: `404 USR_001` (el id no existe),
`409 SYS_RESTORE` (no estaba eliminado), `403 USR_005`, `403 PRM_004`, `422 VAL_REL` (su rol ya no
existe o está eliminado).

#### `DELETE /api/users/{item_id}/hard`

Solo dev. Borra la fila (viva o eliminada) y sus sesiones, y deja un evento `hard_delete`.
Respuesta `200`: `{"detail": "<username> borrado definitivamente"}`. Errores: `403 PRM_002` (no
eres dev), `404 USR_001`, `409 USR_003` (a sí mismo).

#### `POST /api/users/{item_id}/password`

- **Cuerpo:** `new_password` (texto, obligatorio, [reglas de contraseña](#28-reglas-de-usuario-y-contraseña)).
- **Respuesta `200`:** `{"detail": "Contraseña restablecida; se cerraron sus sesiones"}`. Cierra
  **todas** las sesiones del usuario y deja un evento de seguridad (`password_change`, gravedad
  `warning`).
- **Errores:** `404 USR_001`, `403 USR_005`, `403 PRM_004`, `422 VAL_422`.

#### `GET /api/users/{item_id}/sessions`

Respuesta `200`: **lista** de `SessionOut` del usuario, más reciente primero; `is_current` es
siempre `false`. Sirve también para usuarios eliminados. Error: `404 USR_001`.

```json
[
  {
    "id": "01a0f5b4-f15a-753b-b8c0-1976ca99ce74",
    "device": "Other  · Other · Escritorio",
    "ip_address": "127.0.0.1",
    "created_at": "2026-10-01T04:24:31.323384Z",
    "last_activity": "2026-10-01T04:24:33.002894Z",
    "expires_at": "2026-10-08T04:24:33.002747Z",
    "is_current": false
  }
]
```

#### `DELETE /api/users/{item_id}/sessions`

Cierra todas las sesiones abiertas del usuario (él puede volver a iniciar sesión). Respuesta
`200`: `{"detail": "Se cerraron N sesiones"}`. Deja un evento de seguridad `session_revoked`
(`warning`). Errores: `404 USR_001`, `403 USR_005`, `403 PRM_004`.

### 8.3 Roles: `/api/roles`

| Endpoint | Permiso | Acceso | Qué hace |
|---|---|---|---|
| `GET /api/roles/` | `roles.list` · 4001 | rol | Lista roles |
| `GET /api/roles/{item_id}` | `roles.read` · 4002 | rol | Detalle (también eliminados) |
| `POST /api/roles/` | `roles.create` · 4003 | rol | Crea un rol |
| `PATCH /api/roles/{item_id}` | `roles.update` · 4004 | rol | Edita parcialmente |
| `DELETE /api/roles/{item_id}` | `roles.delete` · 4005 | rol | Elimina (reversible) |
| `POST /api/roles/{item_id}/restore` | `roles.restore` · 4006 | rol | Restaura |
| `DELETE /api/roles/{item_id}/hard` | `roles.hard_delete` · 4007 | dev | Borra definitivamente |

**Rol (`RoleOut`)**: `id`, `name`, `description`, `permissions` (lista de ids, ordenada),
`users_count` (usuarios **vivos** con ese rol), `created_at`, `updated_at` y `deleted_at`.

**Qué admite el listado `GET /api/roles/`:**

| Capacidad | Parámetros |
|---|---|
| `search` | `name` |
| Filtros por igualdad, de varios valores | Ninguno |
| Filtros de texto (`_contains`) | Ninguno |
| Rangos (fecha y hora con zona) | `created_at_from` / `created_at_to`, `updated_at_from` / `updated_at_to` |
| `sort` | `name`, `created_at`, `updated_at` |
| Orden por defecto | `name` ascendente |

#### `GET /api/roles/` y `GET /api/roles/{item_id}`

El listado devuelve una página de `RoleOut` ([ejemplo real en 4.7](#47-ejemplos-reales)); el
detalle, un `RoleOut` también si está eliminado, o `404 ROL_001`.

#### `POST /api/roles/`

| Campo | Tipo | Obligatorio | Reglas |
|---|---|---|---|
| `name` | texto | sí | 2–100 caracteres (se quitan los espacios de los extremos); **único**, también entre eliminados |
| `description` | texto | no (`""`) | Hasta 255 |
| `permissions` | lista de enteros | no (`[]`) | Hasta **2000** ids; solo de alcance `role` (ver el catálogo); se guardan ordenados y sin repetidos; deben caber en los permisos de quien lo crea |

Respuesta **`201`**: `RoleOut` (ejemplo en el apartado 5.2). Errores: `422 VAL_422`,
`422 ROL_004` (ids que no existen o no se pueden asignar, con `details.unknown`), `409 SYS_409`
(`fields.name`), `403 PRM_004`.

#### `PATCH /api/roles/{item_id}`

Campos opcionales `name`, `description`, `permissions`, con las mismas reglas. Ninguno admite
`null`. **Enviar `permissions` sustituye la lista entera** (para quitar uno, se envía la lista sin
él; `[]` vacía el rol). Respuesta `200`: `RoleOut`. Errores: `404 ROL_001` (no existe o está
eliminado), `403 PRM_004` (el rol, tal como está, o los permisos nuevos pasan de los de quien
edita), `422 ROL_004`, `409 SYS_409`, `422 VAL_422`.

#### `DELETE /api/roles/{item_id}`

Eliminación reversible. Respuesta `200`: `{"detail": "<nombre> eliminado"}`. Errores: `404 ROL_001`,
`409 ROL_003` (hay usuarios vivos con ese rol; `details.role_id`), `403 PRM_004`.

#### `POST /api/roles/{item_id}/restore`

Respuesta `200`: `RoleOut`. Errores: `404 ROL_001` (el id no existe), `409 SYS_RESTORE` (no estaba
eliminado), `403 PRM_004`.

#### `DELETE /api/roles/{item_id}/hard`

Solo dev. Respuesta `200`: `{"detail": "<nombre> borrado definitivamente"}`. Errores: `403 PRM_002`,
`404 ROL_001`, `409 ROL_003` (aquí cuentan **también los usuarios eliminados** que apuntan al rol).

### 8.4 Auditoría: `/api/events`

| Endpoint | Permiso | Acceso | Qué hace |
|---|---|---|---|
| `GET /api/events/` | `events.list` · 5001 | rol | Lista eventos, con filtros |
| `GET /api/events/{event_id}` | `events.read` · 5002 | rol | Detalle de un evento |
| `GET /api/events/history/{entity_type}/{entity_id}` | `events.history` · 5003 | rol | Historial de un registro |
| `GET /api/events/verify` | `events.verify` · 5004 | rol | Verifica la integridad de la cadena |
| `GET /api/events/stats` | `events.stats` · 5005 | rol | Totales por categoría, acción y gravedad |

Cuerpos de respuesta, parámetros y ejemplos reales: [sección 7](#7-auditoría) (listar: 7.2,
detalle: 7.3, historial: 7.4, estadísticas: 7.5, verificar: 7.6). Son todos `GET`, sin cuerpo.
Errores propios:

| Endpoint | Errores |
|---|---|
| `GET /api/events/` | `422` en un filtro mal escrito (`category=foo`: `Valor no permitido`; fecha sin zona; uuid mal) |
| `GET /api/events/{event_id}` | `404 EVT_001` |
| `GET /api/events/history/{entity_type}/{entity_id}` | `422` si un parámetro pasa de 50 caracteres. Un registro sin eventos devuelve una página vacía |
| `GET /api/events/verify` | `422` (`event_id` con fechas, `date_from` después de `date_to`, fecha sin zona), `404 EVT_001` |
| `GET /api/events/stats` | Ninguno propio |

### 8.5 Sistema: `/api/system`

| Endpoint | Permiso | Acceso | Qué hace |
|---|---|---|---|
| `GET /api/system/health` | `system.health` · 1001 | público | Estado del servidor y de la base |
| `GET /api/system/info` | `system.info` · 1002 | con sesión | Configuración y políticas vigentes |
| `GET /api/system/permissions` | `system.permissions` · 1003 | con sesión | Catálogo de permisos |
| `GET /api/system/errors` | `system.errors` · 1004 | rol | Catálogo de errores |
| `GET /api/system/test-error/{status_code}` | `system.test_error` · 1005 | dev | Provoca un error de prueba |

#### `GET /api/system/health`

Sin sesión. `200` si la base responde; `503 SYS_503` si no. No devuelve nada más (ni versión ni
configuración).

```json
{ "status": "up", "database": "up" }
```

#### `GET /api/system/info`

Los valores vigentes que un cliente puede necesitar:

```json
{
  "name": "Template",
  "version": "0.1.0",
  "debug": true,
  "access_expire_minutes": 15,
  "refresh_expire_days": 7,
  "max_sessions_per_user": 5,
  "password_min_length": 8,
  "login_attempts": 10,
  "login_attempts_per_ip": 50,
  "login_window_seconds": 300
}
```

#### `GET /api/system/permissions`

El catálogo de permisos con el campo `granted` de quien pregunta. Descrito, con ejemplo, en
[6.5](#65-el-catálogo-get-apisystempermissions).

#### `GET /api/system/errors`

El catálogo de errores de la API, ordenado por código, **incluidos los propios del proyecto**:

| Campo | Significado |
|---|---|
| `code`, `status`, `message` | Código, estado HTTP y mensaje por defecto |
| `toast`, `severity` | Lo que el error sugiere a la interfaz |
| `persist` | `true` si el error se guarda como evento de auditoría |
| `hint` | Nota interna sobre cuándo se produce (puede ir vacía) |

```json
[
  {
    "code": "AUT_001",
    "status": 401,
    "message": "Usuario o contraseña incorrectos.",
    "toast": true,
    "severity": "warning",
    "persist": true,
    "hint": ""
  },
  {
    "code": "AUT_002",
    "status": 401,
    "message": "Necesitas iniciar sesión para continuar.",
    "toast": false,
    "severity": "info",
    "persist": false,
    "hint": ""
  },
  "…"
]
```

#### `GET /api/system/test-error/{status_code}`

Solo dev. Sirve para ver cómo llega un error al frontend.

- **Ruta:** `status_code`, entero de 100 a 599 (fuera de rango, `422`). **Query:** `toast`
  (booleano, por defecto `true`) fija el campo `toast` de la respuesta.
- Con **400 a 599** (salvo 500): error `SYS_TEST` con ese estado HTTP, gravedad `info` y
  `details.status_code`.
- Con **500**: lanza una excepción real, y sale un `SYS_500` que se guarda como evento (con
  `DEBUG=true`, el error trae además `debug`).
- Con un estado menor de 400: `200` con `{"status": "ok", "detail": "No se generó ningún error"}`.

```json
{
  "error": {
    "code": "SYS_TEST",
    "message": "Error de prueba generado a propósito.",
    "toast": true,
    "severity": "info",
    "request_id": "01a0f5b4-e740-738b-bb8a-194e852698eb",
    "event_id": null,
    "fields": null,
    "details": { "status_code": 418 }
  }
}
```

---

## 9. Recetas

### 9.1 El flujo de un cliente: entrar, listar con filtros, crear, manejar errores y salir

Con un cookie jar de `curl` (`-c` guarda, `-b` envía). Primero, entrar, y mirar qué puede hacer el
usuario (los `permission_keys` de `me` dicen qué botones enseñar):

```bash
API=http://127.0.0.1:8000/api
JAR=jar.txt

curl -s -c $JAR -X POST $API/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"dev","password":"Dev12345"}'
```

Listar los roles que contienen «vendedor», ordenados por nombre, para que la persona elija uno
([sección 4](#4-listados-resource)):

```bash
curl -s -b $JAR -G $API/roles/ \
  --data-urlencode "search=vendedor" \
  --data-urlencode "sort=name" \
  --data-urlencode "size=20"
```

Crear un usuario con ese rol. La clave `Idempotency-Key` es **una por intención** (una por cada
pulsación de «Guardar» con datos nuevos), no una por petición:

```bash
KEY=$(openssl rand -hex 16)

curl -s -b $JAR -X POST $API/users/ \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $KEY" \
  -d '{"username":"anabb73c","password":"Secreta123","role_id":"01a0f5b4-e792-773b-ad8f-568ca3c83784"}'
```

La respuesta correcta es un `201` con el usuario (el cuerpo del apartado 8.2). Si el envío se
repite con la **misma** `$KEY` (un reintento tras un corte de red), no se crea otro: llega el mismo
`201` con `Idempotent-Replayed: true`. Qué hacer con cada respuesta:

| Respuesta | Qué hace el cliente |
|---|---|
| `201` | Muestra el usuario creado. Descarta la clave: la siguiente acción lleva otra |
| `422 VAL_422` | Pone cada mensaje de `fields` junto a su campo (`fields.password: "Debe tener al menos 8 caracteres"`). El error queda guardado 24 h con esa clave: usa una **nueva** al reenviar |
| `409 SYS_409` | `fields.username` dice que ya existe (también entre eliminados). El usuario cambia el nombre; clave nueva |
| `422 VAL_REL` / `422 ROL_004` | El rol ya no existe o no se puede asignar: recarga la lista de roles. Clave nueva |
| `403 PRM_001` / `PRM_004` / `USR_004` | No tiene permiso para eso: informar, no reintentar |
| `401` | `POST /auth/refresh` una vez y repetir con una clave derivada (`<clave>:renew`): el servidor guarda también los `401` con la clave, y un reintento idéntico recibiría el mismo |
| `429 SYS_429` | Esperar `details.retry_after_seconds` segundos |
| Sin respuesta, o `5xx` | Repetir con **la misma** clave: si llegó, devuelve lo guardado; si no, se ejecuta |
| `409 IDM_001` | La copia anterior sigue en proceso: repetir con la misma clave más tarde |

Y salir, que borra las cookies:

```bash
curl -s -b $JAR -c $JAR -X POST $API/auth/logout
```

### 9.2 Desde un script

**`curl`.** Una función evita repetir las opciones; `-c` y `-b` sobre el mismo archivo mantienen
las cookies al día aunque el servidor las cambie. Un acceso dura 15 minutos: si el script va a
tardar más, llama a `POST /auth/refresh` de vez en cuando.

```bash
API=http://127.0.0.1:8000/api
JAR=jar.txt

api() {
  curl -s -b "$JAR" -c "$JAR" -H "Content-Type: application/json" "$@"
}

api -X POST "$API/auth/login" -d '{"username":"dev","password":"Dev12345"}'
api -G "$API/roles/" --data-urlencode "search=vendedor" --data-urlencode "sort=name"
api -X POST "$API/auth/logout"
```

Para ver el estado HTTP y las cabeceras, `-i`; para solo el estado,
`-s -o /dev/null -w "%{http_code}\n"`. En PowerShell usa `curl.exe`.

**Python con `httpx`.** `httpx.Client` guarda las cookies solo. Este cliente renueva la sesión una
vez ante un `401`, convierte los errores de la API en una excepción con `code`, `fields` y
`request_id`, y deriva la clave de idempotencia al reintentar tras renovar:

```python
from typing import Any
from uuid import uuid4

import httpx

BASE = "http://127.0.0.1:8000/api"


class ApiError(Exception):
    def __init__(self, status: int, error: dict[str, Any]) -> None:
        super().__init__(f"{status} {error['code']}: {error['message']}")
        self.status = status
        self.code = error["code"]
        self.fields = error["fields"] or {}
        self.details = error["details"]
        self.request_id = error["request_id"]


def call(
    api: httpx.Client, method: str, path: str, *, key: str | None = None, **kwargs: Any
) -> Any:
    headers = {"Idempotency-Key": key} if key else {}
    response = api.request(method, path, headers=headers, **kwargs)
    if response.status_code == 401 and not path.startswith("/auth/"):
        if api.post("/auth/refresh").is_success:
            if method != "GET":
                headers = {"Idempotency-Key": f"{key or uuid4().hex}:renew"}
            response = api.request(method, path, headers=headers, **kwargs)
    if response.is_error:
        raise ApiError(response.status_code, response.json()["error"])
    return response.json()


with httpx.Client(base_url=BASE, timeout=30) as api:
    call(api, "POST", "/auth/login", json={"username": "dev", "password": "Dev12345"})

    roles = call(api, "GET", "/roles/", params={"search": "ventas", "sort": "name", "size": 20})
    print(roles["total"], [role["name"] for role in roles["items"]])

    body = {"username": "ana", "password": "Secreta123", "role_id": roles["items"][0]["id"]}
    try:
        user = call(api, "POST", "/users/", key=uuid4().hex, json=body)
    except ApiError as error:
        if error.code in ("VAL_422", "SYS_409", "VAL_REL"):
            raise SystemExit(f"Datos rechazados: {error.fields}")
        if error.code == "SYS_429":
            raise SystemExit(f"Espera {error.details['retry_after_seconds']} s")
        raise

    history = call(api, "GET", f"/events/history/users/{user['id']}", params={"size": 100})
    for event in history["items"]:
        print(event["created_at"], event["actor_username"], event["message"], event["changes"])

    call(api, "POST", "/auth/logout")
```

`httpx` escribe `True` como `true` y una lista como el parámetro repetido:
`params={"role_id": [id_a, id_b]}` equivale a `?role_id=…&role_id=…`. Si el script se queda sin
red o recibe un `5xx`, reintenta con la **misma** `key`.

**JavaScript con `fetch`.** En un navegador, `credentials: "include"` hace que las cookies viajen y
se guarden. Lo normal es llamar a `/api` por el proxy de Vite (el mismo origen: sin CORS). La
renovación se hace una sola vez aunque fallen varias peticiones a la vez:

```js
const BASE = "/api";

export class ApiError extends Error {
	constructor(status, error) {
		super(error.message);
		this.status = status;
		this.code = error.code;
		this.fields = error.fields ?? {};
		this.details = error.details;
		this.requestId = error.request_id;
	}
}

export const newKey = () =>
	Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");

function send(method, path, { body, key, params } = {}) {
	const query = params ? `?${new URLSearchParams(params)}` : "";
	const headers = {};
	if (body !== undefined) headers["Content-Type"] = "application/json";
	if (key) headers["Idempotency-Key"] = key;
	return fetch(`${BASE}${path}${query}`, {
		method,
		credentials: "include",
		headers,
		body: body === undefined ? undefined : JSON.stringify(body),
	});
}

let renewing = null;

export async function api(method, path, options = {}) {
	let response = await send(method, path, options);
	if (response.status === 401 && !path.startsWith("/auth/")) {
		renewing ??= send("POST", "/auth/refresh").finally(() => {
			renewing = null;
		});
		if ((await renewing).ok) {
			const key = method === "GET" ? options.key : `${options.key ?? newKey()}:renew`;
			response = await send(method, path, { ...options, key });
		}
	}
	const data = await response.json();
	if (!response.ok) throw new ApiError(response.status, data.error);
	return data;
}

await api("POST", "/auth/login", { body: { username: "dev", password: "Dev12345" } });

const page = await api("GET", "/users/", {
	params: [
		["is_active", "true"],
		["role_id", "01a0f5b4-e792-773b-ad8f-568ca3c83784"],
		["role_id", "01a0f5b4-e7ba-729b-a290-a6a3feacfe03"],
		["sort", "-last_login_at"],
	],
});
console.log(page.total, page.items.map((user) => user.username));

try {
	await api("POST", "/roles/", { body: { name: "Compras", permissions: [3001] }, key: newKey() });
} catch (error) {
	if (!(error instanceof ApiError)) throw error;
	console.log(error.code, error.fields);
}

await api("POST", "/auth/logout");
```

Para repetir un filtro hay que pasar los parámetros como lista de pares (`[["role_id", a],
["role_id", b]]`): un objeto no puede tener dos veces la misma clave. Notas:

- Entre pestañas, dos renovaciones a la vez con el mismo token cierran la sesión (apartado 2.4).
  El frontend de la plantilla lo evita con un bloqueo compartido (`navigator.locks`).
- Llamar a la API **directamente** desde otro origen (por ejemplo la web en `localhost:5173` y la
  API en `localhost:8000`) exige que ese origen esté en `CORS_ORIGINS` y que ambos sean del mismo
  sitio: con `localhost` y `127.0.0.1` mezclados, el navegador no envía las cookies `SameSite`. Con
  `DEBUG=false`, además, `SameSite=Strict` y `Secure` exigen servir la web y la API bajo el mismo
  dominio y por https.
- `fetch` de Node no guarda cookies: usa `curl` o `httpx`, un paquete con cookie jar, o reenvía
  tú la cabecera `Cookie` con lo que traiga `Set-Cookie`.

### 9.3 Qué cambió en un registro, y comprobar que el historial es fiable

**El historial completo de un registro**, de lo más antiguo a lo más nuevo. `entity_type` es la
**tabla** (`users`, `roles`) y `entity_id`, el id:

```bash
USER_ID=01a0f5b4-eaf5-7052-8359-7266c87f472a
curl -s -b $JAR "$API/events/history/users/$USER_ID?size=100"
```

Cada elemento dice **quién** (`actor_username`), **cuándo** (`created_at`), **qué** (`action` y
`message`), **qué campos** (`changes`, con `before` y `after`) y **desde qué petición**
(`request_id`, `method`, `path`). La contraseña sale como huella, nunca en claro.

**Solo los cambios de ese registro**, con el formato ligero del listado (sin `snapshot` ni
firmas):

```bash
curl -s -b $JAR -G $API/events/ \
  --data-urlencode "entity_type=users" \
  --data-urlencode "entity_id=$USER_ID" \
  --data-urlencode "only_changes=true" \
  --data-urlencode "order=oldest"
```

**Todo lo que hizo una petición** (por ejemplo, la de un error que te reportan con su
`request_id`), y **todo lo que hizo una persona en un periodo**:

```bash
curl -s -b $JAR -G $API/events/ --data-urlencode "request_id=01a0f5b4-f903-76ac-8759-01b7375ff426"

curl -s -b $JAR -G $API/events/ \
  --data-urlencode "actor_username=ana" \
  --data-urlencode "date_from=2026-10-01T00:00:00Z" \
  --data-urlencode "date_to=2026-10-02T00:00:00Z"
```

**Comprobar que el registro no se ha tocado.** Toda la cadena, un periodo o un solo evento
([7.6](#76-verificar-la-integridad-get-apieventsverify)):

```bash
curl -s -b $JAR $API/events/verify

curl -s -b $JAR -G $API/events/verify \
  --data-urlencode "date_from=2026-10-01T00:00:00Z" \
  --data-urlencode "date_to=2026-10-02T00:00:00Z"

curl -s -b $JAR "$API/events/verify?event_id=01a0f5b4-f919-74ae-ade9-581d3ee08887"
```

Cómo leer el resultado: `intact: true` y `append_only: true` es lo esperado. Con `intact: false`,
`first_broken_id` es el evento por el que empezar (`GET /api/events/{id}`) y `detail` dice qué
falla. Con `append_only: false`, la base ha perdido los triggers que impiden modificar los eventos:
el siguiente arranque del servidor los reinstala y deja un evento de aviso.

### 9.4 Documentar tu propio endpoint para que salga bien en `/docs`

El permiso hace casi todo el trabajo. Con el endpoint de abajo, `/docs` (con `DEBUG=true`) muestra
el resumen, la descripción, el permiso y los parámetros sin escribir nada más:

```python
DISCONTINUE = permission(6111, "products.discontinue", "Catálogo", "Descatalogar un producto")


@router.post("/{item_id}/discontinue", response_model=ProductOut)
async def discontinue(item_id: UUID, actor: Users = requires(DISCONTINUE)):
    """Retira el producto del catálogo público; responde 409 si ya estaba descatalogado."""
    ...
```

| Dónde sale en `/docs` | De dónde se toma |
|---|---|
| **Resumen** (el título del endpoint) | El cuarto argumento de `permission(...)`: `Descatalogar un producto`. Escríbelo como una acción, en español |
| **Descripción** | El **docstring** de la función (una línea) y, debajo, de forma automática: `Permiso: products.discontinue (id 6111). Acceso: usuarios cuyo rol lo incluya (y los dev).` Si no hay docstring, solo sale la línea del permiso |
| **`x-permission`** | Automático: `{"id": 6111, "key": "products.discontinue", "scope": "role"}` |
| **Grupo** | Las `tags` del router: `APIRouter(prefix="/products", tags=["Catálogo"])` |
| **Parámetros de la URL** | La firma: `limit: int = Query(5, ge=0, description="Máximo de productos")` pone el tipo, el límite y el texto |
| **Campos del cuerpo** | El esquema: `Field(min_length=2, max_length=100, description="Nombre del producto")` |
| **Respuesta de éxito** | `response_model=ProductOut` (o `Page[ProductOut]` en un listado) |
| **Otras respuestas** | Opcional, de FastAPI: `responses={409: {"description": "Ya estaba descatalogado"}}` en el decorador |

- Los endpoints que genera `Resource` no llevan docstring: su resumen sale de los permisos
  (`Listar productos`) y su descripción es solo la línea del permiso.
- Todo esto existe **solo con `DEBUG=true`**: con `DEBUG=false` no hay `/docs` ni `/openapi.json`.
- No hay un paso extra para aparecer: basta con que el router esté en `ROUTERS` de
  `app/registry.py` (sin eso el endpoint no existe). `fastapi dev` recarga solo y `/docs` se
  actualiza al refrescar.
- Los errores propios (`ERRORS` de `app/registry.py`) salen en `GET /api/system/errors` y en la
  página Debug del frontend, no en `/docs`: descríbelos en el docstring.
- Cómo se declaran los permisos, los routers y los errores: `app/routes/steps.md` y
  `app/errors/steps.md`.

### 9.5 Trampas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `404 SYS_404` en un endpoint que existe | Barra final de más o de menos | La colección **con** barra (`/api/users/`); el resto sin ella |
| `422` con `fields: {"body": "Debe ser un objeto"}` | Falta `Content-Type: application/json` | `-H "Content-Type: application/json"` |
| `401 AUT_002` justo después de iniciar sesión | La siguiente llamada no lleva las cookies (`-b`), o en PowerShell `curl` es otro programa | `-b $JAR`; usa `curl.exe` |
| Una escritura devuelve lo mismo que la anterior y no crea nada | La idempotencia automática: igual y seguida, durante 10 s | Cambia algo, espera, o envía una `Idempotency-Key` distinta |
| `403 PRM_003` desde un script | El script envía una cabecera `Origin` que no es suya | No la envíes |
| La sesión se cierra sola tras renovar en paralelo | Dos renovaciones con el mismo token de refresco: el servidor lo toma por robado | Renueva de una en una |
| `422 La fecha necesita zona horaria` | La fecha va sin `Z` ni desfase, o el `+02:00` se envió sin codificar (el `+` es un espacio) | `2026-01-01T00:00:00Z`, o `%2B02:00` |
| El historial de un registro sale vacío | `entity_type` es el nombre de la clase (`Role`) y no el de la tabla (`roles`) | `/api/events/history/roles/{id}` |
| Un filtro «no hace nada» | Un parámetro que el recurso no declara se ignora, o está mal escrito | Mira el `GET /` del recurso en `/docs` |
| `422` con `size` mayor de 100 | El máximo es 100 | Pagina |
| No puedo reutilizar el nombre de un usuario eliminado | La unicidad cuenta también los eliminados | Restáuralo o bórralo definitivamente (dev) |
| `429 SYS_429` al probar logins | 10 intentos por usuario e IP en 5 minutos | Espera `details.retry_after_seconds` |
| Un `PATCH` con `null` da `422 No puede quedar vacío` | Esa columna es obligatoria | Solo se pone a `null` lo que admite nulos (`role_id`) |

---

## 10. Resumen de límites

### 10.1 Límites numéricos

| Límite | Valor | Dónde vive |
|---|---|---|
| Tamaño del cuerpo de una petición | 1 MiB (1 048 576 bytes); si no, `413 SYS_413` | `app/main.py`: `BodyLimitMiddleware(limit=…)` |
| Filas por página (`size`) | Por defecto 50; de 1 a 100 | `fastapi-pagination`: `Params` |
| Página (`page`) | Desde 1 | `fastapi-pagination`: `Params` |
| Columnas de `sort` | Hasta 4; el texto de `sort`, hasta 200 caracteres | `app/core/crud.py`: `order_of` y `filters_class` |
| `search` de un recurso | Hasta 100 caracteres | `app/core/crud.py`: `filters_class` |
| `<columna>_contains` y cada valor de un filtro de texto | Hasta 100 caracteres | `app/core/crud.py`, `app/core/schemas/types.py` (`SearchText`) |
| Filtros del listado de eventos | Entre 10 y 255 caracteres según el filtro (ver 7.2); `search`, 255 | `app/core/schemas/event.py`: `EventFilters` |
| `entity_type` y `entity_id` del historial | Hasta 50 caracteres | `app/core/routes/events.py` |
| `status_code` de `test-error` | De 100 a 599 | `app/core/routes/system.py` |
| Nombre de usuario | De 3 a 50 caracteres | `app/core/schemas/validators.py` |
| Contraseña | De 8 a 128 caracteres | `app/core/schemas/validators.py` |
| Nombre de un rol | De 2 a 100 caracteres | `app/core/schemas/role.py` |
| Descripción de un rol | Hasta 255 caracteres | `app/core/schemas/role.py` |
| Permisos por rol | Hasta 2000 ids | `app/core/schemas/role.py` |
| Token de acceso | 15 minutos | `app/core/security.py`: `ACCESS_MINUTES` |
| Token de refresco | 7 días | `app/core/security.py`: `REFRESH_DAYS` |
| Vida absoluta de una sesión | 30 días desde que se abrió | `app/core/models/session.py`: `is_expired` |
| Sesiones abiertas por usuario | 5 | `app/core/services/auth.py`: `MAX_SESSIONS_PER_USER` |
| Intentos de login | 10 por usuario e IP, 50 por IP | `app/core/services/auth.py`: `LOGIN_ATTEMPTS`, `LOGIN_ATTEMPTS_PER_IP` |
| Ventana de los intentos | 300 segundos | `app/core/services/auth.py`: `LOGIN_WINDOW_SECONDS` |
| Actividad de una sesión | Se anota si pasaron más de 60 segundos | `app/core/services/auth.py`: `authenticate` |
| `Idempotency-Key` | De 1 a 255 caracteres | `fastapi_idempotency`: `max_key_length` (valor por defecto) |
| Ventana de la idempotencia automática | 10 segundos | `fastapi_idempotency`: `automatic_window` (por defecto) |
| Ventana de la idempotencia con clave | 24 horas | `fastapi_idempotency`: `key_window` (por defecto) |
| Espera de una copia antes de `IDM_001` | 15 segundos | `fastapi_idempotency`: `wait_seconds` (por defecto) |
| Reserva de una escritura lenta | 60 segundos, renovada cada 20 | `fastapi_idempotency`: `lease_seconds`, `heartbeat_seconds` (por defecto) |
| Respuesta que se puede guardar para repetirla | Hasta 8 MiB | `fastapi_idempotency`: `max_response_body_bytes` (por defecto) |
| Eventos de error que se guardan | 30 por IP y código cada 60 segundos | `app/core/errors.py`: `PERSIST_LIMIT`, `PERSIST_WINDOW_SECONDS` |
| Texto del cliente que llega a logs y eventos | 300 caracteres, sin saltos de línea | `app/core/errors.py`: `MAX_TEXT_LENGTH` |
| Eventos por lote al verificar la cadena | 1000 | `app/core/services/audit.py`: `VERIFY_BATCH` |

`main.py` crea el middleware de idempotencia sin cambiar sus valores por defecto: son los de la
librería. Los de `LOGIN_*`, `MAX_SESSIONS_PER_USER` y los tiempos de los tokens salen también en
`GET /api/system/info`.

### 10.2 Configuración que cambia lo que ve el cliente

| Variable (`backend/.env`) | Efecto visible |
|---|---|
| `DEBUG` | `true`: existen `/docs` y `/openapi.json`; los errores `500` traen `debug`; cookies `SameSite=Lax` sin `Secure`. `false`: nada de eso; cookies `SameSite=Strict` y `Secure`; cabecera `Strict-Transport-Security`; `JWT_ISSUER` y `CORS_ORIGINS` deben ser `https://` |
| `APP_NAME` | El nombre de las cookies (`<slug>_access`, `<slug>_refresh`), el título de `/docs` y el `name` de `/api/system/info` |
| `APP_VERSION` | La versión de `/docs` y de `/api/system/info` |
| `CORS_ORIGINS` | Los orígenes de navegador que pueden llamar con cookies **y** que superan la comprobación CSRF. No admite `*` |
| `JWT_ISSUER` | El emisor que firman los tokens. Cambiarlo invalida las sesiones abiertas |
| `SECRET_KEY` | De ella salen todas las claves. Cambiarla cierra todas las sesiones, deja las contraseñas guardadas sin efecto y rompe la verificación de la cadena ya escrita |

Lo que CORS permite a un navegador desde un origen autorizado: métodos `GET`, `POST`, `PUT`,
`PATCH`, `DELETE` y `OPTIONS`; cabeceras `Authorization`, `Content-Type`, `Accept`, `Origin`,
`X-Request-ID` e `Idempotency-Key`; y puede **leer** las cabeceras de respuesta `X-Request-ID`,
`Idempotent-Replayed` y `Content-Disposition`.

Cabeceras de seguridad que acompañan **toda** respuesta: `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY` y `Referrer-Policy: no-referrer` (y `Strict-Transport-Security` con
`DEBUG=false`). Las respuestas de `/api` añaden `Cache-Control: no-store` y
`Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`: ninguna se guarda en cachés.

