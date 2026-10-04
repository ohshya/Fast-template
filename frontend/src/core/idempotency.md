# Clave de idempotencia (`Idempotency-Key`)

Un doble clic o un reintento de red envían la misma escritura dos veces. El
backend puede procesarla **una sola vez** y devolver la misma respuesta a la
copia, pero para eso el frontend tiene que decirle qué peticiones son la misma
intención: con la cabecera `Idempotency-Key`.

**Estado: el frontend ya la envía.** `createForm` custodia una clave por formulario, `post`,
`patch` y `crud()` la aceptan y el interceptor la deriva al reintentar tras renovar la
sesión. Esta guía explica el porqué de cada regla y cómo usarla en código nuevo: las
secciones 1 a 3 describen lo que ya está hecho (con sus fragmentos) y dónde. Sin clave,
el servidor solo protege el modo automático: la misma escritura idéntica (mismo
emisor, método, ruta, query y cuerpo), seguida, durante 10 s desde que termina la
primera; cualquier otra escritura del mismo emisor corta la racha. Las reglas del lado
del servidor están en la sección "Solicitudes repetidas" de `GUIA.md`.

---

## 1. Qué es la clave y cómo generarla

Es un texto de 1 a 255 caracteres que identifica **una intención del usuario**
("guardar este formulario"), no una petición: los reintentos de esa misma
intención llevan la misma clave.

```ts
export const newKey = () =>
	Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
```

Son 128 bits aleatorios en hexadecimal (32 caracteres): no se repite ni se adivina, y
funciona en cualquier contexto. `crypto.randomUUID()` sería igual de válido, pero solo
existe en HTTPS y `localhost`: en `http://192.168.1.20:5173` lanza `crypto.randomUUID
is not a function`. `newKey` está definida una sola vez, en `core/api.ts`: úsala en todos los sitios.

Lo que **no** hay que hacer:

| Idea | Por qué falla |
|---|---|
| Un hash del cuerpo | Dos compras idénticas y legítimas se fundirían en una |
| Una clave por sesión, pestaña o carga de página | La segunda escritura distinta recibe `422 IDM_002` y una idéntica recibe la respuesta de la primera, durante 24 h |
| `Date.now()` o un contador | Se repite entre pestañas y se puede adivinar |
| Una clave nueva en **cada** petición, reintentos incluidos | Es peor que no enviar nada: con clave el servidor deja de aplicar el modo automático de 10 s, y tres envíos idénticos se ejecutan tres veces |

Ojo con lo último: **una escritura que envía clave pierde el modo automático**; la
clave pasa a ser su única protección. Envíala solo cuando vayas a gobernarla bien.

---

## 2. Cuándo se mantiene y cuándo se cambia

La regla: **se mantiene mientras no se sepa qué pasó; se cambia cuando la respuesta
ya es definitiva o cuando la intención cambia.**

| Situación | Clave del siguiente intento | Por qué |
|---|---|---|
| El usuario pulsa Guardar (envío nuevo) | Nueva | Intención nueva |
| No hay respuesta (fallo de red, `NET_000`, estado 0) | **La misma** | No se sabe si llegó. Si llegó, el servidor devuelve la respuesta guardada; si no, la ejecuta por primera vez |
| Error 5xx | **La misma** | El servidor no guarda los 5xx: se ejecuta de nuevo |
| `409 IDM_001` (la copia anterior sigue en proceso) | **La misma** | Espera y responderá con lo que termine guardando |
| Otro 4xx que salga de la ruta (validación 422, 403 de permisos, 404, un 409 de duplicado, un 429...) | Nueva | El servidor lo guarda 24 h con esa clave: con el mismo cuerpo repetiría el error y con otro daría `422 IDM_002`. Un 429 no es "definitivo", pero se guarda igual: espera y usa clave nueva |
| Un 401 y el interceptor renueva la sesión | La derivada `clave:renew` (sección 3.2) | El 401 también se guarda; la petición no llegó a ejecutarse, así que cambiarla es seguro |
| El usuario edita el formulario | Nueva | Cuerpo distinto es otra intención |
| Éxito | Nueva para la siguiente acción | |

Un límite de la fila de edición: si el intento anterior quedó **sin respuesta**, se
edita el formulario y se reenvía, es otra intención con otra clave; si el primero sí
llegó a ejecutarse, se ejecuta también el segundo. Es un compromiso aceptado: el
usuario cambió los datos a propósito.

