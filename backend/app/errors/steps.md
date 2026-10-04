# Errores (`app/errors/`)

Aquí se declaran **los errores de tu proyecto**. Todo error de la API sale con la
misma forma, y el frontend la entiende sin código extra:

```json
{ "error": { "code": "PRD_002", "message": "No queda stock de este producto.",
             "toast": true, "severity": "warning", "request_id": "01a0...",
             "event_id": null, "fields": null, "details": { "sku": "A1" } } }
```

Nada se carga solo: cada error es un objeto `ErrorSpec` definido en esta carpeta
y listado a mano en `ERRORS`, dentro de `app/registry.py` (sección 2). Al arrancar,
`main.py` añade esa lista al catálogo: los errores aparecen en la pestaña
**Errores** de `/debug` y en `GET /api/system/errors`.

Los errores del sistema (sesión, permisos, validación, usuarios, roles...) están
en `app/core/errors.py`, dentro de la clase `Err`. No se editan.
`app/core/registry.py` es el registro del sistema y tampoco se toca.

---

## 1. Declarar un error

Un archivo por dominio (`catalog.py`, `billing.py`). Cada error es una constante
con su `ErrorSpec`; no hay que llamar a nada más:

```python
from app.core.errors import ErrorSpec, Severity

PRODUCT_NOT_FOUND = ErrorSpec("PRD_001", 404, "El producto no existe.", severity=Severity.WARNING)
OUT_OF_STOCK = ErrorSpec(
    "PRD_002", 409, "No queda stock de este producto.", severity=Severity.WARNING
)
```

### Campos de `ErrorSpec`

| Campo | Para qué |
|---|---|
| `code` | Identificador público y estable. Es lo que ve el frontend (`PRD_002`) |
| `status` | Status HTTP de la respuesta |
| `message` | Lo que lee el usuario final. En español y en una frase |
| `toast` | `True` (por defecto): el frontend lo muestra como aviso. `False` si lo gestiona la pantalla sin avisar |
| `severity` | `Severity.INFO`, `WARNING`, `ERROR` (por defecto) o `CRITICAL`. Decide el nivel del log |
| `persist` | `True`: además se guarda como evento en la auditoría. Para errores de seguridad o que interesa investigar |
| `hint` | Nota para desarrolladores. No se envía al cliente; se ve en `/debug` |

### Convenciones

- **Código:** tres letras del dominio, guion bajo y número: `PRD_001`, `PAY_004`.
  Los del sistema usan `SYS_`, `VAL_`, `AUT_`, `PRM_`, `USR_`, `ROL_`, `EVT_`,
  `IDM_` (y `HTTP_` para los status que Starlette genera por su cuenta): no los
  reutilices.
- **Status:** `404` no existe, `409` conflicto con el estado actual, `422` dato
  inválido, `403` sin permiso, `400` petición mal formada.
- **Mensaje:** dice qué pasó y, si se puede, qué hacer. Sin tecnicismos.

---

## 2. Registrarlo

En `app/registry.py`, importa el módulo y añade cada error a la lista `ERRORS`.
Importa con un alias que no choque: `catalog` también puede existir en
`app/routes/` y en `app/services/`, y el segundo `import catalog` pisaría al
primero.

```python
from app.errors import catalog as catalog_errors

ERRORS: list[ErrorSpec] = [catalog_errors.PRODUCT_NOT_FOUND, catalog_errors.OUT_OF_STOCK]
```

- `main.py` recorre `ERRORS` y registra cada error en el catálogo al arrancar.
  **Un código repetido impide arrancar**, tanto si lo repiten dos errores tuyos
  como si choca con uno del sistema: `RuntimeError: Código de error duplicado: PRD_002`.
- Un error que no está en `ERRORS` **funciona igual** al lanzarlo (la respuesta
  sale de su propio `ErrorSpec`), pero no entra al catálogo: no aparece en `/debug`
  ni en `GET /api/system/errors`.

---

## 3. Lanzarlo

Desde una ruta, un servicio o un hook de `Resource`:

```python
from app.core.errors import AppError
from app.errors.catalog import OUT_OF_STOCK

raise AppError(OUT_OF_STOCK, details={"sku": product.sku})
```

```python
raise AppError(Err.VALIDATION, fields={"stock": "No puede ser negativo"})
```

| Argumento | Para qué |
|---|---|
| `details={...}` | Datos extra que viajan en la respuesta |
| `fields={"campo": "mensaje"}` | Errores por campo: el formulario del frontend los marca solo |
| `log_message="..."` | Texto más detallado para el log y la auditoría (no se envía al cliente) |
| `toast=False` | Cambia el aviso para este caso |
| `persist=True` | Fuerza guardarlo como evento en este caso |

Se lanza siempre `AppError`, **nunca `HTTPException`**.

### Como error de un recurso

Para que `Resource` responda `PRODUCT_NOT_FOUND` en lugar del genérico:

```python
class ProductsResource(Resource[Product]):
    not_found = PRODUCT_NOT_FOUND
```

---

## 4. Qué ocurre cuando se lanza

1. Se escribe una línea en el log con el `request_id`, el código y el mensaje.
2. Si el error tiene `persist=True`, se guarda como evento (categoría error o
   seguridad; con el tope de más abajo) y la respuesta lleva su `event_id`.
3. La transacción de la petición se deshace: no queda nada a medias.
4. La respuesta sale con la forma uniforme. El interceptor del frontend muestra el
   aviso si `toast` es `true` y renueva la sesión si el `401` es solo un token
   caducado.

Una excepción que no sea `AppError` (un fallo inesperado) se convierte en `500
SYS_500`, se guarda en la auditoría y, en desarrollo, la respuesta incluye el texto
de la excepción en `debug`. Los eventos de error tienen un tope de 30 por IP y
código cada minuto, por proceso: pasado el tope solo llegan al log.

