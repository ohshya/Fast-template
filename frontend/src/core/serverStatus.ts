import { createSignal } from "solid-js";
import { handleConnection } from "@/core/api";
import { SystemApi } from "@/modules/system";

const [online, setOnline] = createSignal(true);
const [reason, setReason] = createSignal<string | null>(null);
const [checkedAt, setCheckedAt] = createSignal<number | null>(null);
const [offlineSince, setOfflineSince] = createSignal<number | null>(null);
const [latency, setLatency] = createSignal<number | null>(null);
const [nextCheckAt, setNextCheckAt] = createSignal<number | null>(null);

let timer: ReturnType<typeof setTimeout> | undefined;
let polling = false;
let failures = 0;

/** Estado de la conexión con el servidor, para mostrarlo (barra, pantalla sin conexión, Debug). */
export const serverStatus = {
	online,
	/** Por qué se considera caído, o `null` si responde. */
	reason,
	checkedAt,
	offlineSince,
	/** Milisegundos que tardó la última comprobación de `/system/health`. */
	latency,
	/** Cuándo toca la próxima comprobación automática. */
	nextCheckAt,
};

/** El servidor respondió: lo llama el interceptor de axios con cada respuesta. */
export function markOnline() {
	failures = 0;
	setOnline(true);
	setReason(null);
	setOfflineSince(null);
	setCheckedAt(Date.now());
}

/** El servidor no responde: lo llama el interceptor (sin red, 502/503/504, base de datos caída). */
export function markOffline(why: string) {
	const wasOnline = online();
	if (wasOnline) setOfflineSince(Date.now());
	setOnline(false);
	setReason(why);
	setCheckedAt(Date.now());
	if (wasOnline) schedule();
}

handleConnection(markOnline, markOffline);

/** Pregunta a `/system/health` y apunta lo que tardó. Devuelve si el servidor está sano. */
export async function checkServerStatus(): Promise<boolean> {
	const started = performance.now();
	try {
		await SystemApi.health();
		setLatency(Math.round(performance.now() - started));
		return true;
	} catch {
		setLatency(null);
		return false;
	}
}

/** Con el servidor sano se comprueba cada 15 s; caído, cada 2 s y duplicando hasta 15 s. */
function schedule() {
	clearTimeout(timer);
	if (!polling) return;
	const delay = online() ? 15_000 : Math.min(2_000 * 2 ** failures, 15_000);
	setNextCheckAt(Date.now() + delay);
	timer = setTimeout(async () => {
		if (document.visibilityState === "hidden" && online()) return schedule();
		failures = (await checkServerStatus()) ? 0 : failures + 1;
		schedule();
	}, delay);
}

async function checkNow() {
	failures = (await checkServerStatus()) ? 0 : failures + 1;
	schedule();
}

function onVisible() {
	if (document.visibilityState === "visible") void checkNow();
}

function onBrowserOffline() {
	markOffline("Tu dispositivo no tiene conexión a internet.");
}

/** Empieza a vigilar el servidor, y también los avisos del navegador (pestaña visible, red perdida o recuperada). */
export function startServerStatusPolling() {
	if (polling) return;
	polling = true;
	document.addEventListener("visibilitychange", onVisible);
	window.addEventListener("online", checkNow);
	window.addEventListener("offline", onBrowserOffline);
	void checkNow();
}

export function stopServerStatusPolling() {
	polling = false;
	clearTimeout(timer);
	setNextCheckAt(null);
	document.removeEventListener("visibilitychange", onVisible);
	window.removeEventListener("online", checkNow);
	window.removeEventListener("offline", onBrowserOffline);
}
