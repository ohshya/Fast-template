# Esquemas (`app/schemas/`)

Un esquema define la forma exacta de lo que **entra** y **sale** de la API:
qué campos, de qué tipo y con qué reglas. Son modelos de Pydantic.

- Un esquema **no es un modelo de base de datos**. El modelo (`app/models/`)
  describe la tabla; el esquema describe el JSON.
- Esta carpeta **no se registra en ningún sitio**: los esquemas los importan las
  rutas.
- Los esquemas del sistema están en `app/core/schemas/`: `Message` y
  `PlainDecimal` (`common.py`, `types.py`), las validaciones de contraseña y
  usuario (`validators.py`) y los de usuarios, roles, sesión y eventos.

Ejemplos de esta guía: el catálogo de `app/models/steps.md`.

---

## 1. Los tres esquemas de un recurso

Por cada modelo, un archivo con tres esquemas:

| Esquema | Cuándo se usa | Regla |
|---|---|---|
| `XCreate` | `POST` (crear) | Lo obligatorio va sin valor por defecto |
| `XUpdate` | `PATCH` (editar) | **Todo opcional**, con `None` por defecto |
| `XOut` | Respuestas | Lo que el cliente puede ver. Nunca secretos (contraseñas, claves) |

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)


class CategoryOut(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    deleted_at: datetime | None
```

**Cómo funciona el `PATCH`.** Lo que no se envía **no cambia**. Lo que se envía
como `null` significa "ponlo en nulo": si el campo del modelo no admite nulos, la
API responde `422` (`"No puede quedar vacío"`).

Un archivo por modelo o por dominio (`product.py`, `category.py`). Los esquemas
de acciones propias (`StockChange`, `TagsIn`) van en el archivo del recurso al que
pertenecen.

---

## 2. Tipos de campo

| Tipo Python | Entra como | Sale como |
|---|---|---|
| `str`, `int`, `float`, `bool` | igual | igual |
| `Decimal` | `"19.90"` o `19.9` | **texto**. En respuestas usa `PlainDecimal` (ver abajo) |
| `date` | `"2026-05-01"` | `"2026-05-01"` |
| `time` | `"09:30:00"` | `"09:30:00Z"` si viene de un modelo (`TimeField` lo devuelve con zona UTC) |
| `datetime` | `"2026-05-01T10:00:00Z"` | `"2026-05-01T10:00:00Z"` |
| `AwareDatetime` | igual, **exige zona horaria** | igual |
| `timedelta` | `"P30D"` (ISO 8601) o segundos | `"P30D"` |
| `UUID` | `"01a0..."` | texto |
| `Enum` | el valor (`"active"`, `3`) | el valor |
| `list[str]`, `dict[str, str]` | JSON | JSON |
| `Literal["a", "b"]` | solo esos valores | igual |
| `X \| None` | el valor o `null` | igual |
| otro esquema | objeto anidado | objeto anidado |

### Decimales en las respuestas: `PlainDecimal`

Tortoise normaliza el decimal de un objeto recién creado: `Decimal("20.00")` queda
como `Decimal("2E+1")`, y Pydantic lo enviaría al cliente como el texto `"2E+1"`.
Para las respuestas usa `PlainDecimal`, que lo escribe sin exponente (`"20"`):

```python
from app.core.schemas.types import PlainDecimal


class ProductOut(BaseModel):
    price: PlainDecimal
```

Sale como texto sin exponente: el valor recién creado como `"20"` y el leído de la
base de datos con sus decimales (`"20.00"`, `"19.90"`). El frontend lo convierte
y le da formato (`Number(value).toFixed(2)`), así que ambas formas valen. En los
esquemas de **entrada** basta `Decimal`.

### Fechas de entrada

Recomendación: usa `AwareDatetime`. Con `datetime` una
fecha sin zona (`2026-05-01T10:00:00`) se acepta y se interpreta como UTC, lo que
casi nunca es lo que quería quien la envió.

Los enums se importan del **modelo** (`from app.models.product import ProductStatus`)
para no declararlos dos veces.

---

## 3. Restricciones

### Con `Field(...)`

```python
class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    weight: float | None = Field(default=None, gt=0)
    stock: int = Field(default=0, ge=0)
    rating: int | None = Field(default=None, ge=1, le=5)
    tags: list[str] = Field(default_factory=list, max_length=10)
    delta: int = Field(description="Positivo suma, negativo resta")
```

| Opción | Aplica a | Significado |
|---|---|---|
| `min_length`, `max_length` | texto y listas | Longitud |
| `ge`, `gt`, `le`, `lt` | números | Mayor o igual, mayor, menor o igual, menor |
| `multiple_of` | números | Múltiplo de |
| `max_digits`, `decimal_places` | `Decimal` | Dígitos totales y decimales |
| `pattern` | texto | Expresión regular |
| `default`, `default_factory` | todos | Valor por defecto |
| `description`, `examples` | todos | Aparecen en `/docs` |

Los límites del esquema **deben ser iguales o más estrictos** que los del modelo
(`max_length`, `max_digits`...). Si el esquema deja pasar más de lo que cabe en la
columna, el fallo llega al guardar como un `422 VAL_422` **sin campo**, en vez de un
error junto al campo del formulario.

### Todo texto y toda lista llevan `max_length`

El servidor arranca aunque falte, pero es la norma del proyecto. Sin límite, un
`str` acepta cualquier tamaño hasta el tope de 1 MiB del cuerpo de la petición, y
lo que no cabe en la columna del modelo se rechaza al guardar: PostgreSQL no
recorta, y la API responde `422 VAL_422` sin decir qué campo. Con `max_length` en
el esquema, el error llega con su campo y el frontend lo marca en el formulario.

Cada límite se escribe donde se usa: `max_length=n` en el esquema y el **mismo
número** en la columna (`fields.CharField(max_length=n)`). Si el campo se escribe
en un formulario, el frontend lo repite en `frontend/src/core/limits.ts`. Estos
son los topes que usa el sistema, por si quieres ser coherente con ellos:

| Dato | Máximo |
|---|---|
| Nombre de usuario | 50 |
| Contraseña | 128 |
| Nombres (roles, productos...) | 100 |
| Descripciones y notas cortas | 255 |
| Cajas de búsqueda y filtros de texto | 100 |
| Elementos de una lista (los permisos de un rol: `RoleCreate` y `RoleUpdate`) | 2000 |

Los tipos `Username`, `Password` y `SearchText` de `app/core/schemas/types.py` ya
llevan su máximo (50, 128 y 100): úsalos en vez de repetirlos.

```python
from typing import Annotated

from pydantic import BaseModel, Field

from app.core.schemas.types import Password, Username


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    note: str = Field(default="", max_length=255)
    tags: list[Annotated[str, Field(max_length=20)]] = Field(default_factory=list, max_length=10)


class OwnerCreate(BaseModel):
    username: Username
    password: Password
```

### Con `StringConstraints` (limpiar y validar texto)

```python
from typing import Annotated

from pydantic import StringConstraints

Sku = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9-]+$", max_length=40
    ),
]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=150)]
```

Con eso `" ab-1 "` llega al modelo como `"AB-1"`. Un tipo definido una vez se
reutiliza en todos los esquemas.

**Ojo:** el `pattern` se comprueba **antes** de `to_upper` / `to_lower`. Si conviertes
a mayúsculas, el patrón tiene que aceptar también minúsculas (`[A-Za-z0-9-]`).

---

## 4. Validaciones propias

### De un campo (`field_validator`)

```python
from pydantic import field_validator


