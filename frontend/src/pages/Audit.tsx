import { For, Show, createResource, createSignal } from "solid-js";
import {
	FilterSelect,
	FilterText,
	ListTable,
	ListToolbar,
	Pagination,
	RangeFilter,
	createCrudList,
} from "@/components/crud";
import { ChangesTable } from "@/components/history";
import { Can, NoAccess } from "@/components/layout";
import { Modal, PageHeader } from "@/components/ui";
import { withFallback } from "@/core/api";
import { auth } from "@/core/auth";
import { formatDate, shortId } from "@/core/format";
import { LIMITS } from "@/core/limits";
import { notify } from "@/core/notify";
import {
	type AuditEventDetail,
	EVENT_ACTIONS,
	EVENT_CATEGORIES,
	EVENT_SEVERITIES,
	EventsApi,
	type EventStats,
	type VerifyParams,
} from "@/modules/events";

const CATEGORY_BADGES: Record<string, string> = {
	domain: "badge-info",
	security: "badge-warning",
	error: "badge-error",
	system: "badge-ghost",
};

const CATEGORIES = Object.entries(EVENT_CATEGORIES).map(([value, label]) => ({ value, label }));
const ACTIONS = Object.entries(EVENT_ACTIONS).map(([value, label]) => ({ value, label }));
const SEVERITIES = EVENT_SEVERITIES.map((value) => ({ value, label: value }));
const ORDERS = [{ value: "oldest", label: "Más antiguos primero" }];

