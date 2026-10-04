import { For, Show } from "solid-js";
import { formatDate, timeAgo } from "@/core/format";
import type { Session } from "@/modules/auth";

/** Sesiones abiertas de una cuenta; con `onClose`, cada una trae su botón de cerrar. */
export function SessionList(props: { sessions: Session[]; onClose?: (session: Session) => void }) {
	return (
		<ul class="divide-y divide-base-300">
			<For each={props.sessions} fallback={<li class="py-3 text-sm">Sin sesiones.</li>}>
				{(session) => (
					<li class="flex items-center justify-between gap-2 py-3">
						<div class="min-w-0">
							<p class="truncate text-sm font-medium" title={session.device}>
								{session.device}
								<Show when={session.is_current}>
									<span class="badge badge-success badge-xs ml-2">actual</span>
								</Show>
							</p>
							<p class="text-xs opacity-60">
								{session.ip_address ?? "sin IP"} · activa {timeAgo(session.last_activity)} · caduca{" "}
								{formatDate(session.expires_at)}
							</p>
						</div>
						<Show when={props.onClose}>
							{(close) => (
								<button
									type="button"
									class="btn btn-ghost btn-xs text-error"
									onClick={() => close()(session)}
								>
									Cerrar
								</button>
							)}
						</Show>
					</li>
				)}
			</For>
		</ul>
	);
}