---

## 3. Dónde está

Tres piezas, ya hechas. El formulario (`createForm`) es quien guarda la clave, porque sabe
cuándo se edita, cuándo se envía y cómo terminó cada envío.

### 3.1 `core/api.ts`: aceptar la clave

`post` y `patch` reciben `key` (sin clave, axios no envía la cabecera) y `crud()` la pasa
en `create` y `update`:

```ts
function withKey(key?: string): AxiosRequestConfig {
	return key ? { headers: { "Idempotency-Key": key } } : {};
}

export async function post<T>(url: string, body?: unknown, key?: string): Promise<T> {
	return (await api.post<T>(url, body, withKey(key))).data;
}

export async function patch<T>(url: string, body?: unknown, key?: string): Promise<T> {
	return (await api.patch<T>(url, body, withKey(key))).data;
}
```

```ts
create: (data: Create, key?: string) => post<T>(`${path}/`, data, key),
update: (id: string, data: Update, key?: string) => patch<T>(`${path}/${id}`, data, key),
```

### 3.2 `core/api.ts`: otra clave al reintentar tras renovar la sesión

El interceptor de respuestas, justo antes de reenviar:

```ts
if (renewed) {
	deriveRetryKey(config);
	return api.request(config);
}
```

```ts
function deriveRetryKey(config: RequestConfig) {
	if (config.method?.toLowerCase() === "get") return;
	const headers = AxiosHeaders.from(config.headers as AxiosHeaders);
	const previous = headers.get("Idempotency-Key");
	headers.set("Idempotency-Key", `${typeof previous === "string" ? previous : newKey()}:renew`);
	config.headers = headers;
}
```

Por qué hace falta: el servidor guarda también el `401`. El caso normal (el token de
acceso caducó a los 15 minutos) ya no da problemas, porque entonces el emisor de la
petición es la IP y el del reintento es la sesión. Pero si otra pestaña renovó justo
antes, la petición viaja con un token ya rotado, el `401 AUT_004` se guarda con la
sesión como emisor y **el reintento idéntico recibe ese mismo 401**, lleve clave o
no. Comprobado con axios contra el servidor:

| Reintento | Sin clave | Con clave |
|---|---|---|
| Sin `deriveRetryKey` | `401 AUT_004` | `401 AUT_004` |
| Con `deriveRetryKey` | Se ejecuta | Se ejecuta |

La clave del reintento se **deriva** de la original (`clave:renew`) y no se vuelve a
sortear: si el usuario reenvía con la clave original, cae en el mismo registro y
recibe la misma respuesta, sin ejecutar dos veces (probado: reenvío doble, un solo
registro creado). En una escritura sin clave no hay nada que derivar y se crea una.

### 3.3 `core/form.ts`: el formulario custodia la clave

El esquema (el archivo real, además, avisa de los fallos que no son de la API):

```ts
import { ApiError, newKey } from "@/core/api";

export function createForm<T extends object>(initial: T) {
	const [values, setValues] = createSignal<T>(initial);
	const [errors, setErrors] = createSignal<Record<string, string>>({});
	const [saving, setSaving] = createSignal(false);
	let key = newKey();

	return {
		values,
		errors,
		saving,

		set<K extends keyof T>(name: K, value: T[K]) {
			key = newKey();
			setValues((current) => ({ ...current, [name]: value }));
		},

		reset(next: T = initial) {
			key = newKey();
			setValues(() => next);
			setErrors({});
		},

		async submit(action: (values: T, key: string) => Promise<unknown>): Promise<boolean> {
			setErrors({});
			setSaving(true);
			try {
				await action(values(), key);
				key = newKey();
				return true;
			} catch (error) {
				if (error instanceof ApiError) {
					setErrors(error.fields);
					const unknown = error.status === 0 || error.status >= 500 || error.code === "IDM_001";
					if (!unknown) key = newKey();
				}
				return false;
			} finally {
				setSaving(false);
			}
		},
	};
}
```

Cada página que crea o edita pasa la clave a la llamada. Ejemplo, `Roles.tsx` (`Users.tsx`
hace lo mismo en su `form.submit`):

