const FECHA_HORA = new Intl.DateTimeFormat("es", {
	dateStyle: "short",
	timeStyle: "medium",
});

export function formatDate(value: string | null | undefined): string {
	if (!value) return "—";
	return FECHA_HORA.format(new Date(value));
}

/** "hace 3 min", útil para listas de sesiones y eventos. */
export function timeAgo(value: string | number | null | undefined): string {
	if (!value) return "—";
	const seconds = (Date.now() - new Date(value).getTime()) / 1000;
	const steps: [number, Intl.RelativeTimeFormatUnit][] = [
		[60, "second"],
		[3600, "minute"],
		[86400, "hour"],
		[2592000, "day"],
	];
	const formatter = new Intl.RelativeTimeFormat("es", { numeric: "auto" });
	let previous = 1;
	for (const [limit, unit] of steps) {
		if (seconds < limit) return formatter.format(-Math.round(seconds / previous), unit);
		previous = limit;
	}
	return formatDate(new Date(value).toISOString());
}

/**
 * Valor de un <input type="datetime-local"> (hora del navegador) convertido a ISO en UTC para la API.
 *
 * El campo llega hasta el minuto: con `endOfMinute` el límite superior incluye todo ese minuto.
 */
export function toUtcIso(value: string | null | undefined, endOfMinute = false): string | undefined {
	if (!value) return undefined;
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) return undefined;
	return new Date(date.getTime() + (endOfMinute ? 59_999 : 0)).toISOString();
}

/** Lo contrario de `toUtcIso`: una fecha ISO como valor de un <input type="datetime-local">. */
export function toLocalInput(value: string | null | undefined): string {
	if (!value) return "";
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) return "";
	const pad = (part: number) => String(part).padStart(2, "0");
	const day = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
	return `${day}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** Muestra cualquier valor del historial de forma legible. */
export function showValue(value: unknown): string {
	if (value === null || value === undefined) return "—";
	if (typeof value === "boolean") return value ? "sí" : "no";
	if (typeof value === "object") return JSON.stringify(value);
	return String(value);
}

/** Últimos dígitos de un UUID: la parte que distingue una fila de otra. */
export function shortId(id: string | null | undefined): string {
	return id ? id.slice(-8) : "—";
}
