import { IoEye, IoEyeOff } from "solid-icons/io";
import {
	type JSX,
	Show,
	createSignal,
	createUniqueId,
	onCleanup,
	onMount,
	splitProps,
} from "solid-js";
import { reportError } from "@/core/api";

type FieldProps = JSX.InputHTMLAttributes<HTMLInputElement> & {
	label?: string;
	error?: string;
	hint?: string;
	loading?: boolean;
	required?: boolean;
};

const FIELD_PROPS = ["label", "error", "hint", "loading", "required"] as const;

/** Etiqueta, mensaje de error o ayuda de un campo; `id` es el del campo, del que cuelgan los demás. */
function Field(props: {
	id: string;
	label?: string;
	required?: boolean;
	error?: string;
	hint?: string;
	children: JSX.Element;
}) {
	return (
		<fieldset class="fieldset w-full">
			{props.label && (
				<legend id={`${props.id}-label`} class="fieldset-legend">
					{props.label}
					{props.required && <span class="text-error">*</span>}
				</legend>
			)}
			{props.children}
			{props.error ? (
				<p id={`${props.id}-note`} role="alert" class="label text-error">
					{props.error}
				</p>
			) : (
				props.hint && (
					<p id={`${props.id}-note`} class="label">
						{props.hint}
					</p>
				)
			)}
		</fieldset>
	);
}

/** Atributos de accesibilidad que unen un campo con su etiqueta y su mensaje. */
function describe(id: string, props: { label?: string; error?: string; hint?: string }) {
	return {
		"aria-labelledby": props.label ? `${id}-label` : undefined,
		"aria-describedby": props.error || props.hint ? `${id}-note` : undefined,
		"aria-invalid": props.error ? true : undefined,
	} as const;
}

/** Campo de formulario de daisyUI con etiqueta, error y ayuda. */
export function Input(allProps: FieldProps) {
	const [props, inputProps] = splitProps(allProps, FIELD_PROPS);
	const id = inputProps.id ?? createUniqueId();

	return (
		<Field id={id} label={props.label} required={props.required} error={props.error} hint={props.hint}>
			<input
				type="text"
				class="input w-full"
				classList={{ "input-error": !!props.error }}
				disabled={props.loading || inputProps.disabled}
				{...inputProps}
				id={id}
				{...describe(id, props)}
			/>
		</Field>
	);
}

/** Campo de contraseña con botón para mostrarla u ocultarla. */
export function PasswordInput(allProps: FieldProps) {
	const [visible, setVisible] = createSignal(false);
	const [props, inputProps] = splitProps(allProps, FIELD_PROPS);
	const id = inputProps.id ?? createUniqueId();

	return (
		<Field id={id} label={props.label} required={props.required} error={props.error} hint={props.hint}>
			<div class="join w-full">
				<input
					type={visible() ? "text" : "password"}
					class="input join-item grow"
					classList={{ "input-error": !!props.error }}
					disabled={props.loading || inputProps.disabled}
					{...inputProps}
					id={id}
					{...describe(id, props)}
				/>
				<button
					type="button"
					class="btn join-item"
					disabled={props.loading}
					onClick={() => setVisible((value) => !value)}
					aria-label={visible() ? "Ocultar contraseña" : "Mostrar contraseña"}
					aria-pressed={visible()}
				>
					{visible() ? <IoEyeOff /> : <IoEye />}
				</button>
			</div>
		</Field>
	);
}

type ModalProps = {
	open: boolean;
	title: string;
	subtitle?: string;
	onClose: () => void;
	children: JSX.Element;
	actions?: JSX.Element;
	width?: string;
};

const FOCUSABLE =
	'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Diálogo abierto: se anuncia como diálogo modal, recibe el foco al abrirse, lo mantiene
 * dentro con Tab, se cierra con Escape y devuelve el foco a quien lo abrió.
 */