class ProductCreate(BaseModel):
    attributes: dict[str, str] = {}

    @field_validator("attributes")
    @classmethod
    def _limit_attributes(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 20:
            raise ValueError("Máximo 20 atributos")
        return value
```

Lanza `ValueError("mensaje en español")`. El mensaje llega al cliente junto a su
campo. Devuelve siempre el valor (limpio o no).

### De varios campos (`model_validator`)

```python
from pydantic import model_validator


class ProductCreate(BaseModel):
    status: ProductStatus = ProductStatus.DRAFT
    published_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _check_publication(self) -> ProductCreate:
        if self.status is ProductStatus.ACTIVE and self.published_at is None:
            raise ValueError("Un producto activo necesita fecha de publicación")
        return self
```

El error de un `model_validator` no pertenece a ningún campo: llega en
`fields["body"]`.

### Reutilizar las validaciones del sistema

```python
from pydantic import field_validator

from app.core.schemas.types import Password, Username
from app.core.schemas.validators import validate_password, validate_username


class EmployeeCreate(BaseModel):
    username: Username
    password: Password

    _check_username = field_validator("username")(validate_username)
    _check_password = field_validator("password")(validate_password)
```

`validate_username` devuelve el nombre recortado y en minúsculas, y solo admite
ASCII (letras sin acentos, números, punto, guion y guion bajo): el valor que llega
al modelo es el ya normalizado. `validate_password` aplica la política de
contraseñas. Sus longitudes (`USERNAME_MIN_LENGTH`, `USERNAME_MAX_LENGTH`,
`PASSWORD_MIN_LENGTH`, `PASSWORD_MAX_LENGTH`) están en el mismo archivo,
`app/core/schemas/validators.py`.

### Cómo llega el error al cliente

Todo error de validación sale como `422` con el código `VAL_422` y un diccionario
`fields` con un mensaje por campo. El frontend lo deja junto a cada campo del
formulario sin código extra:

```json
{ "error": { "code": "VAL_422", "fields": {
    "sku": "Formato no válido",
    "price": "Debe ser mayor o igual que 0" } } }
```

Los mensajes de las restricciones (`Field`, `StringConstraints`) salen **en
español**: «Este campo es obligatorio», «Mínimo 2 caracteres», «Máximo 150
caracteres», «Debe ser un número entero», «Identificador no válido»... Los genera
el sistema a partir del tipo de error de Pydantic; la lista completa está en
`app/errors/steps.md`, sección 5. Un tipo que no esté en esa lista conserva el
texto en inglés de Pydantic. Para un mensaje más concreto en una regla (por
ejemplo, qué formato se espera en un `pattern`), usa un `field_validator` y lanza
`ValueError` con tu texto.

---

## 5. Campos calculados

Un campo que se calcula a partir de los demás y solo sale en la respuesta:

```python
from pydantic import computed_field


class ProductOut(BaseModel):
    stock: int

    @computed_field
    @property
    def in_stock(self) -> bool:
        return self.stock > 0
```

Si el dato viene de **otra tabla** (por ejemplo `category_name`), no se calcula
aquí: se rellena en el método `serialize` del recurso (ver `app/routes/steps.md`)
y el campo se declara con valor por defecto: `category_name: str | None = None`.

---

## 6. Esquemas de acciones propias

Cada endpoint propio recibe su esquema de entrada:

```python
class StockChange(BaseModel):
    delta: int = Field(description="Positivo suma, negativo resta")


class TagsIn(BaseModel):
    tag_ids: list[UUID] = Field(max_length=200)
```

Para las respuestas hay cuatro formas:

| Devuelve | `response_model` |
|---|---|
| Un registro | `ProductOut` |
| Una lista sin paginar | `list[ProductOut]` |
| Una lista paginada | `Page[ProductOut]` (de `fastapi_pagination`) |
| Un mensaje | `Message` (de `app.core.schemas.common`) |

---

## 7. Parámetros de consulta como esquema

Cuando un listado propio tiene muchos filtros, agrúpalos en una clase y recíbela
con `Depends()`:

```python
from dataclasses import dataclass
from decimal import Decimal

from fastapi import Query
from pydantic import AwareDatetime


@dataclass
class ProductFilters:
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    search: str | None = Query(None, max_length=100, description="Texto del nombre")
    created_from: AwareDatetime | None = None
```

```python
@router.get("/advanced")
async def advanced(filters: ProductFilters = Depends(), actor: Users = requires(LIST)): ...
```

`Query(...)` solo hace falta para añadir descripción o restricciones. Un
`bool` con valor por defecto se recibe como `?flag=true`. Los filtros de texto
también llevan `max_length`, como el `search` de arriba.

Esto es para listados **propios**. El listado de un `Resource` ya trae `search`,
`deleted`, `sort`, filtros por igualdad, «contiene» y rangos: se piden con
`filter_fields`, `text_fields`, `range_fields` y `sort_fields` (sección 3 de
`app/routes/steps.md`), sin escribir ninguna clase.

---

## 8. Conectar los esquemas con un recurso

En la ruta (`app/routes/steps.md`) se asignan a `Resource`:

```python
class ProductsResource(Resource[Product]):
    model = Product
    create_schema = ProductCreate
    update_schema = ProductUpdate
    out_schema = ProductOut
    filter_fields = ("active", "category_id", "status")
```

- Los campos de `create_schema` se pasan tal cual a `Model.create(...)`: **todos
  deben ser columnas del modelo**. Un campo que no lo sea (por ejemplo `tag_ids`)
  no va aquí: se gestiona con un endpoint propio. Tortoise ignora en silencio los
  argumentos que no conoce, así que ese dato se perdería sin ningún error.
- Los campos de `filter_fields`, `text_fields`, `range_fields` y `sort_fields` deben
  ser columnas del modelo **y** campos de `out_schema`: el tipo del parámetro
  (UUID, número, fecha con zona, booleano...) sale de ahí, y un campo que falte
  impide arrancar. Un campo calculado en `serialize` no sirve.
- `Resource` convierte el modelo en `out_schema` con `model_validate(item,
  from_attributes=True)`: los nombres de los campos de `XOut` deben coincidir
  con los atributos del modelo.
- Un esquema con un campo que **elige un rol o concede permisos** (`role_id`, una
  lista de permisos) no basta con validarlo: el recurso debe llamar a
  `check_role_assignable` o `check_can_grant` en su hook. Ver la sección 6 de
  `app/routes/steps.md`.

---

## 9. Errores frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `422` con `Formato no válido` aunque el valor "es correcto" | `pattern` se evalúa antes de `to_upper` | Haz el patrón tolerante a minúsculas |
| `422` con `fields: {"body": ...}` | Error de un `model_validator` | Es lo esperado: no pertenece a un campo |
| Un campo del esquema de creación no llega a la base de datos, sin ningún error | No es una columna del modelo: Tortoise ignora los argumentos que no conoce | Quítalo del esquema y usa un endpoint propio |
| `ConfigurationError: You can't set m2m relations through init` al crear | El esquema de creación trae una relación muchos a muchos (`tags`) | Quítalo del esquema y asígnala en un endpoint propio |
| `422 VAL_422` sin campo al guardar | El esquema permite más largo que la columna | Iguala `max_length` con el del modelo |
| El precio llega como `"2E+1"` | `Decimal` normalizado en un esquema de salida | Usa `PlainDecimal` en `XOut` |
| Un `PATCH` con `null` da `422` | El campo del modelo no admite nulos | Envía solo lo que cambia, o pon `null=True` en el modelo |
| `ValidationError` al construir `XOut` | Falta un campo en el modelo o hay que rellenarlo en `serialize` | Dale valor por defecto o rellénalo en `serialize` |