/** Registro de eventos: cambios de datos, seguridad, errores y sistema, con filtros e integridad. */
export default function Audit() {
	const list = createCrudList(EventsApi.list, {
		trash: false,
		enabled: () => auth.can("events.list"),
	});
	const [stats, { refetch: refetchStats }] = createResource(
		() => auth.can("events.stats"),
		() => withFallback(EventsApi.stats(), null as EventStats | null),
	);
	const [detail, setDetail] = createSignal<AuditEventDetail | null>(null);
	const [verifying, setVerifying] = createSignal(false);

	function refresh() {
		list.refetch();
		refetchStats();
	}

	async function openDetail(id: string) {
		if (auth.can("events.read")) setDetail(await withFallback(EventsApi.read(id), null));
	}

	async function verify(params: VerifyParams) {
		if (params.date_from && params.date_to && params.date_from > params.date_to) {
			return notify.warning("«Desde» es posterior a «Hasta»: no hay periodo que verificar.");
		}
		setVerifying(true);
		const report = await withFallback(EventsApi.verify(params), null);
		setVerifying(false);
		if (!report) return;
		const unprotected = report.append_only ? "" : " Además, la base ya no impide modificar los eventos.";
		if (!report.intact) notify.error(report.detail + unprotected);
		else if (unprotected) notify.warning(report.detail + unprotected);
		else notify.success(report.detail);
	}

	const from = () => String(list.filters().date_from ?? "") || undefined;
	const to = () => String(list.filters().date_to ?? "") || undefined;

	return (
		<Can permission="events.list" fallback={<NoAccess />}>
			<PageHeader title="Auditoría" subtitle="Todo lo que ocurre en el sistema, firmado y encadenado.">
				<button type="button" class="btn btn-ghost btn-sm" onClick={refresh}>
					Actualizar
				</button>
				<Can permission="events.verify">
					<button
						type="button"
						class="btn btn-sm"
						disabled={verifying()}
						onClick={() => verify({ date_from: from(), date_to: to() })}
					>
						{from() || to() ? "Verificar el periodo" : "Verificar integridad"}
					</button>
				</Can>
			</PageHeader>

			<Show when={stats()}>
				{(data) => (
					<div class="flex flex-wrap items-center gap-2">
						<span class="badge badge-neutral">{data().total} eventos</span>
						<For each={Object.entries(data().by_category)}>
							{([category, total]) => (
								<button
									type="button"
									class={`badge ${CATEGORY_BADGES[category] ?? "badge-ghost"}`}
									onClick={() => list.filter("category", category)}
								>
									{EVENT_CATEGORIES[category as keyof typeof EVENT_CATEGORIES] ?? category}: {total}
								</button>
							)}
						</For>
					</div>
				)}
			</Show>

			<ListToolbar list={list} placeholder="Buscar en el mensaje" maxLength={LIMITS.label}>
				<FilterSelect list={list} name="category" label="Todas las categorías" options={CATEGORIES} />
				<FilterSelect list={list} name="action" label="Todas las acciones" options={ACTIONS} />
				<FilterSelect list={list} name="severity" label="Cualquier gravedad" options={SEVERITIES} />
				<FilterSelect list={list} name="order" label="Más recientes primero" options={ORDERS} />
				<div class="grid w-full gap-2 sm:grid-cols-3">
					<FilterText list={list} name="actor_username" label="Usuario" maxLength={LIMITS.username} />
					<FilterText
						list={list}
						name="entity_type"
						label="Tabla (users, roles...)"
						maxLength={LIMITS.identifier}
					/>
					<FilterText list={list} name="error_code" label="Código de error" maxLength={LIMITS.errorCode} />
				</div>
				<div class="flex w-full flex-wrap items-center gap-x-6 gap-y-2">
					<RangeFilter list={list} name="date" label="Fecha" />
					<label class="label cursor-pointer gap-2 text-sm">
						<input
							type="checkbox"
							class="checkbox checkbox-sm"
							checked={list.filters().only_changes === true}
							onChange={(event) =>
								list.filter("only_changes", event.currentTarget.checked ? true : undefined)
							}
						/>
						Solo cambios de datos
					</label>
				</div>
			</ListToolbar>

			<ListTable
				list={list}
				columns={7}
				empty="No hay eventos."
				class="table-zebra"
				head={
					<>
						<th>#</th>
						<th>Fecha</th>
						<th>Categoría</th>
						<th>Acción</th>
						<th>Mensaje</th>
						<th>Usuario</th>
						<th>Registro</th>
					</>
				}
			>
				<For each={list.items()}>
					{(event) => (
						<tr
							classList={{ "cursor-pointer hover:bg-base-200": auth.can("events.read") }}
							tabindex={auth.can("events.read") ? 0 : undefined}
							onClick={() => openDetail(event.id)}
							onKeyDown={(key) => key.key === "Enter" && openDetail(event.id)}
						>
							<td class="font-mono text-xs opacity-50">{event.sequence}</td>
							<td class="whitespace-nowrap text-xs">{formatDate(event.created_at)}</td>
							<td>
								<span class={`badge badge-sm ${CATEGORY_BADGES[event.category] ?? "badge-ghost"}`}>
									{EVENT_CATEGORIES[event.category] ?? event.category}
								</span>
							</td>
							<td class="text-xs">{EVENT_ACTIONS[event.action] ?? event.action}</td>
							<td class="max-w-md text-sm">{event.message}</td>
							<td class="text-xs">{event.actor_username ?? "—"}</td>
							<td class="text-xs opacity-70">
								{event.entity_type ? `${event.entity_type} ${shortId(event.entity_id)}` : "—"}
								<Show when={event.error_code}>
									<span class="badge badge-error badge-xs ml-1">{event.error_code}</span>
								</Show>
							</td>
						</tr>
					)}
				</For>
			</ListTable>

			<Pagination list={list} />

			<Modal
				open={detail() !== null}
				title={`Evento ${detail()?.sequence ?? ""}`}
				subtitle={detail()?.message}
				width="max-w-3xl"
				onClose={() => setDetail(null)}
			>
				<Show when={detail()}>
					{(event) => (
						<div class="space-y-4 text-sm">
							<div class="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
								<Field title="Fecha" value={formatDate(event().created_at)} />
								<Field title="Categoría" value={event().category} />
								<Field title="Acción" value={event().action} />
								<Field title="Gravedad" value={event().severity} />
								<Field title="Usuario" value={event().actor_username ?? "—"} />
								<Field title="Rol en ese momento" value={shortId(event().actor_role_id)} />
								<Field title="Endpoint" value={`${event().method ?? ""} ${event().path ?? ""}`} />
								<Field title="Permiso" value={String(event().permission_id ?? "—")} />
								<Field title="Petición" value={event().request_id ?? "—"} />
								<Field title="IP" value={event().ip ?? "—"} />
								<Field title="Código de error" value={event().error_code ?? "—"} />
								<Field
									title="Integridad"
									value={event().is_intact ? "firma correcta" : "¡firma alterada!"}
								/>
							</div>
							<Show when={event().changes}>
								{(changes) => (
									<div>
										<h4 class="mb-1 font-semibold">Cambios</h4>
										<ChangesTable changes={changes()} />
									</div>
								)}
							</Show>
							<Show when={event().snapshot}>
								<details>
									<summary class="cursor-pointer font-semibold">Estado tras el cambio</summary>
									<pre class="mt-2 overflow-x-auto rounded-box bg-base-200 p-2 text-xs">
										{JSON.stringify(event().snapshot, null, 2)}
									</pre>
								</details>
							</Show>
							<Show when={event().context}>
								<details>
									<summary class="cursor-pointer font-semibold">Contexto del error</summary>
									<pre class="mt-2 overflow-x-auto rounded-box bg-base-200 p-2 text-xs">
										{JSON.stringify(event().context, null, 2)}
									</pre>
								</details>
							</Show>
							<p class="break-all font-mono text-xs opacity-50">
								hash {event().hash}
								<br />
								anterior {event().prev_hash ?? "—"}
							</p>
							<Can permission="events.verify">
								<button
									type="button"
									class="btn btn-sm"
									disabled={verifying()}
									onClick={() => verify({ event_id: event().id })}
								>
									Verificar en la cadena
								</button>
							</Can>
						</div>
					)}
				</Show>
			</Modal>
		</Can>
	);
}

function Field(props: { title: string; value: string }) {
	return (
		<div>
			<p class="text-xs opacity-60">{props.title}</p>
			<p class="break-all">{props.value}</p>
		</div>
	);
}
