import toast from "solid-toast";
import type { ErrorPayload } from "@/core/api";

const OPTIONS = { duration: 4000, position: "top-right" } as const;

/** Texto de un error de la API: el mensaje, el código y, si lo hay, cuánto esperar o qué petición fue. */
function describe(error: ErrorPayload): string {
	const wait = error.details.retry_after_seconds;
	const advice = typeof wait === "number" ? ` Espera ${wait} s.` : "";
	const trace =
		(error.severity === "error" || error.severity === "critical") && error.request_id !== "-"
			? ` · ${error.request_id}`
			: "";
	return `${error.message}${advice} (${error.code}${trace})`;
}

export const notify = {
	success(message: string) {
		toast.success(message, OPTIONS);
	},
	error(message: string) {
		toast.error(message, OPTIONS);
	},
	warning(message: string) {
		toast(message, { ...OPTIONS, icon: "⚠️" });
	},
	info(message: string) {
		toast(message, OPTIONS);
	},
	/** Muestra un error de la API respetando su gravedad. */
	fromApi(error: ErrorPayload) {
		const text = describe(error);
		if (error.severity === "info") return toast(text, OPTIONS);
		if (error.severity === "warning") return this.warning(text);
		return this.error(text);
	},
};
