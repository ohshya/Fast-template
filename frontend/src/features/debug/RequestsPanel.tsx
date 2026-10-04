import { For, Show, createMemo, createSignal } from "solid-js";
import { notify } from "@/core/notify";
import { type RequestEntry, requestLog } from "@/core/requestLog";

const FILTERS = [
	{ id: "all", title: "Todas" },
	{ id: "errors", title: "Con error" },
	{ id: "writes", title: "Escrituras" },
] as const;

type FilterId = (typeof FILTERS)[number]["id"];

const TIME = new Intl.DateTimeFormat("es", { timeStyle: "medium" });

function statusClass(entry: RequestEntry): string {
	if (entry.status === 0) return "badge-error";
	if (entry.status >= 500) return "badge-error";
	if (entry.status >= 400) return "badge-warning";
	return "badge-success";
}

async function copy(text: string) {
	try {
		await navigator.clipboard.writeText(text);
		notify.info("Copiado");
	} catch {
		notify.error("El navegador no permite copiar aquí");
	}
}

/** Las últimas peticiones a la API: método, ruta con sus parámetros, estado, duración, clave y `request_id`. */
export function RequestsPanel() {
	const [filter, setFilter] = createSignal<FilterId>("all");
	const [text, setText] = createSignal("");
	const [probes, setProbes] = createSignal(false);

	const shown = createMemo(() =>
		requestLog.entries().filter((entry) => {
			if (entry.probe && !probes()) return false;
			if (filter() === "errors" && entry.ok) return false;
			if (filter() === "writes" && entry.method === "GET") return false;
			const needle = text().trim().toLowerCase();
			return !needle || `${entry.method} ${entry.url} ${entry.code ?? ""} ${entry.requestId ?? ""}`.toLowerCase().includes(needle);
		}),
	);

	const summary = createMemo(() => {
		const all = shown();
		const times = all.map((entry) => entry.ms).sort((a, b) => a - b);
		const average = times.length ? Math.round(times.reduce((sum, ms) => sum + ms, 0) / times.length) : 0;
		return {
			total: all.length,
			errors: all.filter((entry) => !entry.ok).length,
			average,
			slowest: times.at(-1) ?? 0,
		};
	});

	return (
		<div class="space-y-3">
			<div class="flex flex-col gap-3 rounded-box bg-base-100 p-3 shadow-sm sm:flex-row sm:flex-wrap sm:items-center">
				<div role="tablist" class="tabs tabs-box tabs-sm">
					<For each={FILTERS}>
						{(item) => (
							<button
								type="button"
								role="tab"
								class="tab"
								classList={{ "tab-active": filter() === item.id }}
								aria-selected={filter() === item.id}
								onClick={() => setFilter(item.id)}
							>
								{item.title}
							</button>
						)}
					</For>
				</div>
				<input
					type="search"
					class="input input-sm w-full sm:w-64"
					placeholder="Buscar por ruta, código o request_id"
					aria-label="Buscar en las peticiones"
					value={text()}
					onInput={(event) => setText(event.currentTarget.value)}
				/>
				<label class="label cursor-pointer gap-2 text-sm">
					<input
						type="checkbox"
						class="toggle toggle-sm"
						checked={probes()}
						onChange={(event) => setProbes(event.currentTarget.checked)}
					/>
					Incluir comprobaciones de estado
				</label>
				<button type="button" class="btn btn-ghost btn-sm sm:ml-auto" onClick={requestLog.clear}>
					Vaciar
				</button>
			</div>

			<p class="text-sm opacity-70" aria-live="polite">
				{summary().total} {summary().total === 1 ? "petición" : "peticiones"} · {summary().errors} con error ·
				media {summary().average} ms · la más lenta {summary().slowest} ms
			</p>

			<div class="overflow-x-auto rounded-box bg-base-100 shadow-sm">
				<table class="table table-xs">
					<thead>
						<tr>
							<th>Hora</th>
							<th>Método</th>
							<th>Ruta</th>
							<th>Estado</th>
							<th class="text-right">ms</th>
							<th>Notas</th>
							<th>request_id</th>
						</tr>
					</thead>
					<tbody>
						<For
							each={shown()}
							fallback={
								<tr>
									<td colspan="7" class="py-6 text-center opacity-60">
										Aún no hay peticiones que mostrar. Usa la aplicación y vuelve.
									</td>
								</tr>
							}
						>
							{(entry) => (
								<tr>
									<td class="whitespace-nowrap font-mono">{TIME.format(entry.at)}</td>
									<td class="font-mono font-semibold">{entry.method}</td>
									<td class="max-w-md break-all font-mono">{entry.url}</td>
									<td class="whitespace-nowrap">
										<span class={`badge badge-sm ${statusClass(entry)}`}>
											{entry.status === 0 ? "sin respuesta" : entry.status}
										</span>
										<Show when={entry.code}>
											<span class="ml-1 font-mono">{entry.code}</span>
										</Show>
									</td>
									<td class="text-right font-mono">{entry.ms}</td>
									<td class="space-x-1">
										<Show when={entry.retried}>
											<span class="badge badge-outline badge-xs" title="Segundo intento tras renovar la sesión">
												reintento
											</span>
										</Show>
										<Show when={entry.replayed}>
											<span class="badge badge-info badge-xs" title="Respuesta guardada: no se volvió a ejecutar">
												repetida
											</span>
										</Show>
										<Show when={entry.key}>
											<span class="badge badge-ghost badge-xs font-mono" title={entry.key ?? ""}>
												clave {entry.key?.slice(0, 6)}…
											</span>
										</Show>
									</td>
									<td>
										<Show when={entry.requestId} fallback="—">
											{(id) => (
												<button
													type="button"
													class="btn btn-ghost btn-xs font-mono"
													title="Copiar el request_id"
													onClick={() => copy(id())}
												>
													{id().slice(-8)}
												</button>
											)}
										</Show>
									</td>
								</tr>
							)}
						</For>
					</tbody>
				</table>
			</div>
		</div>
	);
}
