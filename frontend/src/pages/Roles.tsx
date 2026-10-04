import { For, Show, createMemo, createResource, createSignal } from "solid-js";
import {
	ListTable,
	ListToolbar,
	Pagination,
	RangeFilter,
	RowActions,
	SortHeader,
	createCrudList,
} from "@/components/crud";
import { createHistory } from "@/components/history";
import { Can, NoAccess } from "@/components/layout";
import { Input, Modal, PageHeader, createConfirm } from "@/components/ui";
import { withFallback } from "@/core/api";
import { auth } from "@/core/auth";
import { createForm } from "@/core/form";
import { formatDate } from "@/core/format";
import { LIMITS } from "@/core/limits";
import { notify } from "@/core/notify";
import { type Role, RolesApi } from "@/modules/roles";
import { type PermissionInfo, SystemApi } from "@/modules/system";

type RoleForm = { name: string; description: string; permissions: number[] };

const EMPTY: RoleForm = { name: "", description: "", permissions: [] };

/** Roles: cada uno es un nombre y la lista de permisos que abre. */
export default function Roles() {
	const list = createCrudList(RolesApi.list, { enabled: () => auth.can("roles.list") });
	const confirm = createConfirm();
	const history = createHistory();
	const form = createForm(EMPTY);
	const [editing, setEditing] = createSignal<Role | null>();
	const [removed, setRemoved] = createSignal(0);
	const [catalog] = createResource(() =>
		withFallback(SystemApi.permissions(), [] as PermissionInfo[]),
	);

	const assignable = createMemo(() => (catalog() ?? []).filter((permission) => permission.assignable));
	const assignableIds = createMemo(() => new Set(assignable().map((permission) => permission.id)));
	const groups = createMemo(() => {
		const grouped = new Map<string, PermissionInfo[]>();
		for (const permission of assignable()) {
			grouped.set(permission.group, [...(grouped.get(permission.group) ?? []), permission]);
		}
		return [...grouped.entries()];
	});

	/** Quien no es dev solo gestiona roles cuyos permisos tiene también. */
	const manageable = (role: Role) => role.permissions.every((id) => auth.canGrant(id));

	function open(role: Role | null) {
		const known =
			role && assignableIds().size > 0
				? role.permissions.filter((id) => assignableIds().has(id))
				: (role?.permissions ?? []);
		setRemoved(role ? role.permissions.length - known.length : 0);
		form.reset(
			role ? { name: role.name, description: role.description, permissions: [...known] } : EMPTY,
		);
		setEditing(role);
	}

	function toggle(ids: number[], selected: boolean) {
		const current = form.values().permissions;
		form.set(
			"permissions",
			selected
				? [...new Set([...current, ...ids.filter((id) => auth.canGrant(id))])]
				: current.filter((id) => !ids.includes(id)),
		);
	}

	async function save(event: SubmitEvent) {
		event.preventDefault();
		const current = editing();
		const saved = await form.submit(async (values, key) => {
			const data = { ...values, name: values.name.trim(), description: values.description.trim() };
			const role = current
				? await RolesApi.update(current.id, data, key)
				: await RolesApi.create(data, key);
			notify.success(`Rol ${role.name} ${current ? "actualizado" : "creado"}`);
		});
		if (saved) {
			setEditing(undefined);
			list.refetch();
		}
	}

	return (
		<Can permission="roles.list" fallback={<NoAccess />}>
			<PageHeader title="Roles" subtitle="Cada rol abre una lista de permisos. Un usuario tiene un rol.">
				<Can permission="roles.create">
					<button type="button" class="btn btn-primary btn-sm" onClick={() => open(null)}>
						Nuevo rol
					</button>
				</Can>
			</PageHeader>

			<ListToolbar list={list} placeholder="Buscar por nombre">
				<div class="flex w-full flex-wrap gap-x-6 gap-y-2">
					<RangeFilter list={list} name="created_at" label="Creado" />
					<RangeFilter list={list} name="updated_at" label="Modificado" />
				</div>
			</ListToolbar>

			<ListTable
				list={list}
				columns={5}
				empty="No hay roles que mostrar."
				head={
					<>
						<SortHeader list={list} column="name">
							Rol
						</SortHeader>
						<th>Permisos</th>
						<th>Usuarios</th>
						<SortHeader list={list} column="updated_at">
							Modificado
						</SortHeader>
						<th class="text-right">Acciones</th>
					</>
				}
			>
				<For each={list.items()}>
					{(role) => (
						<tr>
							<td>
								<p class="font-medium">
									{role.name}
									<Show when={role.deleted_at}>
										<span class="badge badge-error badge-xs ml-2">eliminado</span>
									</Show>
								</p>
								<p class="text-xs opacity-60">{role.description || "Sin descripción"}</p>
							</td>
							<td>{role.permissions.length}</td>
							<td>{role.users_count}</td>
							<td class="text-xs opacity-70">{formatDate(role.updated_at)}</td>
							<td>
								<Show
									when={manageable(role)}
									fallback={
										<span class="block text-right text-xs opacity-50">
											Tiene permisos que tú no tienes
										</span>
									}
								>
									<RowActions
										item={role}
										label={role.name}
										resource="roles"
										api={RolesApi}
										confirm={confirm}
										history={history}
										onEdit={open}
										onChanged={list.refetch}
										deleteBlocked={
											role.users_count > 0
												? `Lo usan ${role.users_count} usuarios: asígnales otro rol antes`
												: undefined
										}
									/>
								</Show>
							</td>
						</tr>
					)}
				</For>
			</ListTable>

			<Pagination list={list} />

			<Modal
				open={editing() !== undefined}
				title={editing() ? `Editar ${editing()?.name}` : "Nuevo rol"}
				subtitle="Marca los permisos que abre este rol."
				width="max-w-3xl"
				onClose={() => setEditing(undefined)}
				actions={
					<>
						<span class="mr-auto self-center text-sm opacity-60">
							{form.values().permissions.length} permisos seleccionados
						</span>
						<button type="button" class="btn btn-ghost" onClick={() => setEditing(undefined)}>
							Cancelar
						</button>
						<button type="submit" form="role-form" class="btn btn-primary" disabled={form.saving()}>
							{form.saving() ? "Guardando..." : "Guardar"}
						</button>
					</>
				}
			>
				<form id="role-form" onSubmit={save} class="space-y-3">
					<Show when={removed() > 0}>
						<div role="alert" class="alert alert-warning text-sm">
							Este rol incluía {removed()} {removed() === 1 ? "permiso" : "permisos"} que ya no
							existen en el sistema; se quitarán al guardar.
						</div>
					</Show>
					<div class="grid gap-2 sm:grid-cols-2">
						<Input
							label="Nombre"
							maxLength={LIMITS.name}
							value={form.values().name}
							error={form.errors().name}
							onInput={(event) => form.set("name", event.currentTarget.value)}
							required
						/>
						<Input
							label="Descripción"
							maxLength={LIMITS.description}
							value={form.values().description}
							error={form.errors().description}
							onInput={(event) => form.set("description", event.currentTarget.value)}
						/>
					</div>
					<Show when={form.errors().permissions}>
						<p role="alert" class="text-sm text-error">
							{form.errors().permissions}
						</p>
					</Show>
					<Show when={!auth.isDev()}>
						<p class="text-xs opacity-60">
							Solo puedes conceder los permisos que tú tienes; el resto aparecen desactivados.
						</p>
					</Show>
					<div class="max-h-80 space-y-3 overflow-y-auto pr-1">
						<For each={groups()}>
							{([group, permissions]) => (
								<div class="rounded-box border border-base-300 p-3">
									<div class="mb-2 flex items-center justify-between">
										<h4 class="font-semibold">{group}</h4>
										<div class="flex gap-1">
											<button
												type="button"
												class="btn btn-ghost btn-xs"
												onClick={() => toggle(permissions.map((p) => p.id), true)}
											>
												Todos
											</button>
											<button
												type="button"
												class="btn btn-ghost btn-xs"
												onClick={() => toggle(permissions.map((p) => p.id), false)}
											>
												Ninguno
											</button>
										</div>
									</div>
									<div class="grid gap-1 sm:grid-cols-2">
										<For each={permissions}>
											{(permission) => (
												<label
													class="label cursor-pointer justify-start gap-2"
													title={
														auth.canGrant(permission.id)
															? permission.key
															: "No puedes conceder un permiso que no tienes"
													}
												>
													<input
														type="checkbox"
														class="checkbox checkbox-sm"
														checked={form.values().permissions.includes(permission.id)}
														disabled={!auth.canGrant(permission.id)}
														onChange={(event) =>
															toggle([permission.id], event.currentTarget.checked)
														}
													/>
													<span class="text-sm">
														{permission.description}
														<span class="ml-1 font-mono text-xs opacity-40">#{permission.id}</span>
													</span>
												</label>
											)}
										</For>
									</div>
								</div>
							)}
						</For>
					</div>
				</form>
			</Modal>

			<confirm.Dialog />
			<history.Dialog />
		</Can>
	);
}
