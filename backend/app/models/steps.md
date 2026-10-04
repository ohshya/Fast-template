# Modelos (`app/models/`)

Aquí van las tablas de tu proyecto. Nada se carga solo: cada archivo con modelos
se registra a mano en la lista `MODELS` de `app/registry.py` (sección 1). Un
archivo que no esté en la lista no crea tabla.

Los modelos del sistema (usuarios, roles, sesiones, eventos) viven en
`app/core/models/` y no se tocan. `app/core/registry.py` es el registro del
sistema y tampoco se edita.

La base de datos es PostgreSQL y los modelos usan sus tipos nativos (listas,
`jsonb`, `timestamptz`).

Ejemplos de esta guía: un catálogo con `Category`, `Product` y `Tag`. Todo lo
que aparece aquí se comprobó contra el código real, sobre PostgreSQL.

---

## 1. Crear un modelo en seis pasos

1. Crea `app/models/category.py`.
2. Haz que el modelo herede de `Entity`.
3. Declara sus campos.
4. Añade `class Meta(Entity.Meta)` con el nombre de la tabla.
5. Regístralo en `app/registry.py`.
6. Crea la tabla. Si el proyecto **no tiene** `backend/migrations/`, reinicia el
   servidor: al arrancar crea la tabla si no existe. Si **la tiene**, el servidor
   no crea nada: lanza `uv run aerich migrate --name <cambio>` y después
   `uv run aerich upgrade` (sección 9).

```python
from tortoise import fields

from app.core.models.entity import Entity


class Category(Entity):
    name = fields.CharField(max_length=100, unique=True)

    audit_label_field = "name"

    class Meta(Entity.Meta):
        table = "categories"
```

Con esto ya tienes historial de cambios, borrado reversible, autoría y un
identificador UUIDv7. Falta el esquema y la ruta: ver `app/schemas/steps.md` y
`app/routes/steps.md`.

### Registrar los modelos

En `app/registry.py`, importa el módulo y añádelo a `MODELS`. La lista es de
**módulos** (archivos), no de clases: un archivo puede traer varios modelos.

```python
from app.models import category, product, tag

MODELS: list[ModuleType] = [category, product, tag]
```

En ese archivo conviven los imports de todas las carpetas (`app/models/`,
`app/routes/`, `app/errors/`...). Si dos tienen el mismo nombre de archivo, el
segundo `import` pisaría al primero: importa con un alias que diga de dónde viene,
por ejemplo `from app.models import catalog as catalog_models`.

Reglas que no se negocian:

- **El nombre de la clase es único en todo el proyecto.** Tortoise registra los
  modelos por nombre de clase (`"models.Category"`), no por archivo. Si dos clases
  se llaman igual no hay ningún error al arrancar: solo se crea la tabla de una de
  las dos (ver sección 10).
- **`class Meta(Entity.Meta)`** siempre, con `table` propio. No uses
  `class Meta:` a secas.
- **Nunca importes rutas ni servicios** en un modelo. Un modelo solo conoce a
  otros modelos.
- **Todo modelo al que otro apunte (`"models.Tag"`) tiene que estar registrado.**
  Si falta su módulo en `MODELS`, Tortoise no arranca.

---

## 2. Qué te da `Entity`

| Campo | Qué es |
|---|---|
| `id` | UUIDv7. Lleva la fecha de creación escrita dentro y ordena por tiempo |
| `created_at`, `updated_at` | Fechas con zona horaria (UTC) |
| `created_by_id`, `updated_by_id` | Usuario que creó y que editó por última vez |
| `deleted_at`, `deleted_by_id` | Marca de borrado reversible y quién lo hizo |

Además:

- **Historial automático.** Cada `save()` guarda un evento con el cambio
  campo por campo (ver sección 6).
- **Borrado reversible.** `Product.all()`, `Product.filter(...)`, `get(...)` y las
  relaciones **no ven** los registros eliminados. `Product.with_deleted()` sí.
- **`item.delete()` está prohibido** y lanza un error a propósito. Se usa
  `soft_delete()` o `hard_delete()` (sección 7).

No declares en tu modelo ninguno de esos campos: ya existen.