```ts
const saved = await form.submit(async (values, key) => {
	const data = { ...values, name: values.name.trim(), description: values.description.trim() };
	const role = current
		? await RolesApi.update(current.id, data, key)
		: await RolesApi.create(data, key);
	notify.success(`Rol ${role.name} ${current ? "actualizado" : "creado"}`);
});
```

### 3.4 Acciones de un solo clic

Borrar y editar (`DELETE`, `PATCH`) ya son casi idempotentes: repetirlos no duplica
nada. La clave importa sobre todo en los `POST` que **crean** algo o que disparan
algo que no puede repetirse (un pago, un correo, una importación); restaurar
(`restore`) es también un `POST`, pero repetirlo no crea nada.

Los envoltorios `del`, `remove`, `hardDelete` y `restore` de `api.ts` no aceptan clave (y
los de `modules/users.ts` y `modules/auth.ts` solo en las contraseñas): si necesitas una en
un botón, añade un parámetro `key` como en 3.1. En un botón sin formulario, genera la
clave al pulsar y mantenlo deshabilitado mientras la petición está en curso.

---

## 4. Qué ve el frontend

| Respuesta | Significa |
|---|---|
| Cabecera `Idempotent-Replayed: true` | Es una copia de la respuesta guardada; no se volvió a ejecutar. `post()` devuelve solo el cuerpo: para leer la cabecera usa `api.post` directamente |
| `409 IDM_001` | Una copia idéntica sigue procesándose (el servidor espera hasta 15 s antes de contestar esto) |
| `422 IDM_002` | La misma clave con otro método, ruta, query o cuerpo |
| `422 IDM_003` | Clave vacía o de más de 255 caracteres |
| `413 SYS_413` | Cuerpo de más de 1 MiB. Es el límite general de la API, lleve clave o no |

La respuesta repetida conserva el estado, el cuerpo y las cabeceras de la ruta (no
`Set-Cookie`, las cabeceras de conexión ni `Content-Length`). El `X-Request-ID` de la
cabecera es el de **esta** petición, no el de la original; en cambio `request_id` y
`event_id` dentro del cuerpo de un error repetido son los de la original.

---

## 5. Lo que conviene saber

- **La clave vale para quien la envía.** El servidor la une a la sesión (o a la IP,
  sin sesión o con el token de acceso caducado): la misma clave desde otra sesión no
  tiene relación. Al cerrar sesión y volver a entrar, la clave anterior ya no cuenta
  como la misma.
- **Se recuerda 24 h.** Pasado ese tiempo, la misma clave se toma como nueva.
- **Solo `POST`, `PUT`, `PATCH` y `DELETE`** bajo `/api`. En un `GET` se ignora.
- **Login, renovación y cierre de sesión no la necesitan:** sus respuestas correctas
  ponen o borran cookies y por eso nunca se guardan. Un login fallido, que no las
  pone, sí se guarda: 10 s en modo automático, 24 h si llevara clave.
- **El doble clic ya lo evita el botón** (`disabled={form.saving()}`); la clave es la
  segunda línea de defensa. Diez envíos simultáneos con la misma clave, repartidos
  entre procesos: uno se ejecutó y los otros nueve recibieron su respuesta. Vale
  mientras el primero termine con una respuesta que se guarda (ni 5xx ni cookies) en
  menos de 15 s; si no, las copias se ejecutan una tras otra o reciben `409 IDM_001`.
- **Pendiente en la librería `fastapi-idempotency`:** con clave guarda cualquier
  4xx durante 24 h. Las reglas de la sección 2 sobre el 4xx existen por eso; si la
  librería deja de guardarlos, se simplifican.

---

## 6. Errores frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `422 IDM_002` al reenviar el formulario corregido | Se reutilizó la clave después de editar | La clave debe cambiar al editar: `form.set` ya lo hace |
| Tras renovarse la sesión, la escritura falla con `401 AUT_004` y `Idempotent-Replayed: true` | El reintento del interceptor repitió la petición idéntica | Cambia la clave en el reintento (3.2) |
| Se crean dos registros iguales pese a enviar clave | Cada clic generó una clave distinta | Genera la clave una vez por intención, en el formulario, no en cada petición |
| `crypto.randomUUID is not a function` | Página servida por HTTP fuera de `localhost` | Usa `newKey()` (sección 1) |
| `422 IDM_003` | Clave vacía o de más de 255 caracteres | Un texto de 32 o 36 caracteres |
