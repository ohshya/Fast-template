import axios, { AxiosHeaders, type AxiosError, type AxiosRequestConfig } from "axios";
import { notify } from "@/core/notify";
import { requestLog } from "@/core/requestLog";

export type ErrorPayload = {
	code: string;
	message: string;
	toast: boolean;
	severity: "info" | "warning" | "error" | "critical";
	request_id: string;
	event_id: string | null;
	fields: Record<string, string> | null;
	details: Record<string, unknown>;
	debug?: string;
};

export type Page<T> = {
	items: T[];
	total: number;
	page: number;
	size: number;
	pages: number;
};

export type Message = { detail: string };

/** Parámetros de un listado: los comunes y los que declare cada recurso (filtros, rangos, `sort`). */
export type ListParams = {
	page?: number;
	size?: number;
	search?: string;
	deleted?: boolean;
} & Record<string, unknown>;

export class ApiError extends Error {
	payload: ErrorPayload;
	status: number;

	constructor(payload: ErrorPayload, status: number) {
		super(payload.message);
		this.name = "ApiError";
		this.payload = payload;
		this.status = status;
	}

	get code() {
		return this.payload.code;
	}

	get fields() {
		return this.payload.fields ?? {};
	}
}

const NETWORK_ERROR: ErrorPayload = {
	code: "NET_000",
	message: "No se pudo conectar con el servidor.",
	toast: true,
	severity: "error",
	request_id: "-",
	event_id: null,
	fields: null,
	details: {},
};

const IDEMPOTENCY_HEADER = "Idempotency-Key";

/** `_silent`: la petición no muestra avisos ni intenta renovar la sesión. `_started`: cuándo salió. */
type RequestConfig = AxiosRequestConfig & {
	_retried?: boolean;
	_silent?: boolean;
	_started?: number;
};

/** Los arrays se envían como parámetros repetidos (`?role_id=a&role_id=b`), que es lo que lee el backend. */
export const api = axios.create({
	baseURL: "/api",
	withCredentials: true,
	paramsSerializer: { indexes: null },
});

let refreshing: Promise<boolean> | null = null;
let onSessionLost: (() => void) | null = null;
let onPermissionDenied: (() => void) | null = null;
let onReachable: (() => void) | null = null;
let onUnreachable: ((reason: string) => void) | null = null;

/** El store de sesión registra aquí qué hacer cuando ya no hay sesión. */
export function handleSessionLost(callback: () => void) {
	onSessionLost = callback;
}

/** El store de sesión registra aquí qué hacer cuando el servidor niega un permiso (puede haber cambiado). */
export function handlePermissionDenied(callback: () => void) {
	onPermissionDenied = callback;
}

/** `core/serverStatus.ts` registra aquí qué hacer cuando el servidor responde o deja de responder. */
export function handleConnection(reachable: () => void, unreachable: (reason: string) => void) {
	onReachable = reachable;
	onUnreachable = unreachable;
}

/** Si el error indica que el servidor no está disponible: sin respuesta, 502/503/504 o base de datos caída. */
export function isUnreachable(error: unknown): boolean {
	return (
		error instanceof ApiError &&
		(error.status === 0 ||
			[502, 503, 504].includes(error.status) ||
			error.code === "SYS_503" ||
			(error.status >= 500 && error.code.startsWith("HTTP_")))
	);
}

/** Clave nueva para `Idempotency-Key`: 128 bits aleatorios en hexadecimal. Ver `core/idempotency.md`. */
export const newKey = () =>
	Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) =>
		byte.toString(16).padStart(2, "0"),
	).join("");

/** Ejecuta la tarea con un bloqueo compartido por todas las pestañas, si el navegador lo permite. */
async function acrossTabs<T>(name: string, task: () => Promise<T>): Promise<T> {
	const locks = globalThis.navigator?.locks;
	return locks ? await locks.request(name, task) : await task();
}

/**
 * Renueva la sesión una sola vez aunque fallen varias peticiones a la vez.
 *
 * Devuelve `false` si el servidor ya no la reconoce (401 o 403) y lanza el error si no se
 * pudo saber (sin red, 5xx): en ese caso la sesión sigue abierta y no hay que cerrarla.
 * El bloqueo entre pestañas impide que dos pestañas usen a la vez el mismo token de
 * refresco: el servidor lo tomaría por robado y cerraría la sesión.
 */