---

## 3. Tipos de campo

Todos vienen de `tortoise.fields`, salvo `ArrayField`. Ejemplo con uno de cada tipo:

```python
from decimal import Decimal
from enum import IntEnum, StrEnum

from tortoise import fields
from tortoise.contrib.postgres.fields import ArrayField
from tortoise.validators import MinValueValidator

from app.core.models.entity import Entity


class ProductStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DISCONTINUED = "discontinued"


class Priority(IntEnum):
    LOW = 1
    NORMAL = 2
    HIGH = 3


class Product(Entity):
    sku = fields.CharField(max_length=40, unique=True)
    name = fields.CharField(max_length=150, db_index=True)
    description = fields.TextField(default="")
    price = fields.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    weight = fields.FloatField(null=True)
    stock = fields.IntField(default=0)
    views = fields.BigIntField(default=0)
    rating = fields.SmallIntField(null=True)
    active = fields.BooleanField(default=True)
    launched_on = fields.DateField(null=True)
    opens_at = fields.TimeField(null=True)
    published_at = fields.DatetimeField(null=True)
    warranty = fields.TimeDeltaField(null=True)
    external_id = fields.UUIDField(null=True)
    attributes: dict[str, str] = fields.JSONField(default=dict)
    sizes: list[int] = ArrayField(element_type="int", default=list)
    image = fields.BinaryField(null=True)
    status = fields.CharEnumField(ProductStatus, default=ProductStatus.DRAFT)
    priority = fields.IntEnumField(Priority, default=Priority.NORMAL)
```

| Campo | Python | En PostgreSQL y notas |
|---|---|---|
| `CharField(max_length=n)` | `str` | `varchar(n)`. Tortoise exige `max_length`; ponle el mismo tope en el esquema (`app/schemas/steps.md`). Lo que no cabe se rechaza al guardar |
| `TextField` | `str` | `text`. Texto largo sin límite |
| `IntField`, `SmallIntField`, `BigIntField` | `int` | `int4`, `int2` e `int8` |
| `FloatField` | `float` | `float8`. Para dinero usa `DecimalField` |
| `DecimalField(max_digits, decimal_places)` | `Decimal` | `numeric(p, s)`. Ver nota abajo |
| `BooleanField` | `bool` | |
| `DateField` | `date` | |
| `TimeField` | `time` | `timetz`. Se lee con zona horaria UTC |
| `DatetimeField` | `datetime` | `timestamptz`. Siempre con zona horaria (UTC). Nunca guardes fechas sin ella |
| `TimeDeltaField` | `timedelta` | Duraciones. Se guardan como un número (`int8`, microsegundos) |
| `UUIDField` | `UUID` | `uuid` |
| `JSONField` | `dict` o `list` | `jsonb`. Anótalo (`attributes: dict[str, str] = ...`) para que el tipado lo entienda |
| `ArrayField(element_type="int")` | `list[int]` | Lista nativa de PostgreSQL (`int4[]`). Ver abajo |
| `BinaryField` | `bytes` | `bytea`. Evita guardar archivos grandes en la base de datos |
| `CharEnumField(Enum)` | el enum | Guarda el valor como texto |
| `IntEnumField(Enum)` | el enum | Guarda el valor como número |

**Nota sobre `DecimalField`.** Tortoise normaliza el decimal de un objeto que
construye con valores (`Product.create(price=Decimal("20.00"))`, `Product(...)`,
`get_or_create`): `Decimal("20.00")` queda como `Decimal("2E+1")`. Es el mismo
número, pero si lo conviertes a texto sale `2E+1`. El que se lee de la base de
datos (`get`, `filter`) conserva sus decimales (`Decimal("20.00")`). Para mostrarlo
o exportarlo, formatea: `f"{product.price:.2f}"`. En los esquemas de salida usa
`PlainDecimal` (`app/schemas/steps.md`). El historial ya lo normaliza y no genera
cambios falsos.

### Listas de valores: `ArrayField`

