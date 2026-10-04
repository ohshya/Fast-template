import { createSignal } from "solid-js";
import { ApiError, newKey, reportError } from "@/core/api";

/**
 * Estado de un formulario: valores, errores por campo, si se está guardando y la clave de idempotencia.
 *
 *   const form = createForm({ name: "" });
 *   const ok = await form.submit((values, key) => ProductsApi.create(values, key));
 *
 * Si la API responde con error, `errors()` recibe sus `fields` y `submit` devuelve false.
 *
 * El formulario custodia la `Idempotency-Key` (ver `core/idempotency.md`): la mantiene
 * mientras no sepa qué pasó con el envío (sin respuesta, 5xx o `IDM_001`) para que un
 * reintento no duplique la escritura, y la cambia al editar un campo, al terminar con
 * respuesta definitiva y al reiniciar.
 */
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
				} else {
					reportError(error);
				}
				return false;
			} finally {
				setSaving(false);
			}
		},
	};
}
