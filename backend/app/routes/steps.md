# Rutas (`app/routes/`)

Aquí se declaran los endpoints de tu proyecto. Nada se carga solo: cada archivo de
rutas exporta un `router` que se añade a la lista `ROUTERS` de `app/registry.py`
(sección 1), y `main.py` lo monta bajo `/api`.

Los endpoints del sistema (sesión, usuarios, roles, auditoría, salud) están en
`app/core/routes/` y no se tocan. `app/core/registry.py` es el registro del
sistema y tampoco se edita.

Antes de una ruta suelen hacer falta: el **modelo** (`app/models/steps.md`), sus
**esquemas** (`app/schemas/steps.md`) y, si hay lógica, un **servicio**
(`app/services/steps.md`). Ejemplos de esta guía: el catálogo de esas guías.

---

## 1. Forma de un archivo de rutas

De arriba abajo, siempre en este orden:

1. Imports.
2. Permisos.
3. Los `Resource` (CRUD) del archivo.
4. Los routers con su prefijo.
5. Los endpoints propios.
6. `mount(...)` de cada recurso, **después** de los endpoints propios.
7. El `router` final que se exporta.

Un archivo por dominio (`catalog.py`, `billing.py`). Dentro del archivo puede
haber varios recursos.

### Registrar el router

El archivo no hace nada hasta que su `router` está en `ROUTERS`: sin eso sus
endpoints no existen y sus permisos tampoco. En `app/registry.py`:

```python
from app.routes import catalog

ROUTERS: list[APIRouter] = [catalog.router]
```

Lo que la ruta usa se registra en su propia lista: los módulos de modelos en
`MODELS` y los errores propios en `ERRORS`. La sección 10 muestra el
`app/registry.py` completo del ejemplo. Los esquemas y los servicios no se
registran: la ruta los importa.

---

## 2. Permisos

**Cada endpoint declara exactamente un permiso.** Si una ruta no declara ninguno
o dos rutas comparten el mismo, **el servidor no arranca** y el mensaje dice cuál.
Así es imposible publicar un endpoint sin control de acceso.

Un permiso es un número estable (`6111`) con una clave (`products.discontinue`).
Un rol es una lista de esos números; se asignan en la página **Roles**.

### Declararlos

```python
from app.core.permissions import Scope, crud_permissions, permission

GROUP = "Catálogo"

CATEGORY_PERMS = crud_permissions(6000, "categories", GROUP, "categorías")
PRODUCT_PERMS = crud_permissions(6100, "products", GROUP, "productos")

DISCONTINUE = permission(6111, "products.discontinue", GROUP, "Descatalogar un producto")
PUBLIC_LIST = permission(6116, "products.public", GROUP, "Catálogo público", Scope.PUBLIC)
```

`crud_permissions(base, clave, grupo, nombre_en_plural)` crea los siete permisos
del CRUD:

| Permiso | Id | Clave |
|---|---|---|
| `PERMS.list` | base+1 | `products.list` |
| `PERMS.read` | base+2 | `products.read` |
| `PERMS.create` | base+3 | `products.create` |
| `PERMS.update` | base+4 | `products.update` |
| `PERMS.delete` | base+5 | `products.delete` |
| `PERMS.restore` | base+6 | `products.restore` |
| `PERMS.hard_delete` | base+7 | `products.hard_delete` (solo dev) |

**La descripción se ve en `/docs`.** Con `DEBUG=true`, el resumen de cada endpoint
en `/docs` es la descripción de su permiso (`"Descatalogar un producto"`), y a su
descripción se le añade una línea con la clave, el id y a quién deja entrar:
«Permiso: `products.discontinue` (id 6111). Acceso: usuarios cuyo rol lo incluya (y
los dev).» OpenAPI lo trae también como `x-permission` (`id`, `key`, `scope`).
Escribe cada descripción como una frase corta de acción: es el título que lee quien
use la API.

### Numeración

- Los ids de `1000` a `5999` son del sistema. **Los tuyos empiezan en `6000`.**
- Cada recurso CRUD ocupa un bloque de 100: `6000` categorías, `6100` productos,
  `6200` el siguiente.
- Dentro del bloque: `base+1` a `base+7` son el CRUD y `base+11` a `base+99` son
  los endpoints propios de ese recurso.
- Las claves siguen `<recurso>.<acción>`.
- No hay roles iniciales: el primer usuario dev crea los roles a mano en la página
  **Roles** y marca en ellos los permisos. Un permiso nuevo no lo tiene ningún rol
  hasta que alguien lo marca (sección 11).

### Alcance (`Scope`)

| Alcance | Quién entra |
|---|---|
| `Scope.ROLE` (por defecto) | Quien tenga el permiso en su rol, o un `dev` |
| `Scope.AUTHENTICATED` | Cualquier usuario con sesión, tenga rol o no |
| `Scope.PUBLIC` | Cualquiera, sin sesión |
| `Scope.DEV` | Solo usuarios `dev`. No se puede asignar a un rol |

Un usuario `dev` puede con todo. Un usuario sin rol solo usa los endpoints
`AUTHENTICATED`.

---

## 3. CRUD completo con `Resource`

`Resource` genera los siete endpoints de un modelo. Solo hay que decirle qué
modelo, qué esquemas y qué permisos:

```python
from app.core.crud import Resource


class CategoriesResource(Resource[Category]):
    model = Category
    create_schema = CategoryCreate
    update_schema = CategoryUpdate
    out_schema = CategoryOut
    permissions = CATEGORY_PERMS
    search_fields = ("name",)
    sort_fields = ("name", "created_at")
    ordering = ("name",)


categories = CategoriesResource()
categories_router = APIRouter(prefix="/categories")
categories.mount(categories_router)
```

