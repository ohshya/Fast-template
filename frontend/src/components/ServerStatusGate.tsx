import type { RouteSectionProps } from "@solidjs/router";
import { Show, createEffect, on, onCleanup, onMount } from "solid-js";
import { auth } from "@/core/auth";
import { serverStatus, startServerStatusPolling, stopServerStatusPolling } from "@/core/serverStatus";
import Offline from "@/pages/Offline";

/**
 * Vigila la conexión con el servidor para toda la aplicación.
 *
 * Mientras no responde, tapa todo con la pantalla sin conexión y deja lo de debajo inerte;
 * al volver, `auth.recover()` termina lo que quedó pendiente (un cierre de sesión, la lectura
 * de la sesión al arrancar).
 */
export function ServerStatusGate(props: RouteSectionProps) {
	onMount(startServerStatusPolling);
	onCleanup(stopServerStatusPolling);

	createEffect(
		on(
			serverStatus.online,
			(online, was) => {
				if (online && was === false) void auth.recover();
			},
			{ defer: true },
		),
	);

	return (
		<>
			<div class="contents" inert={!serverStatus.online()}>
				{props.children}
			</div>
			<Show when={!serverStatus.online()}>
				<Offline />
			</Show>
		</>
	);
}