async function renewSession(): Promise<boolean> {
	const silent: RequestConfig = { _silent: true };
	refreshing ??= acrossTabs("auth-refresh", () => api.post("/auth/refresh", undefined, silent))
		.then(() => true)
		.catch((error: unknown) => {
			if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
				return false;
			}
			throw error;
		})
		.finally(() => {
			refreshing = null;
		});
	return refreshing;
}

/** Cambia la clave del reintento a `<clave>:renew`: el 401 anterior ya quedó guardado con la original. */
function deriveRetryKey(config: RequestConfig) {
	if (config.method?.toLowerCase() === "get") return;
	const headers = AxiosHeaders.from(config.headers as AxiosHeaders);
	const previous = headers.get(IDEMPOTENCY_HEADER);
	headers.set(IDEMPOTENCY_HEADER, `${typeof previous === "string" ? previous : newKey()}:renew`);
	config.headers = headers;
}

/** Apunta una petición terminada en el registro de `Debug → Peticiones`. */
function record(
	config: RequestConfig,
	status: number,
	headers: AxiosHeaders | undefined,
	code: string | null,
) {
	const sent = AxiosHeaders.from(config.headers as AxiosHeaders);
	const key = sent.get(IDEMPOTENCY_HEADER);
	const requestId = headers?.get("x-request-id");
	requestLog.record({
		at: Date.now(),
		method: (config.method ?? "get").toUpperCase(),
		url: api.getUri(config),
		status,
		ms: Math.round(performance.now() - (config._started ?? performance.now())),
		ok: status >= 200 && status < 400,
		code,
		requestId: typeof requestId === "string" ? requestId : null,
		key: typeof key === "string" ? key : null,
		replayed: headers?.get("idempotent-replayed") === "true",
		retried: !!config._retried,
		probe: !!config._silent && config.method?.toLowerCase() === "get",
	});
}

api.interceptors.request.use((config) => {
	(config as RequestConfig)._started = performance.now();
	return config;
});

api.interceptors.response.use(
	(response) => {
		onReachable?.();
		record(response.config as RequestConfig, response.status, AxiosHeaders.from(response.headers as AxiosHeaders), null);
		return response;
	},
	async (error: AxiosError<{ error?: ErrorPayload }>) => {
		if (axios.isCancel(error)) throw error;
		const config = (error.config ?? {}) as RequestConfig;

		if (!error.response) {
			onUnreachable?.(NETWORK_ERROR.message);
			record(config, 0, undefined, NETWORK_ERROR.code);
			if (!config._silent) notify.fromApi(NETWORK_ERROR);
			throw new ApiError(NETWORK_ERROR, 0);
		}

		const { status, data } = error.response;
		const payload: ErrorPayload = data?.error ?? {
			...NETWORK_ERROR,
			code: `HTTP_${status}`,
			message: "La respuesta del servidor no tiene el formato esperado.",
		};
		const failure = new ApiError(payload, status);
		if (isUnreachable(failure)) {
			onUnreachable?.(payload.code.startsWith("HTTP_") ? `El servidor no responde (error ${status}).` : payload.message);
		}
		else onReachable?.();
		record(config, status, AxiosHeaders.from(error.response.headers as AxiosHeaders), payload.code);
		if (config._silent) throw failure;

		const isSessionRoute = ["/auth/login", "/auth/refresh", "/auth/logout"].some((route) =>
			config.url?.includes(route),
		);
		const canRenew = status === 401 && !config._retried && !isSessionRoute;

		if (canRenew) {
			config._retried = true;
			let renewed: boolean;
			try {
				renewed = await renewSession();
			} catch (failure) {
				if (failure instanceof ApiError && failure.payload.toast) notify.fromApi(failure.payload);
				throw failure;
			}
			if (renewed) {
				deriveRetryKey(config);
				return api.request(config);
			}
			onSessionLost?.();
			throw new ApiError(payload, status);
		}

		if (payload.code === "AUT_006" && !isSessionRoute) onSessionLost?.();
		else if (payload.code === "PRM_001" || payload.code === "PRM_002") onPermissionDenied?.();

		if (payload.toast) {
			notify.fromApi(payload);
		}
		throw new ApiError(payload, status);
	},
);