### Atributos

| Atributo | Para qué |
|---|---|
| `model`, `create_schema`, `update_schema`, `out_schema`, `permissions` | Obligatorios |
| `search_fields` | Columnas donde busca `?search=` (contiene, sin distinguir mayúsculas; basta con que coincida una) |
| `filter_fields` | Columnas que se filtran por igualdad: `?status=active`. **Aceptan varios valores** repitiendo el parámetro: `?status=active&status=draft` (uno u otro) |
| `text_fields` | Columnas de texto que se filtran por «contiene», sin distinguir mayúsculas: `?name_contains=agua` |
| `range_fields` | Columnas numéricas o de fecha que se filtran por rango, extremos incluidos: `?price_from=2&price_to=4` |
| `sort_fields` | Columnas por las que se puede ordenar con `?sort=` |
| `ordering` | Orden cuando no llega `?sort=`. Por defecto `("-id",)`: lo más reciente primero (el id es un UUIDv7, que ordena por fecha de creación). No usa el `Meta.ordering` del modelo y no añade desempate: si la columna puede repetirse, termina con `"id"` para que la paginación sea estable |
| `not_found` | Error que se lanza si el registro no existe. Por defecto `Err.NOT_FOUND`; usa uno propio (`PRODUCT_NOT_FOUND`) para mensajes específicos |

Los atributos de búsqueda, filtro y orden (`search_fields`, `filter_fields`,
`text_fields`, `range_fields`, `sort_fields`) están vacíos por defecto: un recurso
solo admite lo que declara. Cada campo de `filter_fields`, `text_fields`,
`range_fields` y `sort_fields` debe ser una columna del modelo **y** un campo de
`out_schema` (ver «Qué se comprueba al arrancar»).

### Los siete endpoints

| Endpoint | Permiso | Qué hace |
|---|---|---|
| `GET /` | `list` | Listado paginado, con búsqueda, filtros y orden (ver "Parámetros del listado") |
| `GET /{id}` | `read` | Detalle, incluidos eliminados |
| `POST /` | `create` | Alta. Responde `201` |
| `PATCH /{id}` | `update` | Cambios parciales |
| `DELETE /{id}` | `delete` | Eliminación reversible |
| `POST /{id}/restore` | `restore` | Restauración |
| `DELETE /{id}/hard` | `hard_delete` | Borrado físico, solo dev |

### Parámetros del listado

`GET /` acepta estos parámetros de query y los combina todos con «y». `/docs` los
muestra con su tipo, los de tu recurso incluidos. Los errores salen como
`422 VAL_422` con el nombre del parámetro en `fields` y el mensaje en español (de
un parámetro repetido no se numeran los valores: `role_id`, no `role_id.0`).

| Parámetro | Valor | Qué hace | Error si no es válido |
|---|---|---|---|
| `page` | entero, 1 o más (por defecto 1) | Página | `Debe ser mayor o igual que 1` |
| `size` | entero de 1 a 100 (por defecto 50) | Registros por página | `Debe ser mayor o igual que 1`, `Debe ser menor o igual que 100` |
| `search` | texto, hasta 100 caracteres | Busca en `search_fields`. Sin `search_fields` no hace nada | `Máximo 100 caracteres` |
| `deleted` | `true` o `false` (por defecto `false`) | `true`: **solo** los eliminados. `false`: solo los vivos | `Debe ser verdadero o falso` |
| `sort` | hasta 200 caracteres | Orden: columnas separadas por comas, con `-` delante para descendente. Máximo 4, solo las de `sort_fields`. Siempre desempata por `id` | `Columnas permitidas (máximo 4): a, b` (columna que no está en `sort_fields`, o más de 4; con `sort_fields` vacío dice `ninguna`), `Máximo 200 caracteres` |
| `<campo>` (de `filter_fields`), repetible | el tipo de la columna | Igualdad; con varios valores, uno u otro (`IN`) | Según el tipo: `Identificador no válido` (UUID), `Debe ser un número entero`, `Debe ser verdadero o falso`, `Valor no permitido` (enum), `Máximo 100 caracteres` (texto) |
| `<campo>_contains` (de `text_fields`) | texto, hasta 100 caracteres | La columna contiene el texto, sin distinguir mayúsculas | `Máximo 100 caracteres` |
| `<campo>_from`, `<campo>_to` (de `range_fields`) | número, fecha o fecha y hora | `>=` y `<=`; se puede dar uno solo o los dos. Los registros con la columna vacía (`NULL`) quedan fuera | `Debe ser un número entero`, `Debe ser un número`, `Debe ser un número decimal`, `Fecha no válida`, `Fecha y hora no válidas`, `La fecha necesita zona horaria`; en `<campo>_to`, `Debe ser igual o posterior al inicio` si `_from` es posterior a `_to` |

Un parámetro que el recurso no declara **se ignora**, sin error: si un filtro no
hace nada, revisa su nombre en `/docs`.

- **Orden.** `?sort=-price,name` ordena por precio descendente y, a igualdad, por
  nombre. Al final se añade siempre `id`, así que dos páginas seguidas no repiten ni
  pierden filas. Sin `sort` (o con `?sort=` vacío) manda `ordering`. Solo se ordena
  por columnas del modelo: un campo calculado en `serialize` (`role_name`,
  `users_count`) no se puede ordenar.
- **Fechas y horas.** `date`: `2026-03-31`. `datetime`: ISO 8601 **con zona
  horaria**, `2026-03-31T00:00:00Z` o `2026-03-31T09:00:00-05:00`; sin zona da
  `La fecha necesita zona horaria`. El `+` de un desfase positivo se escribe `%2B`
  en la URL. Los extremos están incluidos: `_to` con un `datetime` llega hasta ese
  instante exacto, así que para incluir un día entero envía `T23:59:59.999999Z`.