Una columna que guarda varios valores del mismo tipo, sin tabla intermedia. Se
importa de `tortoise.contrib.postgres.fields` y se anota con su tipo de lista
(así están los permisos de un rol: `permissions: list[int] = ArrayField(...)`).
`element_type` es el tipo de PostgreSQL de cada elemento (`"int"`, `"text"`...):

```python
sizes: list[int] = ArrayField(element_type="int", default=list)
```

Se asigna y se lee como una lista normal (`product.sizes = [38, 40]`) y tiene sus
propios filtros:

| Filtro | Ejemplo |
|---|---|
| Contiene todos | `Product.filter(sizes__contains=[38])` |
| Contenida en | `Product.filter(sizes__contained_by=[38, 40, 42, 44])` |
| Comparte alguno | `Product.filter(sizes__overlap=[40, 99])` |
| Longitud | `Product.filter(sizes__len=3)` |

Si lo que guardas son referencias a otros registros, usa una relación (sección 4):
una lista de ids no comprueba que existan.

### Opciones que aceptan todos los campos

| Opción | Para qué |
|---|---|
| `null=True` | Admite `NULL` |
| `default=valor` o `default=función` | Valor inicial (`default=0`, `default=dict`, `default=uuid7`) |
| `unique=True` | Valor único, **contando también los eliminados** |
| `db_index=True` | Índice para buscar más rápido |
| `description="..."` | Comentario de la columna |
| `validators=[...]` | Se ejecutan al guardar (`MinValueValidator`, `MaxValueValidator`, `MinLengthValidator`, `RegexValidator`, `EmailValidator`...). Si fallan, lanzan `ValidationError` |
| `source_field="nombre_columna"` | Nombre distinto en la base de datos |

Un campo sin `null=True` ni `default` es obligatorio: `Product.create(...)` falla
si no lo recibe.

---

## 4. Relaciones entre modelos

Una relación se declara con **el nombre de la clase del otro modelo**, con el
prefijo `models.`: `"models.Category"`. Como los modelos están en archivos
distintos, el tipo se importa solo para el verificador de tipos:

```python
from typing import TYPE_CHECKING
from uuid import UUID

from tortoise import fields

from app.core.models.entity import Entity

if TYPE_CHECKING:
    from app.core.models.user import Users
    from app.models.category import Category
    from app.models.tag import Tag
```

El otro modelo tiene que estar también en `MODELS` (sección 1).

### 4.1 Muchos a uno (`ForeignKeyField`)

Varios productos pertenecen a una categoría. Se escriben **tres cosas**:

```python
category: fields.ForeignKeyRelation[Category] = fields.ForeignKeyField(
    "models.Category", related_name="products", on_delete=fields.NO_ACTION
)
category_id: UUID
```

1. `category`: la relación.
2. `category_id: UUID`: la anotación del valor guardado. Sin ella el verificador
   de tipos no conoce `product.category_id` y `Resource` no reconoce la clave.
3. `related_name="products"`: crea `category.products` en el otro lado.

En el otro modelo, la relación inversa se anota (no se declara con `fields.`):

```python
class Category(Entity):
    products: fields.ReverseRelation[Product]
```

Relación opcional: `ForeignKeyNullableRelation`, `null=True` y el `_id` con `| None`:

```python
owner: fields.ForeignKeyNullableRelation[Users] = fields.ForeignKeyField(
    "models.Users", related_name="products", null=True, on_delete=fields.SET_NULL
)
owner_id: UUID | None
```

Para relacionarte con los usuarios o los roles del sistema usa
`"models.Users"` y `"models.Role"`.

**`on_delete`** decide qué pasa con estos registros cuando se borra **de verdad**
el registro al que apuntan (`hard_delete`):

| Valor | Efecto |
|---|---|
| `fields.CASCADE` | Se borran también |
| `fields.NO_ACTION` | Se impide el borrado mientras quede alguno. La API responde `409 SYS_REL` |
| `fields.RESTRICT` | Lo mismo (PostgreSQL lo señala con otro código, `23001`, y la API también lo traduce a `409 SYS_REL`) |
| `fields.SET_NULL` | Quedan con la relación en `NULL` (exige `null=True`) |
| `fields.SET_DEFAULT` | Toman el valor por defecto |

