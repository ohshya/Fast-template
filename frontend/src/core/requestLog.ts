import { createSignal } from "solid-js";

export type RequestEntry = {
	id: number;
	at: number;
	method: string;
	url: string;
	/** 0 si no hubo respuesta (sin red). */
	status: number;
	ms: number;
	ok: boolean;
	/** Código de error de la API, si lo hubo. */
	code: string | null;
	requestId: string | null;
	/** `Idempotency-Key` que llevaba la petición. */
	key: string | null;
	/** La respuesta es una copia guardada (`Idempotent-Replayed`). */
	replayed: boolean;
	/** Segundo intento tras renovar la sesión. */
	retried: boolean;
	/** Comprobación de estado del servidor, no una acción del usuario. */
	probe: boolean;
};

let counter = 0;
const [entries, setEntries] = createSignal<RequestEntry[]>([]);

/** Últimas 150 peticiones a la API, las más recientes primero. Las alimenta el interceptor de `core/api.ts`. */
export const requestLog = {
	entries,

	record(entry: Omit<RequestEntry, "id">) {
		counter += 1;
		setEntries((current) => [{ id: counter, ...entry }, ...current].slice(0, 150));
	},

	clear() {
		setEntries([]);
	},
};