- **Números.** Sin separador de miles y con punto decimal (`2`, `2.5`). Una columna
  entera rechaza `1.5`.

**Ejemplo.** Un recurso con todo declarado:

```python
class ProductsResource(Resource[Product]):
    model = Product
    create_schema = ProductCreate
    update_schema = ProductUpdate
    out_schema = ProductOut
    permissions = PRODUCT_PERMS
    search_fields = ("sku", "name")
    filter_fields = ("active", "category_id", "stock")
    text_fields = ("name", "sku")
    range_fields = ("price", "stock", "launched_on", "weight", "created_at")
    sort_fields = ("sku", "name", "price", "stock", "launched_on", "created_at")
```

Y una llamada con sesión iniciada (la cookie de sesión se guarda en `cookies.txt`):

```bash
curl -c cookies.txt -H "Content-Type: application/json" \
  -d '{"username": "dev", "password": "<contraseña>"}' http://127.0.0.1:8000/api/auth/login

curl -b cookies.txt "http://127.0.0.1:8000/api/products/?category_id=<id1>&category_id=<id2>&active=true&name_contains=agua&price_from=1.5&price_to=4&created_at_from=2026-01-01T00:00:00Z&sort=-price,sku&size=20"
```

Pide los productos activos de dos categorías cuyo nombre contiene «agua», con
precio entre 1,50 y 4, creados desde el 1 de enero de 2026, del más caro al más
barato (a igual precio, por SKU), de 20 en 20. Responde
`{"items": [...], "total": 2, "page": 1, "size": 20, "pages": 1}`. Con una columna
que no está en `sort_fields` (`?sort=category_id`):

```json
{ "error": { "code": "VAL_422", "message": "Los datos enviados no son válidos.",
             "fields": { "sort": "Columnas permitidas (máximo 4): sku, name, price, stock, launched_on, created_at" } } }
```

**Qué se comprueba al arrancar.** Al montar el recurso (`mount()`), cada campo de
`filter_fields`, `text_fields`, `range_fields` y `sort_fields` debe ser **una
columna del modelo** (también la clave foránea `<campo>_id`) **y un campo de
`out_schema`**: de ahí sale el tipo del parámetro. Si no, el servidor no arranca y
un `RuntimeError` dice cuál:

```
RuntimeError: ProductsResource.sort_fields: 'category_name' debe ser una columna de Product y un campo de ProductOut
RuntimeError: ProductsResource.range_fields: 'name' no es un número ni una fecha
```

- `range_fields` solo admite columnas `int`, `float`, `Decimal`, `date` o `datetime`.
- Los campos que rellena `serialize` (`category_name`, `role_name`, `users_count`)
  no son columnas: `Resource` no los filtra ni los ordena. Para eso, un endpoint
  propio con su consulta (sección 5).

### Lo que hace solo

- Rechaza `null` en campos obligatorios (`422`).
- Comprueba los campos `unique`, **incluidos los registros eliminados**
  (`409 SYS_409` con el campo en `fields`).
- Comprueba las claves foráneas al crear, editar y restaurar: apuntar a un
  registro inexistente o eliminado da `422 VAL_REL` con el campo.
- Pagina, busca, filtra (igualdad con varios valores, «contiene» y rangos) y ordena,
  y valida esos parámetros: un valor mal escrito da `422 VAL_422` con el parámetro
  en `fields`, en español. Cada uno aparece en `/docs` con su tipo.
- Al arrancar, comprueba que los campos declarados para filtrar y ordenar existen
  (ver arriba).
- Cada escritura va en una transacción y deja historial.
- Una escritura repetida (doble clic) se procesa una sola vez.

---

## 4. Reglas de negocio: los hooks

Sobrescribe estos métodos del `Resource`. Todos reciben `actor`, el usuario que
hace la petición. Si lanzan un error, **no se guarda nada**.

```python
from typing import Any

from app.core.errors import AppError, Err
from app.core.models.user import Users


class ProductsResource(Resource[Product]):
    ...

    async def before_create(self, data: dict[str, Any], actor: Users) -> dict[str, Any]:
        return {**data, "owner_id": actor.id}

    async def before_update(
        self, item: Product, data: dict[str, Any], actor: Users
    ) -> dict[str, Any]:
        if not item.active and "price" in data:
            raise AppError(Err.VALIDATION, fields={"price": "El producto está inactivo"})
        return data

    async def before_delete(self, item: Product, actor: Users, *, hard: bool) -> None:
        if item.stock > 0:
            raise AppError(Err.VALIDATION, fields={"stock": "Aún queda stock"})

    async def after_delete(self, item: Product, actor: Users) -> None: ...

    async def before_restore(self, item: Product, actor: Users) -> None: ...

    async def serialize(self, items: list[Product]) -> list[Any]: ...
```

| Hook | Cuándo corre | Qué hace |
|---|---|---|
| `before_create(data, actor)` | Antes de crear | Devuelve los datos que se guardan (añade, normaliza o rechaza) |
| `after_create(item, actor)` | Tras crear | Efectos dentro de la misma transacción: si lanzas un error, se deshace todo (también el evento) |
| `before_update(item, data, actor)` | Antes de editar | `data` solo lleva los campos enviados. Devuelve lo que se aplica |
| `after_update(item, changes, actor)` | Tras editar (solo si hubo cambios) | `changes` son los campos aplicados. Mismo contrato que `after_create` |
| `before_delete(item, actor, hard=...)` | Antes de eliminar | Valida. `hard` es `True` en el borrado definitivo |
| `after_delete(item, actor)` | Tras eliminar (reversible) | Efectos: cerrar sesiones, avisar... |
| `before_restore(item, actor)` | Antes de restaurar | Valida |
| `after_restore(item, actor)` | Tras restaurar | Efectos dentro de la transacción |
| `serialize(items)` | Al responder | Convierte registros en `out_schema`. Aquí se añaden campos de otras tablas |

