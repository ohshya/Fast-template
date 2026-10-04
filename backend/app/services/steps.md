# Servicios (`app/services/`)

Aquí va la **lógica de negocio**: las reglas que no pertenecen a un solo modelo
ni a un solo endpoint. Un servicio es un archivo de funciones `async` que no
saben nada de HTTP: reciben modelos o valores, hacen algo y devuelven modelos o
valores.

- Esta carpeta **no se registra en ningún sitio**: los servicios los importan
  rutas, otros servicios, scripts y tareas.
- Los servicios del sistema están en `app/core/services/` (eventos,
  autenticación y sesiones, usuarios, auditoría).

Ejemplos de esta guía: el catálogo de `app/models/steps.md`.

---

## 1. ¿Servicio, método del modelo o ruta?

| Si la lógica... | Va en |
|---|---|
| Solo usa los datos de un registro y no consulta otros modelos | **Método del modelo** (`app/models/`) |
| Es un paso de una petición HTTP: leer parámetros, elegir la respuesta | **Ruta** (`app/routes/`) |
| Une varios modelos, aplica una regla de negocio o llama a un servicio externo | **Servicio** |
| Se necesita desde varios sitios (dos rutas, una ruta y un script) | **Servicio** |
| Es una validación de un campo o de un cuerpo | **Esquema** (`app/schemas/`) |

Una ruta debe poder leerse de un vistazo: recibe, llama a un servicio y responde.

---

## 2. Anatomía

Un archivo por dominio (`catalog.py`, `billing.py`). Funciones con un docstring de
una línea, tipos completos y errores con `AppError`:

```python
from app.core.errors import AppError
from app.errors.catalog import OUT_OF_STOCK
from app.models.product import Product


async def change_stock(product: Product, delta: int) -> Product:
    """Suma o resta unidades; falla si quedaría por debajo de cero."""
    if product.stock + delta < 0:
        raise AppError(OUT_OF_STOCK, details={"sku": product.sku, "stock": product.stock})
    product.stock += delta
    await product.save()
    return product
```

Y desde la ruta:

```python
product = await change_stock(await products.get(item_id), data.delta)
```

Reglas:

- **No importes nada de `fastapi`** salvo que sea imprescindible (`Request`).
  Así el servicio se puede llamar desde un script o una tarea.
- **No conviertas a esquemas de salida**: eso es de la ruta.
- Recibe **objetos** (`product`) cuando ya los tienes cargados y **ids** cuando el
  servicio debe cargarlos.
- Nada de estado global. Si necesitas configuración, léela de un objeto de ajustes
  (sección 6).

---

## 3. Errores

Lanza `AppError` con un error del catálogo. La ruta no tiene que capturarlo: se
convierte solo en la respuesta uniforme (`code`, `message`, `fields`, `request_id`).

```python
raise AppError(Err.VALIDATION, fields={"stock": "No puede ser negativo"})
raise AppError(OUT_OF_STOCK, details={"sku": product.sku})
```

Los errores propios del proyecto se declaran en `app/errors/` y se listan en
`ERRORS` de `app/registry.py` (ver `app/errors/steps.md`).

---

## 4. Transacciones e historial

- Dentro de una ruta de escritura ya hay una **transacción**: un servicio no
  necesita abrir otra. Si algo lanza un error, se deshace todo, historial incluido.
- **Fuera de una ruta** (un script, una tarea en segundo plano) abre la tuya:

```python
from typing import Any

from tortoise.transactions import in_transaction


async def import_products(rows: list[dict[str, Any]]) -> int:
    """Crea varios productos: o entran todos o ninguno."""
    async with in_transaction():
        for row in rows:
            await Product.create(**row)
    return len(rows)
```

- El historial de cada `save()` lo escribe el sistema. Para hechos que no son un
  cambio de tabla, registra un evento:

