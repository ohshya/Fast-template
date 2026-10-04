import { Show } from "solid-js";
import { auth } from "@/core/auth";
import { serverStatus } from "@/core/serverStatus";

/** Indicador de la barra superior: servidor (con su latencia) y si hay un cierre de sesión pendiente. */
export function StatusBadge() {
	const label = () => {
		if (!serverStatus.online()) return "Sin conexión con el servidor";
		const latency = serverStatus.latency();
		return latency === null ? "Servidor en línea" : `Servidor en línea (${latency} ms)`;
	};

	return (
		<div class="tooltip tooltip-bottom" data-tip={label()}>
			<span class="badge badge-ghost gap-2" role="status" aria-label={label()}>
				<span
					class="status"
					classList={{
						"status-success": serverStatus.online(),
						"status-error": !serverStatus.online(),
					}}
				/>
				<span class="hidden sm:inline">
					<Show when={serverStatus.online()} fallback="Sin conexión">
						<Show when={serverStatus.latency() !== null} fallback="En línea">
							{serverStatus.latency()} ms
						</Show>
					</Show>
				</span>
				<Show when={auth.pendingLogout()}>
					<span class="badge badge-warning badge-xs">cierre pendiente</span>
				</Show>
			</span>
		</div>
	);
}