Orden al crear: nulos → `before_create` → únicos → claves foráneas → guardado → `after_create`.
Al editar: nulos → `before_update` → únicos → claves foráneas → guardado → `after_update`.
Al restaurar: `before_restore` → claves foráneas → restauración → `after_restore`.

Si tu recurso permite **elegir un rol o guardar permisos**, o actúa sobre otros
usuarios, sus hooks deben usar las comprobaciones de la sección 6.

### `serialize`: campos que vienen de otra tabla

Recibe una lista, no un registro: consulta lo que necesites **una sola vez** y
rellena todos los elementos (así un listado de 20 filas hace una consulta, no 20):

```python
async def serialize(self, items: list[Product]) -> list[Any]:
    ids = {item.category_id for item in items}
    names = {row.id: row.name for row in await Category.with_deleted().filter(id__in=ids)}
    return [
        ProductOut.model_validate(item, from_attributes=True).model_copy(
            update={"category_name": names.get(item.category_id)}
        )
        for item in items
    ]
```

### Métodos útiles del `Resource`

Se usan dentro de tus endpoints propios:

| Método | Qué hace |
|---|---|
| `await resource.get(id)` | El registro vivo, o lanza `not_found` (404) |
| `await resource.get(id, include_deleted=True)` | Igual, incluyendo eliminados |
| `await resource.one(item)` | El registro convertido en `out_schema` |
| `await resource.serialize(items)` | Una lista convertida en `out_schema` |
| `await resource.check_unique(data)` | Lanza `409` si un campo único ya existe |
| `await resource.check_relations(data)` | Lanza `422` si una clave foránea no existe |

---

## 5. Endpoints propios

Para todo lo que no sea CRUD: acciones, listados especiales, exportaciones.

### Dónde declararlos

**Antes de `mount()`.** `GET /{item_id}` captura cualquier ruta de una sola
parte: `/low-stock` declarada después la interpretaría como un id y daría `422`.

```python
products_router = APIRouter(prefix="/products")


@products_router.get("/low-stock", response_model=list[ProductOut])
async def low_stock(limit: int = Query(5, ge=0), actor: Users = requires(LOW_STOCK)):
    """Productos activos con poco stock."""
    return await products.serialize(await Product.low_stock(limit))


products.mount(products_router)
```

El docstring de la función aparece como descripción en `/docs`.

### La barra final

La API no redirige las barras (`redirect_slashes=False` en `main.py`): una URL con
la barra de más o de menos da `404 SYS_404`. La colección se llama **con** barra
(`/api/products/`) y todo lo demás **sin** ella (`/api/products/{id}`,
`/api/products/low-stock`). Un endpoint propio sobre la colección se declara con
`"/"` (`@router.get("/")`); los demás, con su nombre y sin barra final.

### De dónde salen los parámetros

FastAPI los reparte por el tipo:

| Parámetro | Ejemplo |
|---|---|
| En la ruta | `item_id: UUID` con `"/{item_id}/stock"` |
| En la consulta (`?limit=5`) | `limit: int = Query(5, ge=0)` |
| En el cuerpo (JSON) | `data: StockChange` (un esquema) |
| En una cabecera | `token: str = Header()` |
| La petición entera | `request: Request` |
| Para tocar la respuesta | `response: Response` (cookies, cabeceras) |
| Tareas tras responder | `background: BackgroundTasks` |
| Filtros agrupados | `filters: ProductFilters = Depends()` |

### El usuario

```python
async def discontinue(item_id: UUID, actor: Users = requires(DISCONTINUE)):
    actor.username
    actor.dev
    await actor.can(PERMS.update)
```

En un endpoint `Scope.PUBLIC` no hay usuario: se escribe
`_public: None = requires(PUBLIC_LIST)`.

### Ejemplos

**Acción sobre un registro** (usa un método del modelo):

```python
@products_router.post("/{item_id}/discontinue", response_model=ProductOut)
async def discontinue(item_id: UUID, actor: Users = requires(DISCONTINUE)):
    product = await products.get(item_id)
    await product.discontinue()
    return await products.one(product)
```

**Acción con regla de negocio** (delega en un servicio):

```python
@products_router.post("/{item_id}/stock", response_model=ProductOut)
async def adjust_stock(item_id: UUID, data: StockChange, actor: Users = requires(STOCK)):
    product = await change_stock(await products.get(item_id), data.delta)
    return await products.one(product)
```

**Relación muchos a muchos**:

```python
@products_router.put("/{item_id}/tags", response_model=Message)
async def set_tags(item_id: UUID, data: TagsIn, actor: Users = requires(SET_TAGS)):
    product = await products.get(item_id)
    tags = await Tag.filter(id__in=data.tag_ids)
    await product.tags.clear()
    await product.tags.add(*tags)
    return Message(detail=f"{len(tags)} etiquetas asignadas")
```

**Listado paginado propio**:

```python
from fastapi_pagination import Page
from fastapi_pagination.ext.tortoise import apaginate


@categories_router.get("/{item_id}/products", response_model=Page[ProductOut])
async def category_products(item_id: UUID, actor: Users = requires(CATEGORY_PRODUCTS)):
    category = await categories.get(item_id)

    async def transform(items: Any) -> Any:
        return await products.serialize(list(items))

    return await apaginate(Product.filter(category_id=category.id), transformer=transform)
```

