import { FiWifiOff } from "solid-icons/fi";
import { createSignal, onCleanup, onMount } from "solid-js";
import { timeAgo } from "@/core/format";
import { checkServerStatus, serverStatus } from "@/core/serverStatus";

/**
 * Pantalla que tapa la aplicación mientras el servidor no responde.
 *
 * Lo pinta `ServerStatusGate`; la aplicación de debajo sigue montada (no se pierde un
 * formulario a medias) pero inerte. Vuelve a comprobar sola y se quita al responder el servidor.
 */
export default function Offline() {
	const [checking, setChecking] = createSignal(false);
	const [now, setNow] = createSignal(Date.now());
	const tick = setInterval(() => setNow(Date.now()), 1000);
	let retryButton: HTMLButtonElement | undefined;
	onMount(() => retryButton?.focus());
	onCleanup(() => clearInterval(tick));

	const seconds = () => Math.max(0, Math.ceil(((serverStatus.nextCheckAt() ?? now()) - now()) / 1000));

	async function retry() {
		setChecking(true);
		try {
			await checkServerStatus();
		} finally {
			setChecking(false);
		}
	}

	return (
		<div
			role="alertdialog"
			aria-modal="true"
			aria-labelledby="offline-title"
			aria-describedby="offline-reason"
			class="fixed inset-0 z-100 flex items-center justify-center bg-base-200/95 p-4 backdrop-blur-sm"
		>
			<div class="w-full max-w-sm text-center">
				<FiWifiOff size={56} class="mx-auto text-error" aria-hidden="true" />
				<h1 id="offline-title" class="mt-4 text-2xl font-bold">
					Sin conexión con el servidor
				</h1>
				<p id="offline-reason" class="mt-2 text-sm opacity-70">
					{serverStatus.reason() ?? "El servidor no responde."}
				</p>
				<p class="mt-1 text-xs opacity-50" aria-live="polite">
					Sin conexión desde {timeAgo(serverStatus.offlineSince())}. Próximo intento en {seconds()} s.
				</p>
				<button
					ref={retryButton}
					type="button"
					class="btn btn-primary mt-6 gap-2"
					disabled={checking()}
					onClick={retry}
				>
					{checking() ? <span class="loading loading-spinner loading-sm" /> : null}
					{checking() ? "Comprobando..." : "Reintentar ahora"}
				</button>
				<p class="mt-4 text-xs opacity-50">Lo que tenías abierto se conserva: al volver la conexión sigues donde estabas.</p>
			</div>
		</div>
	);
}