El borrado reversible (`soft_delete`) **no dispara `on_delete`**: la fila sigue
existiendo. Por eso `NO_ACTION` casi nunca molesta en el día a día.

### 4.2 Uno a uno (`OneToOneField`)

Cada sección tiene como máximo un responsable, y cada usuario responde de una:

```python
manager: fields.OneToOneNullableRelation[Users] = fields.OneToOneField(
    "models.Users", related_name="managed_section", null=True, on_delete=fields.SET_NULL
)
manager_id: UUID | None
```

Sin nulos: `OneToOneRelation[...]`. Desde el usuario: `user.managed_section`.

### 4.3 Muchos a muchos (`ManyToManyField`)

Un producto tiene varias etiquetas y una etiqueta varios productos. Se declara
**en un solo lado** y Tortoise crea la tabla intermedia (con migraciones, la crea
la migración que genera `aerich migrate`, como el resto de tablas):

```python
tags: fields.ManyToManyRelation[Tag] = fields.ManyToManyField(
    "models.Tag", related_name="products", through="product_tags"
)
```

```python
class Tag(Entity):
    products: fields.ManyToManyRelation[Product]
```

```python
await product.tags.add(tag_a, tag_b)
await product.tags.remove(tag_a)
await product.tags.clear()
await product.tags.all()
await Product.filter(tags__name="oferta")
```

**Importante:** añadir o quitar en una relación muchos a muchos **no deja
historial**, porque no se guarda ninguna entidad. Si te interesa auditarlo,
registra el evento a mano con `record_security(...)` (ver `app/services/steps.md`).

### 4.4 Relación consigo mismo (árboles)

```python
parent: fields.ForeignKeyNullableRelation["Section"] = fields.ForeignKeyField(
    "models.Section", related_name="children", null=True, on_delete=fields.SET_NULL
)
parent_id: UUID | None
children: fields.ReverseRelation["Section"]
```

### 4.5 Leer y filtrar por relaciones

```python
await category.products.all()  # productos vivos de la categoría
await category.products.filter(stock__gt=5)
await Product.filter(category__name="Ropa")  # filtra atravesando la relación
await Product.filter(tags__name="oferta")
await Product.all().prefetch_related("tags")  # carga las etiquetas de golpe
await Product.all().select_related("category")  # carga la categoría con un JOIN
await Product.filter(sku="A1").values("sku", "category__name")
```

- **Leer** una relación (`category.products.all()`, `product.tags.all()`,
  `prefetch_related`) **no devuelve** registros eliminados.
- **Filtrar atravesando** una relación (`Product.filter(category__name="Ropa")`) no
  mira si el registro del otro lado está eliminado: devuelve el producto igual.
- `select_related` trae la categoría aunque esté eliminada.
- Para leer una clave foránea suelta, consulta el modelo con el `_id`
  (`await Category.get_or_none(id=product.category_id)`) o usa `select_related`.
  Evita `await product.category`: el verificador de tipos no lo entiende bien.

---

## 5. `class Meta`

```python
class Meta(Entity.Meta):
    table = "products"
    ordering = ["name"]
    unique_together = (("category", "name"),)
    indexes = (("status", "priority"),)
    table_description = "Productos del catálogo"
```

| Opción | Para qué |
|---|---|
| `table` | Nombre de la tabla. Obligatorio |
| `ordering` | Orden por defecto de las consultas. `"-campo"` es descendente. El listado de un `Resource` no lo usa: manda el `ordering` del recurso (`app/routes/steps.md`, sección 3) |
| `unique_together` | Combinaciones únicas. Se usa el nombre de la relación (`"category"`) |
| `indexes` | Índices compuestos |
| `table_description` | Comentario de la tabla |
| `abstract = True` | El modelo no crea tabla: es una base para otros |

`unique_together` lo comprueba la base de datos, no `Resource`: si se repite, la
API responde `409 SYS_409` **sin** indicar campo. Los campos con `unique=True`
sí los comprueba `Resource` y devuelven el campo en `fields`.

### Modelo base compartido

