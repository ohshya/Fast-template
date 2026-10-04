import { createSignal } from "solid-js";
import {
	ApiError,
	handlePermissionDenied,
	handleSessionLost,
	isUnreachable,
	reportError,
	withFallback,
} from "@/core/api";
import { APP_NAME } from "@/core/app";
import { notify } from "@/core/notify";
import { AuthApi, type Me } from "@/modules/auth";
import { SystemApi, type SystemInfo } from "@/modules/system";

const [user, setUser] = createSignal<Me | null>(null);
const [loading, setLoading] = createSignal(true);
const [expired, setExpired] = createSignal(false);
const [info, setInfo] = createSignal<SystemInfo | null>(null);

type SessionMessage = "login" | "logout" | "expired";

const channel = typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel(`${APP_NAME}-session`);
let checkedAt = 0;

const PENDING_KEY = `${APP_NAME}-pending-logout`;

function storedPending(): boolean {
	try {
		return localStorage.getItem(PENDING_KEY) === "1";
	} catch {
		return false;
	}
}

/** Un cierre de sesión que no llegó al servidor se recuerda aunque se recargue la página. */
const [pendingLogout, setPendingLogout] = createSignal(storedPending());

function markPending(value: boolean) {
	setPendingLogout(value);
	try {
		if (value) localStorage.setItem(PENDING_KEY, "1");
		else localStorage.removeItem(PENDING_KEY);
	} catch {
		return;
	}
}

/** Cierra la sesión en el servidor. Devuelve `false` si no se pudo (sin conexión): queda pendiente. */
async function closeOnServer(): Promise<boolean> {
	try {
		await AuthApi.logout();
	} catch (error) {
		if (isUnreachable(error)) {
			markPending(true);
			return false;
		}
		if (!(error instanceof ApiError)) reportError(error);
	}
	markPending(false);
	return true;
}

let reading: Promise<boolean> | null = null;

/**
 * Lee otra vez quién es el usuario y las políticas del servidor, una sola lectura a la vez.
 *
 * Devuelve `false` si el servidor no respondió (sin red, 502/503/504): la sesión que ya hay
 * no se toca. Un 401 lo gestiona el interceptor.
 */
function readSession(): Promise<boolean> {
	reading ??= (async () => {
		checkedAt = Date.now();
		try {
			setUser(await AuthApi.me());
			setExpired(false);
		} catch (error) {
			if (isUnreachable(error)) return false;
			reportError(error);
			return true;
		}
		setInfo(await withFallback(SystemApi.info(), info()));
		return true;
	})().finally(() => {
		reading = null;
	});
	return reading;
}

function leave(wasExpired: boolean) {
	setUser(null);
	setLoading(false);
	setExpired(wasExpired);
}

export const auth = {
	user,
	loading,
	/** Si la sesión se perdió sola (caducó o la cerraron desde otro sitio) en vez de salir el usuario. */
	expired,
	/** Políticas del servidor (`/system/info`): longitud de contraseña, si está en modo desarrollo... */
	info,
	isLoggedIn: () => user() !== null,
	isDev: () => user()?.dev === true,

	/** Si el usuario tiene el permiso con esta clave, p. ej. "users.create". Los dev pueden con todo. */
	can(key: string) {
		const actual = user();
		if (!actual) return false;
		return actual.dev || actual.permission_keys.includes(key);
	},

	/** Si el usuario tiene al menos uno de estos permisos. */
	canAny(...keys: string[]) {
		return keys.some((key) => this.can(key));
	},

	/** Si el usuario puede conceder este permiso (por id): un dev todos, el resto solo los suyos. */
	canGrant(id: number) {
		const actual = user();
		return !!actual && (actual.dev || actual.permissions.includes(id));
	},

	/** Texto de ayuda de un campo de contraseña nueva, con la longitud mínima que exige el servidor. */
	passwordHint() {
		const minimum = info()?.password_min_length ?? 8;
		return `Mínimo ${minimum} caracteres, con una letra y un número, sin espacios al principio ni al final`;
	},

	/** Hay un cierre de sesión que aún no llegó al servidor (se cerró sin conexión). */
	pendingLogout,

	/**
	 * Comprueba si hay sesión abierta. Se llama una vez al arrancar.
	 *
	 * Si el servidor no responde, `loading` sigue en `true` (la pantalla sin conexión tapa la
	 * espera) hasta que `recover` lo reintente; con un cierre de sesión pendiente no se lee la
	 * sesión: seguiría abierta en el servidor.
	 */
	async load() {
		setLoading(true);
		if (pendingLogout() && !(await closeOnServer())) {
			leave(false);
			return;
		}
		if (await readSession()) setLoading(false);
	},

	/** El servidor vuelve a responder: termina el cierre pendiente o completa la carga que quedó a medias. */
	async recover() {
		if (pendingLogout()) await closeOnServer();
		else if (loading()) await this.load();
		else if (user()) await readSession();
	},

	/** Vuelve a leer los datos y permisos sin mostrar la pantalla de carga. */
	async refresh() {
		await readSession();
	},

	/** Vuelve a leerlos si hace más de un minuto de la última vez: al volver a la pestaña o ante un 403. */
	async refreshIfStale() {
		if (user() && Date.now() - checkedAt > 60_000) await readSession();
	},

	async login(username: string, password: string) {
		const me = await AuthApi.login(username, password);
		markPending(false);
		setExpired(false);
		setUser(me);
		checkedAt = Date.now();
		setInfo(await withFallback(SystemApi.info(), info()));
		channel?.postMessage("login" satisfies SessionMessage);
	},

	async logout() {
		const closed = await closeOnServer();
		leave(false);
		channel?.postMessage("logout" satisfies SessionMessage);
		if (!closed) {
			notify.warning("Saliste en este equipo; la sesión se cerrará en el servidor cuando vuelva la conexión.");
		}
	},

	/** Limpia la sesión en memoria (no llama al servidor) y avisa a las demás pestañas. */
	clear() {
		leave(false);
		channel?.postMessage("logout" satisfies SessionMessage);
	},
};

handleSessionLost(() => {
	const hadSession = user() !== null;
	leave(hadSession);
	if (hadSession) channel?.postMessage("expired" satisfies SessionMessage);
});

handlePermissionDenied(() => {
	void auth.refresh();
});

channel?.addEventListener("message", (event: MessageEvent<SessionMessage>) => {
	if (event.data === "login") void auth.refresh();
	else if (user()) leave(event.data === "expired");
});

document.addEventListener("visibilitychange", () => {
	if (document.visibilityState === "visible") void auth.refreshIfStale();
});
