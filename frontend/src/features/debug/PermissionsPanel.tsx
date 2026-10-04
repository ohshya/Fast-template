import { For, Show, createMemo, createResource, createSignal } from "solid-js";
import { withFallback } from "@/core/api";
import { type PermissionInfo, SystemApi, type SystemInfo } from "@/modules/system";

const SCOPES: Record<string, string> = {
	public: "Sin sesión",
	authenticated: "Cualquier usuario",
	role: "Según el rol",
	dev: "Solo dev",
};

export function PermissionsPanel() {
	const [permisos] = createResource(() =>
		withFallback(SystemApi.permissions(), [] as PermissionInfo[]),
	);
	const [info] = createResource(() => withFallback(SystemApi.info(), null as SystemInfo | null));
	const [soloMios, setSoloMios] = createSignal(false);

	const [buscar, setBuscar] = createSignal("");

	const lista = createMemo(() => {
		const texto = buscar().trim().toLowerCase();
		return (permisos() ?? []).filter(
			(permiso) =>
				(!soloMios() || permiso.granted) &&
				(!texto ||
					`${permiso.id} ${permiso.key} ${permiso.group} ${permiso.description} ${permiso.endpoint ?? ""}`
						.toLowerCase()
						.includes(texto)),
		);
	});

	return (
		<div class="space-y-4">
			<Show when={info()}>
				{(datos) => (
					<div class="stats stats-vertical w-full bg-base-100 shadow-sm sm:stats-horizontal">
						<div class="stat">
							<div class="stat-title">API</div>
							<div class="stat-value text-xl">
								{datos().name} {datos().version}
							</div>
							<div class="stat-desc">{datos().debug ? "modo desarrollo" : "producción"}</div>
						</div>
						<div class="stat">
							<div class="stat-title">Sesiones</div>
							<div class="stat-value text-xl">{datos().max_sessions_per_user}</div>
							<div class="stat-desc">
								acceso {datos().access_expire_minutes} min · refresco {datos().refresh_expire_days} d
							</div>
						</div>
						<div class="stat">
							<div class="stat-title">Permisos</div>
							<div class="stat-value text-xl">{permisos()?.length ?? 0}</div>
							<div class="stat-desc">uno por endpoint</div>
						</div>
					</div>
				)}
			</Show>

			<div class="flex flex-col gap-3 sm:flex-row sm:items-center">
				<input
					type="search"
					class="input input-sm w-full sm:w-80"
					placeholder="Buscar por clave, módulo, endpoint o número"
					aria-label="Buscar permisos"
					value={buscar()}
					onInput={(event) => setBuscar(event.currentTarget.value)}
				/>
				<label class="label cursor-pointer justify-start gap-2">
					<input
						type="checkbox"
						class="toggle toggle-sm"
						checked={soloMios()}
						onChange={(event) => setSoloMios(event.currentTarget.checked)}
					/>
					Ver solo los que tengo
				</label>
				<span class="text-sm opacity-70 sm:ml-auto">
					{lista().length} de {permisos()?.length ?? 0} permisos
				</span>
			</div>

			<div class="overflow-x-auto rounded-box bg-base-100 shadow-sm">
				<table class="table table-sm">
					<thead>
						<tr>
							<th>#</th>
							<th>Clave</th>
							<th>Módulo</th>
							<th>Qué permite</th>
							<th>Endpoint</th>
							<th>Alcance</th>
							<th>¿Lo tengo?</th>
						</tr>
					</thead>
					<tbody>
						<For each={lista()}>
							{(permiso) => (
								<tr>
									<td class="font-mono">{permiso.id}</td>
									<td class="font-mono text-xs">{permiso.key}</td>
									<td>{permiso.group}</td>
									<td class="text-sm">{permiso.description}</td>
									<td class="font-mono text-xs opacity-70">{permiso.endpoint ?? "—"}</td>
									<td class="text-xs">{SCOPES[permiso.scope] ?? permiso.scope}</td>
									<td>
										<span
											class="badge badge-sm"
											classList={{
												"badge-success": permiso.granted,
												"badge-ghost": !permiso.granted,
											}}
										>
											{permiso.granted ? "sí" : "no"}
										</span>
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