```python
class Named(Entity):
    name = fields.CharField(max_length=80)

    audit_label_field = "name"

    class Meta(Entity.Meta):
        abstract = True


class Section(Named):
    class Meta(Named.Meta):
        table = "sections"
```

Los campos y atributos del modelo abstracto pasan a los que heredan de él. Un
archivo que solo tenga modelos abstractos no va en `MODELS` (Tortoise avisaría de
que no tiene modelos): registra el archivo de los modelos que heredan de él.

---

## 6. Historial: atributos de auditoría

Se declaran dentro de la clase, junto a los campos:

```python
class ApiKey(Entity):
    name = fields.CharField(max_length=80)
    secret = fields.CharField(max_length=200)
    last_used_at = fields.DatetimeField(null=True)

    audit_label_field = "name"
    audit_redact = frozenset({"secret"})
    audit_ignore = frozenset({"last_used_at"})

    class Meta(Entity.Meta):
        table = "api_keys"
```

| Atributo | Para qué |
|---|---|
| `audit = False` | La tabla no guarda historial (tablas muy volátiles, registros técnicos) |
| `audit_label_field = "name"` | Campo que da nombre legible al registro en los eventos |
| `audit_redact = frozenset({...})` | Campos secretos: no se guarda su valor, solo una huella (HMAC con `SECRET_KEY`) que dice que cambió |
| `audit_ignore = frozenset({...})` | Campos que no generan evento al cambiar (contadores, marcas de uso) |

Qué queda registrado: quién, cuándo, qué endpoint, y por cada campo el valor
anterior y el nuevo. Se consulta en la página **Auditoría** o en
`GET /api/events/history/<tabla>/<id>`.

Cómo se guarda:

- **Cada `save()` es atómico.** La fila y su evento se escriben en una misma
  transacción, también fuera de una ruta (un script, una tarea en segundo plano).
  Si el evento no se puede escribir, la fila tampoco se guarda: no existe un
  cambio sin historial.
- **`save(update_fields=[...])`** guarda solo esas columnas, sella `updated_at` y
  `updated_by_id` sin que los pidas, y el historial compara únicamente lo que se
  guardó. Un cambio hecho en memoria y no guardado no aparece.
- Cada `save()` de una fila existente hace un `SELECT` previo para calcular el
  cambio. En una tabla de mucho volumen que no necesite historial, usa
  `audit = False`.

**Cuándo NO hay historial** (porque no pasa por `save()`):

| Operación | ¿Deja evento? |
|---|---|
| `item.save()`, `Model.create(...)`, `get_or_create`, `update_or_create` | Sí |
| `item.soft_delete()`, `item.restore()`, `item.hard_delete()` | Sí |
| `Model.filter(...).update(...)` | **No** |
| `Model.filter(...).delete()` | **No** |
| `Model.bulk_create([...])` | **No** |
| `item.relacion.add(...)` en muchos a muchos | **No** |

En tablas auditadas trabaja siempre con el objeto (`item.save()`).
Los `update()` con expresiones (`F("stock") - 1`) son útiles para contadores
atómicos, pero no dejan historial: úsalos solo donde no importe.

---

## 7. Métodos del modelo

### Los que trae `Entity`

| Método | Qué hace |
|---|---|
| `await item.soft_delete()` | Elimina de forma reversible y anota quién |
| `await item.restore()` | Restaura un eliminado |
| `await item.hard_delete()` | Borra la fila de verdad (deja evento). Solo para casos justificados |
| `item.delete()` | **Prohibido**: lanza `RuntimeError` |
| `item.is_deleted` | `True` si está eliminado |
| `Model.with_deleted()` | Consulta que incluye eliminados |
| `Model.entity_name()` | Nombre de la tabla, el que usa el historial |
| `item.audit_label()` | Nombre legible del registro |

### Los tuyos

Pon en el modelo la lógica que solo depende de sus propios datos:

```python
class Product(Entity):
    ...

    @property
    def in_stock(self) -> bool:
        return self.stock > 0

    def discounted(self, percent: Decimal) -> Decimal:
        return self.price * (100 - percent) / 100

    async def discontinue(self) -> None:
        self.status = ProductStatus.DISCONTINUED
        self.active = False
        await self.save()

    @classmethod
    async def low_stock(cls, limit: int = 5) -> list[Self]:
        return await cls.filter(stock__lte=limit, active=True).order_by("stock")
```