```python
from app.core.models.event import EventAction
from app.core.services.event_log import record_security, record_system

await record_security(EventAction.SYSTEM, f"{user_name} exportó {rows} productos")
await record_system("Importación diaria terminada", entity_type="products")
```

| Función | Para qué |
|---|---|
| `record_security(acción, mensaje, severity=...)` | Sesiones, accesos, exportaciones, acciones sensibles |
| `record_system(mensaje)` | Arranques, scripts, tareas programadas |
| `record(categoría, acción, mensaje, ...)` | La función general; las otras dos la usan |

Parámetros opcionales: `severity` (`"info"`, `"warning"`, `"critical"`),
`entity_type`, `entity_id` y `entity_label` (para que aparezca en el historial de
ese registro), `changes`, `snapshot` y `context_data` (datos extra), y
`actor_id`/`actor_username` si el actor no es quien hace la petición. Los eventos
se firman en cadena: no se editan ni se borran (la base lo impide con triggers; ver
"Integridad del registro de eventos" en `GUIA.md`).

---

## 5. Efectos que no deben bloquear la respuesta

Enviar un correo, avisar a otro sistema o recalcular algo pesado: se pide desde
la ruta con `BackgroundTasks` y corre **después** de responder, con su propia
transacción:

```python
@router.post("/{item_id}/publish", response_model=ProductOut)
async def publish(item_id: UUID, background: BackgroundTasks, actor: Users = requires(PUBLISH)):
    product = await products.get(item_id)
    background.add_task(notify_subscribers, product.id)
    return await products.one(product)
```

La tarea es una función de servicio corriente. La exportación de
`app/routes/steps.md` deja constancia así:

```python
from app.core.models.event import EventAction
from app.core.services.event_log import record_security


async def register_export(username: str, rows: int) -> None:
    """Deja constancia de una exportación."""
    await record_security(EventAction.SYSTEM, f"{username} exportó {rows} productos")
```

Si la tarea falla, el cliente ya recibió su respuesta: registra el fallo con
`record_system(..., severity="warning")` en lugar de dejarlo pasar en silencio.

### Servicios externos (otras API)

Usa `httpx` con **tiempo máximo** y no llames dentro de una transacción larga:

```python
import httpx

from app.core.errors import AppError, Err


async def fetch_rate(currency: str) -> float:
    """Cambio actual de una moneda."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"https://api.example.com/rates/{currency}")
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise AppError(Err.DATABASE_ERROR, log_message=f"Servicio de cambio caído: {exc}") from exc
    return float(response.json()["rate"])
```

Para un error de un servicio externo declara uno propio en `app/errors/` (por
ejemplo `EXCHANGE_UNAVAILABLE`, `503`) y añádelo a `ERRORS` en vez de reutilizar
`DATABASE_ERROR`.

---

## 6. Configuración propia

Las variables del `.env` que solo usa tu proyecto van en su propio objeto de
ajustes, sin tocar el del sistema:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class ShopSettings(BaseSettings):
    currency: str = "EUR"
    low_stock_limit: int = 5

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