Responde `{"items": [...], "total": 42, "page": 1, "size": 50, "pages": 1}` y
acepta `?page=` y `?size=`.

**Endpoint público**:

```python
@products_router.get("/public", response_model=list[ProductOut])
async def public_catalog(_public: None = requires(PUBLIC_LIST)):
    return await products.serialize(await Product.filter(active=True).limit(50))
```

**Archivo (CSV) con una tarea en segundo plano**:

```python
@products_router.get("/export", response_class=Response)
async def export_products(background: BackgroundTasks, actor: Users = requires(EXPORT)):
    rows = await Product.all().order_by("sku")
    lines = ["sku,name,price"] + [f"{p.sku},{p.name},{p.price:.2f}" for p in rows]
    background.add_task(register_export, actor.username, len(rows))
    return Response("\n".join(lines), media_type="text/csv")
```

Las tareas de `BackgroundTasks` corren **después** de responder y con su propia
transacción: si fallan, la respuesta ya se envió.

---

## 6. Roles, permisos y otros usuarios

**Quien no es dev no puede conceder ni gestionar más permisos de los que tiene.**
Si lo intenta, la API responde `403 PRM_004`, con los permisos que le sobran en
`details.permissions`. El sistema lo aplica en sus propias rutas de usuarios y
roles; las tuyas tienen que hacerlo igual cuando:

- un `Resource` permite **elegir un rol** (`role_id`) o **guardar permisos**;
- un endpoint **actúa sobre otro usuario**: cambiarle el rol, cerrarle las
  sesiones, editar su cuenta...

Las comprobaciones son funciones de `app.core.services.users`. Cuándo usar cada
una y qué error da está en la tabla de `app/services/steps.md`, sección 8:
`check_role_assignable(actor, role_id)` para un rol, `check_can_grant(actor, ids)`
para una lista de permisos y `await protect_account(actor, target)` para otro
usuario (es `async`). Van **antes** de guardar, y un `dev` pasa todas.

Ejemplo: un equipo tiene un rol, y quien entra en el equipo lo recibe. El modelo
(`app/models/team.py`), que apunta al rol del sistema con `"models.Role"`:

```python
from typing import TYPE_CHECKING
from uuid import UUID

from tortoise import fields

from app.core.models.entity import Entity

if TYPE_CHECKING:
    from app.core.models.role import Role


class Team(Entity):
    name = fields.CharField(max_length=100, unique=True)
    role: fields.ForeignKeyNullableRelation[Role] = fields.ForeignKeyField(
        "models.Role", related_name="teams", null=True, on_delete=fields.SET_NULL
    )
    role_id: UUID | None

    audit_label_field = "name"

    class Meta(Entity.Meta):
        table = "teams"
```

Los esquemas (`app/schemas/team.py`):

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TeamCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    role_id: UUID | None = None


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    role_id: UUID | None = None


class TeamOut(BaseModel):
    id: UUID
    name: str
    role_id: UUID | None
    created_at: datetime
    deleted_at: datetime | None
```

El servicio `add_member` está en `app/services/steps.md`, sección 8. Y la ruta
(`app/routes/teams.py`): los hooks del `Resource` comprueban el rol que se elige, y
el endpoint delega en el servicio:

```python
from typing import Any
from uuid import UUID

from fastapi import APIRouter

from app.core.crud import Resource
from app.core.dependencies import requires
from app.core.errors import AppError, Err
from app.core.models.user import Users
from app.core.permissions import crud_permissions, permission
from app.core.schemas.common import Message
from app.core.services.users import check_role_assignable
from app.models.team import Team
from app.schemas.team import TeamCreate, TeamOut, TeamUpdate
from app.services.teams import add_member

GROUP = "Equipos"
TEAM_PERMS = crud_permissions(6200, "teams", GROUP, "equipos")
ADD_MEMBER = permission(6211, "teams.add_member", GROUP, "Añadir un usuario a un equipo")


class TeamsResource(Resource[Team]):
    model = Team
    create_schema = TeamCreate
    update_schema = TeamUpdate
    out_schema = TeamOut
    permissions = TEAM_PERMS
    search_fields = ("name",)
    ordering = ("name",)

    async def before_create(self, data: dict[str, Any], actor: Users) -> dict[str, Any]:
        await check_role_assignable(actor, data.get("role_id"))
        return data

    async def before_update(self, item: Team, data: dict[str, Any], actor: Users) -> dict[str, Any]:
        await check_role_assignable(actor, data.get("role_id"))
        return data


teams = TeamsResource()
router = APIRouter(prefix="/teams", tags=[GROUP])


@router.post("/{item_id}/members/{user_id}", response_model=Message)
async def add_team_member(item_id: UUID, user_id: UUID, actor: Users = requires(ADD_MEMBER)):
    """Añade un usuario al equipo: recibe el rol del equipo."""
    team = await teams.get(item_id)
    user = await Users.filter(id=user_id).first()
    if user is None:
        raise AppError(Err.USER_NOT_FOUND, details={"id": str(user_id)})
    await add_member(actor, team, user)
    return Message(detail=f"{user.username} añadido a {team.name}")


