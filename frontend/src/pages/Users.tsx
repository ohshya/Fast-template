import { For, Show, createMemo, createResource, createSignal } from "solid-js";
import {
	FilterMulti,
	FilterSelect,
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
import { SessionList } from "@/components/sessions";
import { Input, Modal, PageHeader, PasswordInput, createConfirm } from "@/components/ui";
import { listAll, withFallback } from "@/core/api";
import { auth } from "@/core/auth";
import { createForm } from "@/core/form";
import { formatDate } from "@/core/format";
import { LIMITS } from "@/core/limits";
import { notify } from "@/core/notify";
import type { Session } from "@/modules/auth";
import { type Role, RolesApi } from "@/modules/roles";
import { type User, UsersApi } from "@/modules/users";

type UserForm = {
	username: string;
	password: string;
	role_id: string;
	is_active: boolean;
	dev: boolean;
};

const EMPTY: UserForm = { username: "", password: "", role_id: "", is_active: true, dev: false };

const STATES = [
	{ value: "true", label: "Activos" },
	{ value: "false", label: "Inactivos" },
];

const KINDS = [
	{ value: "true", label: "Desarrolladores" },
	{ value: "false", label: "Usuarios normales" },
];

/**
 * Gestión de usuarios.
 *
 * Es también la página de referencia para un módulo CRUD: listado con búsqueda, filtros,
 * orden y páginas (`createCrudList`), acciones por permiso (`RowActions`), formulario con
 * errores por campo y clave de idempotencia (`createForm`) e historial (`createHistory`).
 * Los datos de apoyo (aquí, los roles) solo se piden si el usuario tiene permiso para verlos.
 */
export default function Users() {
	const list = createCrudList(UsersApi.list, { enabled: () => auth.can("users.list") });
	const confirm = createConfirm();
	const history = createHistory();
	const form = createForm(EMPTY);
	const passwordForm = createForm({ new_password: "" });
	const [roles] = createResource(
		() => auth.can("roles.list"),
		() => withFallback(listAll(RolesApi.list), [] as Role[]),
	);
	const [editing, setEditing] = createSignal<User | null>();
	const [passwordOf, setPasswordOf] = createSignal<User>();
	const [sessionsOf, setSessionsOf] = createSignal<User>();
	const [sessions, { refetch: refetchSessions }] = createResource(sessionsOf, (user) =>
		withFallback(UsersApi.sessions(user.id), [] as Session[]),
	);

	const roleOptions = () => (roles() ?? []).map((role) => ({ value: role.id, label: role.name }));
	const rolesById = createMemo(() => new Map((roles() ?? []).map((role) => [role.id, role])));
	const isMe = (user: User) => user.id === auth.user()?.id;
	const editingMe = () => {
		const user = editing();
		return !!user && isMe(user);
	};
	const grantable = (role: Role) => role.permissions.every((id) => auth.canGrant(id));

	/** Por qué el usuario conectado no puede gestionar esta cuenta, o `null` si puede. */
	function lockedReason(user: User): string | null {
		if (auth.isDev()) return null;
		if (user.dev) return "Solo la gestiona un dev";
		const role = user.role_id ? rolesById().get(user.role_id) : undefined;
		return role && !grantable(role) ? "Su rol tiene permisos que tú no tienes" : null;
	}

	function open(user: User | null) {
		form.reset(
			user
				? {
						username: user.username,
						password: "",
						role_id: user.role_id ?? "",
						is_active: user.is_active,
						dev: user.dev,
					}
				: EMPTY,
		);
		setEditing(user);
	}

	function openPassword(user: User) {
		passwordForm.reset();
		setPasswordOf(user);
	}

	async function save(event: SubmitEvent) {
		event.preventDefault();
		const current = editing();
		const saved = await form.submit(async (values, key) => {
			const common = {
				username: values.username.trim(),
				role_id: values.role_id || null,
				is_active: values.is_active,
				...(auth.isDev() ? { dev: values.dev } : {}),
			};
			const user = current
				? await UsersApi.update(current.id, common, key)
				: await UsersApi.create({ ...common, password: values.password }, key);
			notify.success(`Usuario ${user.username} ${current ? "actualizado" : "creado"}`);
		});
		if (saved) {
			setEditing(undefined);
			list.refetch();
		}
	}

	async function savePassword(event: SubmitEvent) {
		event.preventDefault();
		const user = passwordOf();
		if (!user) return;
		const saved = await passwordForm.submit(async (values, key) => {
			notify.success((await UsersApi.resetPassword(user.id, values.new_password, key)).detail);
		});
		if (saved) setPasswordOf(undefined);
	}

	function closeSessions(user: User) {
		confirm.ask({
			title: `Cerrar las sesiones de ${user.username}`,
			message: "Tendrá que iniciar sesión de nuevo en todos sus dispositivos.",
			confirmLabel: "Cerrar todas",
			action: async () => {
				notify.success((await UsersApi.closeSessions(user.id)).detail);
				refetchSessions();
			},
		});
	}

	return (
		<Can permission="users.list" fallback={<NoAccess />}>
			<PageHeader title="Usuarios" subtitle="Cuentas con acceso al sistema y su rol.">
				<Can permission="users.create">
					<button type="button" class="btn btn-primary btn-sm" onClick={() => open(null)}>
						Nuevo usuario
					</button>
				</Can>
			</PageHeader>

			<ListToolbar list={list} placeholder="Buscar por nombre de usuario">
				<Show when={roleOptions().length > 0}>
					<FilterMulti list={list} name="role_id" label="Roles" options={roleOptions()} />
				</Show>
				<FilterSelect list={list} name="is_active" label="Todos los estados" options={STATES} />
				<Show when={auth.isDev()}>
					<FilterSelect list={list} name="dev" label="Todas las cuentas" options={KINDS} />
				</Show>
				<div class="flex w-full flex-wrap gap-x-6 gap-y-2">
					<RangeFilter list={list} name="created_at" label="Creado" />
					<RangeFilter list={list} name="last_login_at" label="Último acceso" />
				</div>
			</ListToolbar>

			<ListTable
				list={list}
				columns={6}
				empty="No hay usuarios que mostrar."
				head={
					<>
						<SortHeader list={list} column="username">
							Usuario
						</SortHeader>
						<th>Rol</th>
						<SortHeader list={list} column="is_active">
							Estado
						</SortHeader>
						<SortHeader list={list} column="created_at">
							Creado
						</SortHeader>
						<SortHeader list={list} column="last_login_at">
							Último acceso
						</SortHeader>
						<th class="text-right">Acciones</th>
					</>
				}
			>
				<For each={list.items()}>
					{(user) => (
						<tr>
							<td class="font-medium">
								{user.username}
								<Show when={user.dev}>
									<span class="badge badge-warning badge-xs ml-2">dev</span>
								</Show>
								<Show when={isMe(user)}>
									<span class="badge badge-ghost badge-xs ml-2">tú</span>
								</Show>
							</td>
							<td>{user.role_name ?? <span class="opacity-50">Sin rol</span>}</td>
							<td>
								<Show
									when={!user.deleted_at}
									fallback={<span class="badge badge-error badge-sm">eliminado</span>}
								>
									<span
										class="badge badge-sm"
										classList={{
											"badge-success": user.is_active,
											"badge-ghost": !user.is_active,
										}}
									>
										{user.is_active ? "activo" : "inactivo"}
									</span>
								</Show>
							</td>
							<td class="text-xs opacity-70">{formatDate(user.created_at)}</td>
							<td class="text-xs opacity-70">{formatDate(user.last_login_at)}</td>
							<td>
								<Show
									when={!lockedReason(user)}
									fallback={
										<span class="block text-right text-xs opacity-50">{lockedReason(user)}</span>
									}
								>
									<RowActions
										item={user}
										label={user.username}
										resource="users"
										api={UsersApi}
										confirm={confirm}
										history={history}
										onEdit={open}
										onChanged={list.refetch}
										deleteBlocked={isMe(user) ? "No puedes eliminar tu propia cuenta" : undefined}
									>
										<Can permission="users.sessions.list">
											<button
												type="button"
												class="btn btn-ghost btn-xs"
												onClick={() => setSessionsOf(user)}
											>
												Sesiones
											</button>
										</Can>
										<Show when={!isMe(user)}>
											<Can permission="users.password.reset">
												<button
													type="button"
													class="btn btn-ghost btn-xs"
													onClick={() => openPassword(user)}
												>
													Contraseña
												</button>
											</Can>
										</Show>
									</RowActions>
								</Show>
							</td>
						</tr>
					)}
				</For>
			</ListTable>

			<Pagination list={list} />

			<Modal
				open={editing() !== undefined}
				title={editing() ? `Editar ${editing()?.username}` : "Nuevo usuario"}
				onClose={() => setEditing(undefined)}
				actions={
					<>
						<button type="button" class="btn btn-ghost" onClick={() => setEditing(undefined)}>
							Cancelar
						</button>
						<button type="submit" form="user-form" class="btn btn-primary" disabled={form.saving()}>
							{form.saving() ? "Guardando..." : "Guardar"}
						</button>
					</>
				}
			>
				<form id="user-form" onSubmit={save}>
					<Input
						label="Usuario"
						maxLength={LIMITS.username}
						autocomplete="off"
						autocapitalize="none"
						spellcheck={false}
						hint="De 3 a 50 caracteres: letras sin acentos, números, punto, guion y guion bajo. Se guarda en minúsculas."
						value={form.values().username}
						error={form.errors().username}
						onInput={(event) => form.set("username", event.currentTarget.value)}
						required
					/>
					<Show when={editing() === null}>
						<PasswordInput
							label="Contraseña"
							maxLength={LIMITS.password}
							autocomplete="new-password"
							value={form.values().password}
							error={form.errors().password}
							hint={auth.passwordHint()}
							onInput={(event) => form.set("password", event.currentTarget.value)}
							required
						/>
					</Show>
					<fieldset class="fieldset">
						<legend class="fieldset-legend">Rol</legend>
						<select
							class="select w-full"
							aria-label="Rol"
							onChange={(event) => form.set("role_id", event.currentTarget.value)}
						>
							<option value="" selected={form.values().role_id === ""}>
								Sin rol (solo su propia cuenta)
							</option>
							<Show
								when={
									form.values().role_id &&
									!rolesById().has(form.values().role_id) &&
									editing()?.role_id === form.values().role_id
								}
							>
								<option value={form.values().role_id} selected>
									{editing()?.role_name ?? "Rol actual"} (no disponible)
								</option>
							</Show>
							<For each={roles()}>
								{(role) => (
									<option
										value={role.id}
										selected={form.values().role_id === role.id}
										disabled={!grantable(role) && form.values().role_id !== role.id}
									>
										{role.name}
										{grantable(role) ? "" : " (tiene permisos que tú no tienes)"}
									</option>
								)}
							</For>
						</select>
						<Show when={!auth.can("roles.list")}>
							<p class="label">No tienes permiso para ver los roles: el actual se conserva.</p>
						</Show>
						<Show when={form.errors().role_id}>
							<p role="alert" class="label text-error">
								{form.errors().role_id}
							</p>
						</Show>
					</fieldset>
					<label class="label mt-2 cursor-pointer gap-2">
						<input
							type="checkbox"
							class="toggle toggle-sm"
							checked={form.values().is_active}
							disabled={editingMe()}
							onChange={(event) => form.set("is_active", event.currentTarget.checked)}
						/>
						Activo
					</label>
					<Show when={auth.isDev()}>
						<label class="label mt-2 cursor-pointer gap-2">
							<input
								type="checkbox"
								class="toggle toggle-warning toggle-sm"
								checked={form.values().dev}
								disabled={editingMe()}
								onChange={(event) => form.set("dev", event.currentTarget.checked)}
							/>
							Desarrollador (acceso total)
						</label>
					</Show>
					<Show when={editingMe()}>
						<p class="label mt-2">
							No puedes desactivar tu cuenta ni quitarte el acceso de desarrollador.
						</p>
					</Show>
				</form>
			</Modal>

			<Modal
				open={passwordOf() !== undefined}
				title={`Nueva contraseña para ${passwordOf()?.username ?? ""}`}
				subtitle="Se cerrarán todas sus sesiones abiertas."
				onClose={() => setPasswordOf(undefined)}
				actions={
					<>
						<button type="button" class="btn btn-ghost" onClick={() => setPasswordOf(undefined)}>
							Cancelar
						</button>
						<button
							type="submit"
							form="password-form"
							class="btn btn-primary"
							disabled={passwordForm.saving()}
						>
							{passwordForm.saving() ? "Guardando..." : "Cambiar"}
						</button>
					</>
				}
			>
				<form id="password-form" onSubmit={savePassword}>
					<PasswordInput
						label="Contraseña"
						maxLength={LIMITS.password}
						autocomplete="new-password"
						value={passwordForm.values().new_password}
						error={passwordForm.errors().new_password}
						hint={auth.passwordHint()}
						onInput={(event) => passwordForm.set("new_password", event.currentTarget.value)}
						required
					/>
				</form>
			</Modal>

			<Modal
				open={sessionsOf() !== undefined}
				title={`Sesiones de ${sessionsOf()?.username ?? ""}`}
				width="max-w-2xl"
				onClose={() => setSessionsOf(undefined)}
				actions={
					<>
						<Can permission="users.sessions.revoke">
							<button
								type="button"
								class="btn btn-error btn-outline mr-auto"
								disabled={!sessions()?.length}
								onClick={() => {
									const user = sessionsOf();
									if (user) closeSessions(user);
								}}
							>
								Cerrar todas
							</button>
						</Can>
						<button type="button" class="btn btn-ghost" onClick={() => setSessionsOf(undefined)}>
							Cerrar ventana
						</button>
					</>
				}
			>
				<Show when={!sessions.loading} fallback={<span class="loading loading-spinner" />}>
					<SessionList sessions={sessions() ?? []} />
				</Show>
			</Modal>

			<confirm.Dialog />
			<history.Dialog />
		</Can>
	);
}