shop_settings = ShopSettings()
```

Se guarda como `app/services/shop_settings.py` y se importa donde haga falta:
`from app.services.shop_settings import shop_settings`. En `.env`:
`CURRENCY=USD`. Los ajustes del sistema (`from app.settings import settings`, en
`app/settings.py`) se pueden leer, no cambiar.

---

## 7. Servicios del sistema que puedes usar

| Importación | Qué ofrece |
|---|---|
| `app.core.services.event_log` | `record`, `record_security`, `record_system` |
| `app.core.services.auth` | `granted_permissions(user)` y las constantes de sesión y límites de login |
| `app.core.services.users` | `create_dev_user` y las comprobaciones de la sección 8: `check_can_grant`, `check_role_assignable`, `protect_account` (`async`) y `check_dev_change` |
| `app.core.services.audit` | `build_events_query`, `event_stats`, `verify_chain` |

Y el resto del core que se usa desde un servicio: `app.core.errors` (`AppError`,
`Err`), `app.core.models.*` (`Users`, `Role`, `Entity`), `app.core.context`
(`get_context()` da el usuario y el `request_id` de la petición en curso).

---

## 8. Actuar sobre otros usuarios, roles y permisos

Regla del sistema: **quien no es dev no puede conceder ni gestionar más permisos
de los que tiene**. Si lo intenta, la petición falla con `403 PRM_004`
(`Err.PRIVILEGE_ESCALATION`) y `details.permissions` lista los permisos que le
sobran. Un servicio que asigne un rol, guarde una lista de permisos o toque la
cuenta de otro usuario tiene que pasar por estas comprobaciones de
`app.core.services.users` **antes** de guardar:

| Función | Cuándo llamarla | Si no pasa |
|---|---|---|
| `await check_can_grant(actor, ids)` | Vas a conceder o guardar una lista de ids de permiso | `403 PRM_004` si el actor no tiene alguno |
| `await check_role_assignable(actor, role_id)` | Vas a asignar un rol (con `None` no comprueba nada) | `403 PRM_004` si el rol tiene permisos que el actor no tiene |
| `await protect_account(actor, target)` | Vas a actuar sobre otro usuario: editarlo, cambiarle el rol, cerrarle las sesiones... | `403 USR_005` si es una cuenta dev y el actor no lo es; `403 PRM_004` si tiene más permisos que el actor |
| `check_dev_change(actor, wants_dev)` | Tu lógica puede cambiar la marca `dev` de una cuenta | `403 USR_004` si el actor no es dev |

Un usuario `dev` las pasa todas. El `actor` llega desde la ruta
(`actor: Users = requires(...)`): pásalo al servicio, no lo busques en
`get_context()`.

Ejemplo: un equipo tiene un rol y quien entra en él lo recibe. El servicio comprueba
las dos cosas antes de guardar; si alguna falla, no se guarda nada:

```python
from app.core.models.user import Users
from app.core.services.users import check_role_assignable, protect_account
from app.models.team import Team


async def add_member(actor: Users, team: Team, user: Users) -> Users:
    """Pasa un usuario al rol del equipo: exige poder gestionarlo y poder conceder ese rol."""
    await protect_account(actor, user)
    await check_role_assignable(actor, team.role_id)
    user.role_id = team.role_id
    await user.save(update_fields=["role_id"])
    return user
```

El modelo `Team`, su recurso y la ruta que llama a este servicio están en
`app/routes/steps.md`, sección 6.

---

## 9. Comprobar un servicio

No hay pruebas unitarias. Para ver un servicio
funcionando, llama desde `/docs` (con `DEBUG=true`) al endpoint que lo usa y
revisa dos cosas: la respuesta (o el error con su `code`) y los eventos que dejó
en la página **Auditoría**, buscándolos por el `request_id`.

---

## 10. Errores frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| Un cambio se guardó aunque la ruta respondió error | El servicio corrió en una tarea en segundo plano o fuera de una ruta de escritura | Abre `async with in_transaction():` |
| `ImportError` circular | El servicio importa una ruta, o dos servicios se importan entre sí | Los servicios no importan rutas; mueve lo común a un tercero |
| El historial no registra un cambio | Se usó `Model.filter(...).update(...)` | Carga el objeto y usa `save()` |
| El evento no muestra el actor | Se llamó desde un script sin sesión | Pasa `actor_username=` a `record(...)` |
| La ruta se cuelga esperando a un servicio externo | Falta el `timeout` | Usa siempre `httpx.AsyncClient(timeout=...)` |
| `403 PRM_004` al asignar un rol o permisos | El actor no es dev y no tiene alguno de esos permisos | Es lo esperado: lo asigna quien los tenga, o un dev |
| `403 USR_005` al actuar sobre una cuenta | La cuenta es dev y el actor no | Lo hace un dev |