Excepciones de la base de datos que se convierten solas: `DoesNotExist` (`404`),
valor único repetido (`409 SYS_409`), clave foránea que impide borrar
(`409 SYS_REL`), texto o valor que no cumple la columna o sus validadores
(`422 VAL_422`, sin campo) y base de datos caída o columna inexistente
(`503 SYS_503`).

---

## 5. Mensajes de validación por campo

Cuando Pydantic rechaza un dato (del cuerpo, de la ruta o de la query), la
respuesta es `422 VAL_422` y `fields` trae **un mensaje en español por campo**. Los
genera `_from_validation`, en `app/core/errors.py`, a partir del tipo de error de
Pydantic:

| Tipo de error de Pydantic | Mensaje |
|---|---|
| `missing` | Este campo es obligatorio |
| `string_type` | Debe ser un texto |
| `string_too_short`, `string_too_long` | Mínimo N caracteres, Máximo N caracteres |
| `string_pattern_mismatch` | Formato no válido |
| `too_short`, `too_long` | Mínimo N elementos, Máximo N elementos |
| `greater_than`, `greater_than_equal`, `less_than`, `less_than_equal` | Debe ser mayor que N, mayor o igual que N, menor que N, menor o igual que N |
| `int_type`, `int_parsing`, `int_from_float` | Debe ser un número entero |
| `float_type`, `float_parsing` | Debe ser un número |
| `decimal_type`, `decimal_parsing` | Debe ser un número decimal |
| `decimal_max_digits`, `decimal_max_places`, `decimal_whole_digits` | Máximo N dígitos, Máximo N decimales, Máximo N dígitos enteros |
| `bool_type`, `bool_parsing` | Debe ser verdadero o falso |
| `uuid_type`, `uuid_parsing` | Identificador no válido |
| `date_type`, `date_parsing`, `date_from_datetime_parsing` | Fecha no válida |
| `datetime_type`, `datetime_parsing`, `datetime_from_date_parsing` | Fecha y hora no válidas |
| `time_type`, `time_parsing` | Hora no válida |
| `timezone_aware`, `timezone_naive` | La fecha necesita zona horaria, La fecha no debe llevar zona horaria |
| `enum`, `literal_error` | Valor no permitido |
| `list_type` | Debe ser una lista |
| `dict_type`, `model_type`, `model_attributes_type` | Debe ser un objeto |
| `json_invalid` | JSON no válido |
| `extra_forbidden` | Campo no permitido |
| `url_parsing` | URL no válida |

- **El nombre del campo** es el del cuerpo o de la query (`name`, `role_id`). El
  error de un `model_validator` no es de ningún campo y llega como `body`. Los
  elementos de una lista del cuerpo llevan su posición (`tags.0`); los de una lista
  de la query no (`role_id`, no `role_id.0`).
- **Un tipo que no está en la tabla** conserva el texto de Pydantic, en inglés.
  Pasa solo con validaciones poco comunes.
- **Un validador propio** (`field_validator`, `model_validator`) pone su mensaje
  con `raise ValueError("mensaje en español")`: llega tal cual al campo, sin el
  prefijo `Value error, ` de Pydantic (con un `assert`, tampoco `Assertion failed, `).

```python
from pydantic import BaseModel, field_validator


class ProductCreate(BaseModel):
    sku: str

    @field_validator("sku")
    @classmethod
    def _check_sku(cls, value: str) -> str:
        if value.startswith("X"):
            raise ValueError("El SKU no puede empezar por X")
        return value
```

Con `{"sku": "X1"}` responde:

```json
{ "error": { "code": "VAL_422", "fields": { "sku": "El SKU no puede empezar por X" } } }
```

Para dar un mensaje propio a un tipo de Pydantic en todo el proyecto, hay que
añadirlo al diccionario de `_from_validation`: la clave es el tipo del error y el
valor, una función que recibe el contexto del error y devuelve el texto. Es código
del sistema. Si el error lo detectas tú en una ruta o un servicio, escribe el
mensaje directamente (`raise AppError(Err.VALIDATION, fields={"stock": "..."})`).

---

## 6. Comprobarlo

No hay pruebas unitarias (los `backend/checks/` ejercitan la API real, pero no tus errores nuevos). Para ver un error funcionando:

1. Guarda los cambios: `fastapi dev` recarga solo y, si un código está repetido, no
   arranca y dice cuál.
2. Abre **Debug → Errores** (solo dev): tu código debe salir en el catálogo con su
   status y su mensaje.
3. Llama desde `/docs` (con `DEBUG=true`) al endpoint que lo lanza y revisa la
   respuesta: `code`, `message`, `details` y `request_id`.

---

## 7. Errores frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `RuntimeError: Código de error duplicado` al arrancar | Dos errores con el mismo código, o uno choca con un código del sistema | Cambia uno |
| Un mensaje de `fields` sale en inglés | El tipo de error de Pydantic no está en la tabla de la sección 5 | Valida con un `field_validator` que lance `ValueError("mensaje en español")` |
| El error no aparece en `/debug` → Errores | No está en `ERRORS` de `app/registry.py` | Añádelo a la lista |
| `ModuleNotFoundError` al arrancar | El import de `app/registry.py` apunta a un archivo que no existe | Corrige el nombre del módulo |
| La respuesta es un `500` en vez de tu error | Lanzaste `HTTPException` o una excepción normal | Lanza `AppError(...)` |
| El aviso sale aunque no lo quieres | `toast=True` (por defecto) | `ErrorSpec(..., toast=False)` |
| No se puede rastrear un error de seguridad | `persist=False` | Usa `persist=True` |