teams.mount(router)
```

Con un rol que solo tiene `teams.list`, `teams.create`, `teams.update` y
`teams.add_member`, el usuario responde así:

| Acción | Respuesta |
|---|---|
| Crea un equipo con su propio rol | `201` |
| Crea, o cambia, un equipo con un rol que tiene permisos que él no tiene | `403 PRM_004` |
| Añade a un usuario sin rol a un equipo cuyo rol cabe en el suyo | `200` |
| Añade a un usuario a un equipo con un rol mayor que el suyo | `403 PRM_004` |
| Añade a un usuario con más permisos que él | `403 PRM_004` |
| Añade a una cuenta dev | `403 USR_005` |

Si lo que guarda tu recurso es una **lista de ids de permiso** (una plantilla de
rol, por ejemplo), en `before_create` y `before_update` comprueba primero que los
ids existen y se pueden asignar (`unknown_permissions` de `app.core.permissions`,
como hace el recurso de roles del sistema) y después `await check_can_grant(actor,
ids)`.

---

## 7. Errores

Se lanza siempre `AppError`, nunca `HTTPException`:

```python
from app.core.errors import AppError, Err

raise AppError(Err.VALIDATION, fields={"stock": "No puede ser negativo"})
raise AppError(OUT_OF_STOCK, details={"sku": product.sku})
```

| Argumento | Para qué |
|---|---|
| `fields={"campo": "mensaje"}` | Error por campo de formulario |
| `details={...}` | Datos extra en la respuesta |
| `log_message="..."` | Texto para el log y la auditoría |
| `toast=False` | El frontend no muestra aviso |
| `persist=True` | Se guarda como evento en la auditoría |

Errores del sistema útiles: `Err.NOT_FOUND`, `Err.VALIDATION`, `Err.DUPLICATED`,
`Err.RELATED_NOT_FOUND`, `Err.PERMISSION_DENIED`, `Err.USER_NOT_FOUND`. Los
propios de tu proyecto se declaran en `app/errors/` y se listan en `ERRORS` de
`app/registry.py` (ver `app/errors/steps.md`).

Lo que **se convierte solo**:

| Excepción | Respuesta |
|---|---|
| `DoesNotExist` de Tortoise (`Model.get(...)`) | `404 SYS_404` |
| Valor único repetido en la base de datos | `409 SYS_409` |
| Clave foránea que impide borrar (`on_delete=NO_ACTION` o `RESTRICT`) | `409 SYS_REL` |
| Texto o valor que no cumple la columna o sus validadores | `422 VAL_422`, sin campo |
| Base de datos caída (o una columna que no existe) | `503 SYS_503` |
| Cualquier otra excepción | `500 SYS_500` y se guarda en la auditoría |

---

## 8. Transacciones y efectos

- **Toda escritura** (`POST`, `PUT`, `PATCH`, `DELETE`) protegida con `requires(...)`
  va dentro de una transacción: si la función falla, no se guarda nada, ni los
  cambios ni sus eventos de historial.
- `requires(PERMISO, atomic=False)` desactiva eso. Solo para rutas que deben
  guardar algo **aunque respondan con error** (el login anota cada intento antes
  de comprobar la contraseña). En ellas abre tus propias transacciones con
  `async with in_transaction():`.
- Los `GET` no abren transacción.

Para dejar constancia de algo que no es un cambio de una tabla (una exportación,
un envío de correo, un pago recibido):

```python
from app.core.models.event import EventAction
from app.core.services.event_log import record_security

await record_security(EventAction.SYSTEM, f"{actor.username} exportó 120 productos")
```

---

## 9. Repeticiones (idempotencia)

No hay que hacer nada: si el mismo usuario envía dos veces seguidas la misma
escritura (doble clic, reintento), la segunda recibe la respuesta de la primera
con la cabecera `Idempotent-Replayed: true` y **no se ejecuta otra vez**.

Para operaciones que se pueden reintentar horas después (un pago, una
importación), el cliente envía una cabecera `Idempotency-Key` con un identificador
único por operación. Cómo generarla y cuándo cambiarla en el frontend:
`frontend/src/core/idempotency.md`.

Consecuencia al **probar a mano**: dos peticiones idénticas seguidas desde la
misma sesión dan la misma respuesta. Para probar el caso repetido con datos
distintos, cámbialos o espera 10 s.

---

## 10. Ejemplo completo: `app/routes/catalog.py`

```python
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Query, Response
from fastapi_pagination import Page
from fastapi_pagination.ext.tortoise import apaginate

from app.core.crud import Resource
from app.core.dependencies import requires
from app.core.models.user import Users
from app.core.permissions import Scope, crud_permissions, permission
from app.core.schemas.common import Message
from app.errors.catalog import PRODUCT_NOT_FOUND
from app.models.category import Category
from app.models.product import Product
from app.models.tag import Tag
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate
from app.schemas.product import ProductCreate, ProductOut, ProductUpdate, StockChange, TagsIn
from app.services.catalog import change_stock, register_export

GROUP = "Catálogo"
CATEGORY_PERMS = crud_permissions(6000, "categories", GROUP, "categorías")
CATEGORY_PRODUCTS = permission(6011, "categories.products", GROUP, "Ver productos de una categoría")
PRODUCT_PERMS = crud_permissions(6100, "products", GROUP, "productos")
DISCONTINUE = permission(6111, "products.discontinue", GROUP, "Descatalogar un producto")
STOCK = permission(6112, "products.stock", GROUP, "Cambiar el stock de un producto")
SET_TAGS = permission(6113, "products.tags", GROUP, "Cambiar las etiquetas de un producto")
LOW_STOCK = permission(6114, "products.low_stock", GROUP, "Ver productos con poco stock")
EXPORT = permission(6115, "products.export", GROUP, "Exportar productos a CSV")
PUBLIC_LIST = permission(6116, "products.public", GROUP, "Catálogo público", Scope.PUBLIC)