/** Quita los parámetros vacíos para no ensuciar la URL. */
function clean(params?: object): Record<string, unknown> | undefined {
	if (!params) return undefined;
	return Object.fromEntries(
		Object.entries(params).filter(
			([, value]) =>
				value !== undefined &&
				value !== null &&
				value !== "" &&
				!(Array.isArray(value) && value.length === 0),
		),
	);
}

/** Cabecera `Idempotency-Key` si hay clave; sin ella, axios no envía nada. */
function withKey(key?: string): AxiosRequestConfig {
	return key ? { headers: { [IDEMPOTENCY_HEADER]: key } } : {};
}

/** Petición sin avisos ni renovación de sesión, para comprobaciones y tareas de fondo. */
export async function quiet<T>(method: "get" | "post", url: string): Promise<T> {
	const config: RequestConfig = { _silent: true };
	const response = method === "get" ? await api.get<T>(url, config) : await api.post<T>(url, undefined, config);
	return response.data;
}

/** GET que devuelve directamente el cuerpo de la respuesta. */
export async function get<T>(url: string, params?: object): Promise<T> {
	return (await api.get<T>(url, { params: clean(params) })).data;
}

/** POST que devuelve directamente el cuerpo de la respuesta. `key`: ver `core/idempotency.md`. */
export async function post<T>(url: string, body?: unknown, key?: string): Promise<T> {
	return (await api.post<T>(url, body, withKey(key))).data;
}

/** PATCH que devuelve directamente el cuerpo de la respuesta. `key`: ver `core/idempotency.md`. */
export async function patch<T>(url: string, body?: unknown, key?: string): Promise<T> {
	return (await api.patch<T>(url, body, withKey(key))).data;
}

/** DELETE que devuelve directamente el cuerpo de la respuesta. */
export async function del<T>(url: string, params?: object): Promise<T> {
	return (await api.delete<T>(url, { params: clean(params) })).data;
}

/** Avisa de un fallo del propio navegador; los de la API ya los avisó el interceptor. */
export function reportError(error: unknown) {
	if (error instanceof ApiError) return;
	console.error(error);
	notify.error("Ocurrió un error inesperado en la aplicación.");
}

/** Espera una petición y, si falla, devuelve un valor por defecto: el aviso ya lo dio el interceptor. */
export async function withFallback<T>(promise: Promise<T>, fallback: T): Promise<T> {
	try {
		return await promise;
	} catch (error) {
		reportError(error);
		return fallback;
	}
}

/** Todas las filas de un listado, de 100 en 100 (hasta 20 páginas), para rellenar un selector. */
export async function listAll<T>(
	fetchPage: (params: ListParams) => Promise<Page<T>>,
): Promise<T[]> {
	const first = await fetchPage({ size: 100 });
	const rest = await Promise.all(
		Array.from({ length: Math.min(first.pages, 20) - 1 }, (_, index) =>
			fetchPage({ size: 100, page: index + 2 }),
		),
	);
	return [first, ...rest].flatMap((page) => page.items);
}

/**
 * Cliente de un recurso CRUD del backend (los que monta `Resource.mount`).
 *
 *   export const ProductsApi = crud<Product, ProductCreate>("/products");
 */
export function crud<T, Create, Update = Partial<Create>>(path: string) {
	return {
		list: (params: ListParams = {}) => get<Page<T>>(`${path}/`, params),
		read: (id: string) => get<T>(`${path}/${id}`),
		create: (data: Create, key?: string) => post<T>(`${path}/`, data, key),
		update: (id: string, data: Update, key?: string) => patch<T>(`${path}/${id}`, data, key),
		remove: (id: string) => del<Message>(`${path}/${id}`),
		restore: (id: string) => post<T>(`${path}/${id}/restore`),
		hardDelete: (id: string) => del<Message>(`${path}/${id}/hard`),
	};
}