En un `classmethod` el tipo de retorno es `Self` (`from typing import Self`), no el
nombre de la clase: así el verificador de tipos acepta también los modelos que
hereden de este.

La regla para decidir dónde va la lógica:

- Depende solo del registro y no llama a otros modelos: **método del modelo**.
- Une varios modelos, llama a servicios externos o decide un flujo:
  **servicio** (`app/services/`).
- Es un paso de una petición HTTP: **ruta** (`app/routes/`).

---

## 8. Usar el modelo desde fuera del archivo

Los ejemplos valen para servicios, rutas y scripts. Siempre con `await`.

### Crear

```python
product = await Product.create(sku="A1", name="Camisa", price=Decimal("19.90"), category_id=cat.id)

product = Product(sku="A2", name="Pantalón", price=Decimal("29.90"), category_id=cat.id)
await product.save()

product, created = await Product.get_or_create(
    sku="A3", defaults={"name": "Gorra", "price": 5, "category_id": cat.id}
)
product, created = await Product.update_or_create(sku="A3", defaults={"stock": 10})
```

`Model.create(...)` ignora en silencio los argumentos que no son campos del modelo:
si el nombre está mal escrito, el dato simplemente no se guarda.

### Leer

```python
await Product.get(id=product_id)  # lanza DoesNotExist si no existe (la API responde 404)
await Product.get_or_none(sku="A1")  # None si no existe
await Product.filter(active=True)  # lista
await Product.all()  # todos los vivos, en el orden de Meta.ordering
await Product.filter(name="Beta").first()  # el primero o None
await Product.with_deleted().filter(...)  # incluye eliminados
await Product.filter(sku="A1").exists()  # bool
await Product.filter(active=True).count()  # int
```

### Filtros

| Filtro | Ejemplo |
|---|---|
| Igual | `filter(status="active")` |
| Mayor, menor | `price__gt=10`, `price__gte=10`, `price__lt=50`, `price__lte=50` |
| Texto | `name__icontains="cam"`, `name__startswith="Ca"`, `name__endswith="sa"`, `name__iexact="camisa"` |
| En lista | `sku__in=["A1", "A2"]` |
| Nulo | `owner_id__isnull=True` |
| Rango | `price__range=(10, 50)` |
| Excluir | `.exclude(name="Alfa")` |
| O / combinados | `filter(Q(name="Alfa") \| Q(stock__gt=8))` con `from tortoise.expressions import Q` |
| Por relación | `category__name="Ropa"`, `tags__name="oferta"` |
| Sobre una lista (`ArrayField`) | `sizes__contains=[38]`, `sizes__overlap=[40, 41]` (sección 3) |

### Ordenar, paginar, elegir columnas

```python
await Product.all().order_by("-created_at", "name")
await Product.all().offset(20).limit(10)
await Product.filter(active=True).only("id", "sku")
await Product.filter(active=True).values("sku", "price")  # lista de diccionarios
await Product.all().values_list("sku", flat=True)  # lista de valores
```

### Agregados

```python
from tortoise.functions import Avg, Count, Max, Sum

await Product.annotate(n=Count("id"), total=Sum("price")).values("n", "total")
await Product.annotate(n=Count("id")).group_by("category_id").values("category_id", "n")
```

### Actualizar

```python
product.stock = 7
await product.save()  # deja historial
await product.save(update_fields=["stock"])  # solo esa columna, también con historial

from tortoise.expressions import F

await Product.filter(sku="A1").update(stock=F("stock") - 1)  # atómico, SIN historial
```

### Eliminar y restaurar

```python
await product.soft_delete()
await product.restore()
deleted = await Product.with_deleted().filter(deleted_at__isnull=False)
```

### Transacciones

Las rutas de escritura (`POST`, `PUT`, `PATCH`, `DELETE`) ya van dentro de una
transacción. Fuera de ellas (scripts, tareas en segundo plano):