class CategoriesResource(Resource[Category]):
    model = Category
    create_schema = CategoryCreate
    update_schema = CategoryUpdate
    out_schema = CategoryOut
    permissions = CATEGORY_PERMS
    search_fields = ("name",)
    sort_fields = ("name", "created_at")
    ordering = ("name",)


class ProductsResource(Resource[Product]):
    model = Product
    create_schema = ProductCreate
    update_schema = ProductUpdate
    out_schema = ProductOut
    permissions = PRODUCT_PERMS
    not_found = PRODUCT_NOT_FOUND
    search_fields = ("sku", "name")
    filter_fields = ("active", "category_id", "status")
    text_fields = ("name",)
    range_fields = ("price", "stock", "created_at")
    sort_fields = ("sku", "name", "price", "stock", "created_at")

    async def serialize(self, items: list[Product]) -> list[Any]:
        ids = {item.category_id for item in items}
        names = {row.id: row.name for row in await Category.with_deleted().filter(id__in=ids)}
        return [
            ProductOut.model_validate(item, from_attributes=True).model_copy(
                update={"category_name": names.get(item.category_id)}
            )
            for item in items
        ]


categories = CategoriesResource()
products = ProductsResource()
categories_router = APIRouter(prefix="/categories")
products_router = APIRouter(prefix="/products")


@products_router.get("/low-stock", response_model=list[ProductOut])
async def low_stock(limit: int = Query(5, ge=0), actor: Users = requires(LOW_STOCK)):
    """Productos activos con poco stock."""
    return await products.serialize(await Product.low_stock(limit))


@products_router.get("/export", response_class=Response)
async def export_products(background: BackgroundTasks, actor: Users = requires(EXPORT)):
    """CSV con todos los productos."""
    rows = await Product.all().order_by("sku")
    lines = ["sku,name,price"] + [f"{p.sku},{p.name},{p.price:.2f}" for p in rows]
    background.add_task(register_export, actor.username, len(rows))
    return Response("\n".join(lines), media_type="text/csv")


@products_router.get("/public", response_model=list[ProductOut])
async def public_catalog(_public: None = requires(PUBLIC_LIST)):
    """Productos activos, sin sesión."""
    return await products.serialize(await Product.filter(active=True).limit(50))


@products_router.post("/{item_id}/discontinue", response_model=ProductOut)
async def discontinue(item_id: UUID, actor: Users = requires(DISCONTINUE)):
    """Descataloga un producto."""
    product = await products.get(item_id)
    await product.discontinue()
    return await products.one(product)


@products_router.post("/{item_id}/stock", response_model=ProductOut)
async def adjust_stock(item_id: UUID, data: StockChange, actor: Users = requires(STOCK)):
    """Suma o resta stock."""
    product = await change_stock(await products.get(item_id), data.delta)
    return await products.one(product)


@products_router.put("/{item_id}/tags", response_model=Message)
async def set_tags(item_id: UUID, data: TagsIn, actor: Users = requires(SET_TAGS)):
    """Sustituye las etiquetas de un producto."""
    product = await products.get(item_id)
    tags = await Tag.filter(id__in=data.tag_ids)
    await product.tags.clear()
    await product.tags.add(*tags)
    return Message(detail=f"{len(tags)} etiquetas asignadas")


@categories_router.get("/{item_id}/products", response_model=Page[ProductOut])
async def category_products(item_id: UUID, actor: Users = requires(CATEGORY_PRODUCTS)):
    """Productos de una categoría, paginados."""
    category = await categories.get(item_id)

    async def transform(items: Any) -> Any:
        return await products.serialize(list(items))

    return await apaginate(Product.filter(category_id=category.id), transformer=transform)


products.mount(products_router)
categories.mount(categories_router)

router = APIRouter(tags=[GROUP])
router.include_router(categories_router)
router.include_router(products_router)
```

Si el archivo tiene **un solo recurso**, basta un router:

```python
router = APIRouter(prefix="/categories", tags=["Catálogo"])
categories.mount(router)
```

Y así queda `app/registry.py` con todo lo del catálogo: los tres modelos, el
router y los dos errores (los middlewares, en `app/middlewares/steps.md`). Los
errores se importan con un alias, porque `catalog` ya es el nombre de las rutas:

```python
from types import ModuleType

from fastapi import APIRouter
from starlette.middleware import Middleware

from app.core.errors import ErrorSpec
from app.errors import catalog as catalog_errors
from app.models import category, product, tag
from app.routes import catalog