function ModalDialog(props: ModalProps) {
	const titleId = createUniqueId();
	const opener = document.activeElement;
	let box: HTMLDivElement | undefined;

	const focusable = () => [...(box?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])];

	onMount(() => (focusable()[0] ?? box)?.focus());
	onCleanup(() => {
		if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
	});

	function onKeyDown(event: KeyboardEvent) {
		if (event.key === "Escape") {
			event.stopPropagation();
			props.onClose();
			return;
		}
		if (event.key !== "Tab") return;
		const items = focusable();
		const first = items[0];
		const last = items[items.length - 1];
		if (!first || !last) return event.preventDefault();
		if (event.shiftKey && document.activeElement === first) {
			event.preventDefault();
			last.focus();
		} else if (!event.shiftKey && document.activeElement === last) {
			event.preventDefault();
			first.focus();
		}
	}

	return (
		<div class="modal modal-open" onKeyDown={onKeyDown}>
			<div
				ref={box}
				role="dialog"
				aria-modal="true"
				aria-labelledby={titleId}
				tabindex="-1"
				class="modal-box"
				classList={{ [props.width ?? "max-w-lg"]: true }}
			>
				<h3 id={titleId} class="text-lg font-bold">
					{props.title}
				</h3>
				<Show when={props.subtitle}>
					<p class="text-sm opacity-70">{props.subtitle}</p>
				</Show>
				<div class="py-4">{props.children}</div>
				<Show when={props.actions}>
					<div class="modal-action">{props.actions}</div>
				</Show>
			</div>
			<button
				type="button"
				class="modal-backdrop"
				tabindex="-1"
				aria-label="Cerrar"
				onClick={props.onClose}
			/>
		</div>
	);
}

/** Diálogo de daisyUI. Se monta solo cuando está abierto. */
export function Modal(props: ModalProps) {
	return (
		<Show when={props.open}>
			<ModalDialog {...props} />
		</Show>
	);
}

export type ConfirmRequest = {
	title: string;
	message: string;
	confirmLabel?: string;
	danger?: boolean;
	action: () => Promise<unknown>;
};

/**
 * Confirmación reutilizable.
 *
 *   const confirm = createConfirm();
 *   <button onClick={() => confirm.ask({ ... })}>Eliminar</button>
 *   <confirm.Dialog />
 *
 * Si la acción falla, el diálogo se queda abierto (el aviso ya lo dio la API).
 */
export function createConfirm() {
	const [request, setRequest] = createSignal<ConfirmRequest | null>(null);
	const [working, setWorking] = createSignal(false);

	async function accept() {
		const current = request();
		if (!current) return;
		setWorking(true);
		try {
			await current.action();
			setRequest(null);
		} catch (error) {
			reportError(error);
		} finally {
			setWorking(false);
		}
	}

	function Dialog() {
		return (
			<Modal
				open={request() !== null}
				title={request()?.title ?? ""}
				onClose={() => setRequest(null)}
				actions={
					<>
						<button type="button" class="btn btn-ghost" onClick={() => setRequest(null)}>
							Cancelar
						</button>
						<button
							type="button"
							class="btn"
							classList={{
								"btn-error": request()?.danger !== false,
								"btn-primary": request()?.danger === false,
							}}
							disabled={working()}
							onClick={accept}
						>
							{working() ? "Un momento..." : (request()?.confirmLabel ?? "Confirmar")}
						</button>
					</>
				}
			>
				<p>{request()?.message}</p>
			</Modal>
		);
	}

	return { ask: setRequest, Dialog };
}

export type Confirm = ReturnType<typeof createConfirm>;

/** Título de página con subtítulo opcional y acciones a la derecha. */
export function PageHeader(props: { title: string; subtitle?: string; children?: JSX.Element }) {
	return (
		<div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
			<div>
				<h1 class="text-2xl font-bold">{props.title}</h1>
				<Show when={props.subtitle}>
					<p class="text-sm opacity-60">{props.subtitle}</p>
				</Show>
			</div>
			<div class="flex flex-wrap gap-2">{props.children}</div>
		</div>
	);
}
