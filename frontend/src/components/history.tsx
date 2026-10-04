import { For, Show, batch, createResource, createSignal } from "solid-js";
import { Modal } from "@/components/ui";
import { type Page, withFallback } from "@/core/api";
import { formatDate, showValue } from "@/core/format";
import { type AuditEventDetail, type Change, EVENT_ACTIONS, EventsApi } from "@/modules/events";

const PAGE_SIZE = 10;

/** Tabla de cambios de un evento: cada campo con su valor anterior y el nuevo. */
export function ChangesTable(props: { changes: Record<string, Change> }) {
	return (
		<div class="overflow-x-auto">
			<table class="table table-xs">
				<thead>
					<tr>
						<th>Campo</th>
						<th>Antes</th>
						<th>Después</th>
					</tr>
				</thead>
				<tbody>
					<For each={Object.entries(props.changes)}>
						{([campo, cambio]) => (
							<tr>
								<td class="font-medium">{campo}</td>
								<td class="text-error">{showValue(cambio.before)}</td>
								<td class="text-success">{showValue(cambio.after)}</td>
							</tr>
						)}
					</For>
				</tbody>
			</table>
		</div>
	);
}

type Target = { type: string; id: string; label: string };

const EMPTY: Page<AuditEventDetail> = { items: [], total: 0, page: 1, size: PAGE_SIZE, pages: 0 };

/**
 * Historial de cambios de un registro en un diálogo.
 *
 *   const history = createHistory();
 *   <button onClick={() => history.open("users", user.id, user.username)}>Historial</button>
 *   <history.Dialog />
 */
export function createHistory() {
	const [target, setTarget] = createSignal<Target | null>(null);
	const [page, setPage] = createSignal(1);
	const [data] = createResource(
		() => {
			const actual = target();
			return actual ? { ...actual, page: page() } : false;
		},
		(fuente) =>
			withFallback(
				EventsApi.history(fuente.type, fuente.id, { page: fuente.page, size: PAGE_SIZE }),
				EMPTY,
			),
	);

	function open(type: string, id: string, label: string) {
		batch(() => {
			setPage(1);
			setTarget({ type, id, label });
		});
	}

	function Dialog() {
		const paginas = () => Math.max(data.latest?.pages ?? 1, 1);
		return (
			<Modal
				open={target() !== null}
				title={`Historial de ${target()?.label ?? ""}`}
				subtitle="Cada cambio queda firmado en el registro de eventos."
				width="max-w-3xl"
				onClose={() => setTarget(null)}
			>
				<Show when={!data.loading} fallback={<span class="loading loading-spinner" />}>
					<ul class="space-y-3">
						<For
							each={data.latest?.items}
							fallback={<li class="opacity-60">No hay cambios registrados.</li>}
						>
							{(evento) => (
								<li class="space-y-2 rounded-box border border-base-300 p-3">
									<div class="flex flex-wrap items-center gap-2 text-sm">
										<span class="badge badge-sm">{EVENT_ACTIONS[evento.action] ?? evento.action}</span>
										<span class="font-medium">{evento.actor_username ?? "Sistema"}</span>
										<span class="opacity-60">{formatDate(evento.created_at)}</span>
									</div>
									<Show when={evento.changes}>
										{(cambios) => <ChangesTable changes={cambios()} />}
									</Show>
								</li>
							)}
						</For>
					</ul>
				</Show>
				<Show when={paginas() > 1}>
					<div class="join mt-4 flex justify-center">
						<button
							type="button"
							class="join-item btn btn-sm"
							disabled={page() <= 1}
							onClick={() => setPage(page() - 1)}
						>
							«
						</button>
						<span class="join-item btn btn-sm pointer-events-none">
							{page()} / {paginas()}
						</span>
						<button
							type="button"
							class="join-item btn btn-sm"
							disabled={page() >= paginas()}
							onClick={() => setPage(page() + 1)}
						>
							»
						</button>
					</div>
				</Show>
			</Modal>
		);
	}

	return { open, Dialog };
}

export type History = ReturnType<typeof createHistory>;