MODELS: list[ModuleType] = [category, product, tag]
ROUTERS: list[APIRouter] = [catalog.router]
MIDDLEWARES: list[Middleware] = []
ERRORS: list[ErrorSpec] = [catalog_errors.PRODUCT_NOT_FOUND, catalog_errors.OUT_OF_STOCK]
```

---

## 11. Después de escribir la ruta

1. Registra lo que falte en `app/registry.py`: el `router` en `ROUTERS`, los
   módulos de modelos nuevos en `MODELS` y los errores propios en `ERRORS`.
2. **La tabla del modelo nuevo.** Mientras el proyecto no tenga `backend/migrations/`,
   al reiniciar el servidor la crea sola. Con migraciones **no**: el esquema es de
   aerich, y hasta que lo aplicas el endpoint falla con `503 SYS_503` (la tabla o
   la columna no existe):

   ```bash
   cd backend && uv run aerich migrate --name catalogo
   cd backend && uv run aerich upgrade
   ```

   Revisa el archivo que genera `migrate` en `backend/migrations/` antes del
   `upgrade` (`GUIA.md`, sección 5).
3. Guarda el archivo: `fastapi dev` recarga solo. Al arrancar comprueba todos los
   permisos y, si el proyecto tiene migraciones, que la base las haya recibido; si
   algo falta o se repite, el error dice qué ruta.
4. Abre <http://127.0.0.1:8000/docs> (solo con `DEBUG=true`) y prueba el endpoint.
   Cada endpoint muestra su resumen en español (la descripción de su permiso) y,
   debajo, la clave del permiso, su id y a quién deja entrar. Un listado de
   `Resource` muestra además todos sus parámetros de filtro y orden.
5. **Da los permisos nuevos a los roles** en la página **Roles**. Los roles que
   ya existían no los reciben solos: es a propósito, para que nadie gane acceso
   sin que alguien lo decida. Un usuario `dev` siempre los tiene, y quien no es
   dev solo puede marcar en un rol permisos que él mismo tiene (sección 6).
6. Si hay pantalla, crea el cliente en `frontend/src/modules/` y la página en
   `frontend/src/pages/` (ver `GUIA.md`).

### Probar un endpoint

No hay pruebas unitarias: se prueba a mano desde `/docs` y, para lo de siempre, con `backend/checks/` (ver su `README.md`).
Inicia sesión allí con `POST /api/auth/login` y las siguientes llamadas usarán la
cookie de sesión. Revisa, como mínimo:

- El camino feliz de cada endpoint y sus errores: `422` con `fields`, `404`, `409`.
- Los permisos: con un usuario cuyo rol no tenga el permiso, el endpoint debe
  responder `403` con el código `PRM_001`. Con un endpoint `Scope.DEV`, `PRM_002`.
  Sin sesión, `401` con `AUT_002`.
- El historial: cada escritura debe dejar su evento en la página **Auditoría**.

---

## 12. Errores frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| El servidor no arranca: `no declara permiso` | Falta `requires(...)` en un endpoint | Añade `actor: Users = requires(PERMISO)` |
| El servidor no arranca: `declara varios permisos` | Un endpoint con dos `requires(...)` | Deja uno solo |
| El servidor no arranca: `ya lo usa` o `ya existe` | Dos permisos con el mismo id o clave | Usa otro número dentro de tu bloque |
| El servidor no arranca: `que ya usa` | Dos endpoints usan el mismo permiso | Un permiso distinto para cada endpoint |
| El servidor no arranca: `No se encontró ningún endpoint con permiso` | La comprobación de permisos lee la estructura interna de las rutas de FastAPI y una actualización la cambió | Vuelve a la versión de `fastapi` de `uv.lock` (`uv sync`) hasta adaptar `core/permissions.py` |
| El servidor no arranca: `ProductsResource.sort_fields: 'x' debe ser una columna de ... y un campo de ...` (o en `filter_fields`, `text_fields`, `range_fields`) | El nombre no es una columna del modelo o no está en `out_schema`; un campo calculado en `serialize` tampoco vale | Corrige el nombre o añade el campo a `out_schema`; para un campo calculado, un endpoint propio |
| El servidor no arranca: `range_fields: 'x' no es un número ni una fecha` | `range_fields` solo admite `int`, `float`, `Decimal`, `date` y `datetime` | Usa `filter_fields` o `text_fields` |
| `422 VAL_422` con `fields.sort`: `Columnas permitidas (máximo 4): ...` | Ordenas por una columna que no está en `sort_fields`, o por más de 4 | Añádela a `sort_fields` (si es columna del modelo) u ordena por otra |
| `422 VAL_422` en `created_at_from` o `_to`: `La fecha necesita zona horaria` | Fecha o hora sin zona | `2026-01-01T00:00:00Z` (un `+` se escribe `%2B`) |
| `422 VAL_422` en `<campo>_to`: `Debe ser igual o posterior al inicio` | `<campo>_from` es posterior a `<campo>_to` | Invierte los extremos |
| Un filtro no hace nada y no da error | El recurso no declara ese parámetro, o está mal escrito: se ignora | Decláralo en `filter_fields`, `text_fields` o `range_fields` y compara el nombre con `/docs` |
| Al paginar con el orden por defecto se repiten o faltan filas | `ordering` por una columna que puede repetirse, sin desempate | Termina `ordering` con `"id"`; con `?sort=` ya se añade solo |
| Los endpoints nuevos no existen (`404`) | El `router` no está en `ROUTERS` de `app/registry.py` | Añádelo a la lista |
| `503 SYS_503` en un endpoint nuevo, con la tabla o la columna sin crear | El proyecto tiene migraciones y no se aplicó la del modelo nuevo | `uv run aerich migrate --name x` y `uv run aerich upgrade` (sección 11) |
| `404 SYS_404` al llamar a un endpoint que sí existe | Barra final de más o de menos (`/api/products` en vez de `/api/products/`) | La colección con barra; el resto sin ella (sección 5) |
| `422 VAL_422` al llamar a `/products/low-stock` | El endpoint está declarado **después** de `mount()` | Muévelo antes |
| `403 PRM_001` con un usuario con rol | El rol no tiene el permiso | Márcalo en **Roles** |
| `403 PRM_002` | El endpoint es `Scope.DEV` | Solo lo usa un dev |
| `403 PRM_004` al asignar un rol o permisos | El usuario no es dev y no tiene alguno de esos permisos | Es lo esperado (sección 6): lo asigna quien los tenga, o un dev |
| `403 USR_005` al actuar sobre una cuenta | La cuenta es dev y el usuario no | Lo hace un dev |
| El mismo POST devuelve lo mismo y no crea otro registro | Idempotencia | Cambia los datos o espera 10 s |
| Un cambio no queda guardado aunque la función llegó al final | Falló algo después y la transacción se deshizo | Busca el error por su `request_id` |