```python
from tortoise.transactions import in_transaction

async with in_transaction():
    await Category.create(name="A")
    await Category.create(name="B")  # si algo falla, se deshace todo, eventos incluidos
```

---

## 9. Después de crear o cambiar un modelo

1. **Registro.** Comprueba que el módulo está en `MODELS` de `app/registry.py`.
2. **Esquema y ruta.** Sin ellos el modelo no tiene API: ver
   `app/schemas/steps.md` y `app/routes/steps.md`.
3. **Tablas.** Depende de si el proyecto tiene `backend/migrations/`:
   - **Sin migraciones** (la plantilla recién clonada): al arrancar, Tortoise crea
     las tablas que falten, pero no modifica las que ya existen: una columna nueva
     en una tabla existente necesita una migración con aerich. En desarrollo, si
     los datos no importan, también puedes borrar la tabla afectada (o la base de
     datos entera) y volver a crear tu usuario con `create_admin`.
   - **Con migraciones**: el esquema es de aerich y el servidor **no crea ni
     altera nada** (ni una tabla nueva, ni una columna). Cada cambio en los modelos
     necesita su migración, y sin aplicarla el servidor no la ve:

     ```bash
     cd backend && uv run aerich migrate --name productos
     cd backend && uv run aerich upgrade
     ```

   Para empezar a usar migraciones hay que lanzar una sola vez, antes del primer
   `migrate`, `uv run aerich init-migrations` y `uv run aerich upgrade`. Las
   migraciones se guardan con el proyecto. Los casos que dan guerra (una columna
   obligatoria en una tabla con datos, renombrar o quitar un campo, una base nueva)
   están en `GUIA.md`, en "Base de datos y migraciones".

---

## 10. Errores frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| No hay error al arrancar, pero una tabla no existe | Dos clases con el mismo nombre en archivos distintos: Tortoise se queda con una | Nombres de clase únicos en todo el proyecto |
| `ConfigurationError: No model with name 'X' registered in app 'models'` | La relación apunta a un nombre que no existe: errata, o el módulo de ese modelo no está en `MODELS` | Escribe `"models.<NombreDeLaClase>"` (no el de la tabla) y registra el módulo |
| `ModuleNotFoundError` al arrancar | Un import de `app/registry.py` apunta a un archivo que no existe | Corrige el nombre del módulo |
| `RuntimeWarning: Module "..." has no models` | Metiste en `MODELS` un archivo sin modelos | Quítalo de la lista |
| El modelo no crea tabla | Su módulo no está en `MODELS` de `app/registry.py`, o el proyecto tiene migraciones y no aplicaste la del modelo | Añádelo; con migraciones, `aerich migrate` y `aerich upgrade` (sección 9) |
| La columna nueva no existe (`column "x" does not exist`; la API responde `503 SYS_503`) | La tabla ya existía (el arranque no altera tablas) o el proyecto tiene migraciones y falta aplicarla | Migración con aerich (sección 9) |
| El servidor (o `create_admin`) no arranca: `Este proyecto tiene migraciones y esta base no las ha recibido` | Con `backend/migrations/` el servidor no crea tablas, y esta base es nueva | `cd backend && uv run aerich upgrade` |
| `RuntimeError: usa soft_delete()` | Se llamó a `item.delete()` | Usa `soft_delete()` o `hard_delete()` |
| `409 SYS_REL` al borrar de verdad | Hay registros que apuntan a este (`on_delete=NO_ACTION` o `RESTRICT`) | Bórralos antes o cambia el `on_delete` |
| `422 VAL_422` sin campo al guardar un texto | El texto no cabe en la columna (`max_length`) | Pon el mismo `max_length` en el esquema: así el error llega con su campo |
| Un cambio no aparece en el historial | Se hizo con `update()`, `bulk_create()` o en muchos a muchos | Usa el objeto y `save()` |
| Se guardó `2E+1` en un CSV | `DecimalField` normalizado en un objeto recién creado | Formatea con `f"{valor:.2f}"` |
| `NameError` por un modelo en una anotación | Falta el `import` bajo `TYPE_CHECKING` | Añádelo (sección 4) |
