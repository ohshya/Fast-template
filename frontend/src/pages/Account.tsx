import { Show, createResource } from "solid-js";
import { SessionList } from "@/components/sessions";
import { PageHeader, PasswordInput, createConfirm } from "@/components/ui";
import { withFallback } from "@/core/api";
import { auth } from "@/core/auth";
import { createForm } from "@/core/form";
import { formatDate } from "@/core/format";
import { LIMITS } from "@/core/limits";
import { notify } from "@/core/notify";
import { AuthApi, type Session } from "@/modules/auth";

/** Cuenta del usuario conectado: sus datos, su contraseña y sus sesiones abiertas. */
export default function Account() {
	const confirm = createConfirm();
	const form = createForm({ current_password: "", new_password: "" });
	const [sessions, { refetch }] = createResource(() =>
		withFallback(AuthApi.sessions(), [] as Session[]),
	);

	async function changePassword(event: SubmitEvent) {
		event.preventDefault();
		const saved = await form.submit(async (values, key) => {
			const response = await AuthApi.changePassword(values.current_password, values.new_password, key);
			notify.success(response.detail);
		});
		if (saved) {
			form.reset();
			refetch();
		}
	}

	function closeSession(session: Session) {
		confirm.ask({
			title: "Cerrar sesión",
			message: session.is_current
				? "Es la sesión que estás usando: saldrás ahora mismo."
				: `Se cerrará la sesión de ${session.device}.`,
			action: async () => {
				notify.success((await AuthApi.closeSession(session.id)).detail);
				if (session.is_current) auth.clear();
				else refetch();
			},
		});
	}

	return (
		<>
			<PageHeader title="Mi cuenta" subtitle="Tus datos, tu contraseña y dónde tienes la sesión abierta." />

			<div class="grid gap-4 lg:grid-cols-2">
				<div class="card bg-base-100 shadow-sm">
					<div class="card-body">
						<h2 class="card-title text-base">Datos</h2>
						<dl class="grid grid-cols-2 gap-y-1 text-sm">
							<dt class="opacity-60">Usuario</dt>
							<dd>{auth.user()?.username}</dd>
							<dt class="opacity-60">Rol</dt>
							<dd>{auth.user()?.role_name ?? "Sin rol"}</dd>
							<dt class="opacity-60">Desarrollador</dt>
							<dd>{auth.isDev() ? "sí (acceso total)" : "no"}</dd>
							<dt class="opacity-60">Permisos</dt>
							<dd>{auth.user()?.permissions.length}</dd>
							<dt class="opacity-60">Último acceso</dt>
							<dd>{formatDate(auth.user()?.last_login_at)}</dd>
						</dl>

						<form class="mt-4 border-t border-base-300 pt-4" onSubmit={changePassword}>
							<h3 class="font-semibold">Cambiar mi contraseña</h3>
							<PasswordInput
								label="Contraseña actual"
								maxLength={LIMITS.password}
								autocomplete="current-password"
								value={form.values().current_password}
								error={form.errors().current_password}
								onInput={(event) => form.set("current_password", event.currentTarget.value)}
								required
							/>
							<PasswordInput
								label="Contraseña nueva"
								maxLength={LIMITS.password}
								autocomplete="new-password"
								value={form.values().new_password}
								error={form.errors().new_password}
								hint={`${auth.passwordHint()}. Se cerrarán tus demás sesiones.`}
								onInput={(event) => form.set("new_password", event.currentTarget.value)}
								required
							/>
							<button type="submit" class="btn btn-primary btn-sm mt-3" disabled={form.saving()}>
								{form.saving() ? "Guardando..." : "Actualizar contraseña"}
							</button>
						</form>
					</div>
				</div>

				<div class="card bg-base-100 shadow-sm">
					<div class="card-body">
						<div class="flex items-center justify-between">
							<h2 class="card-title text-base">Mis sesiones</h2>
							<button
								type="button"
								class="btn btn-ghost btn-xs text-error"
								disabled={(sessions()?.length ?? 0) < 2}
								onClick={() =>
									confirm.ask({
										title: "Cerrar las demás sesiones",
										message: "Se cerrarán todas las sesiones abiertas salvo esta.",
										confirmLabel: "Cerrar todas",
										action: async () => {
											notify.success((await AuthApi.closeOtherSessions()).detail);
											refetch();
										},
									})
								}
							>
								Cerrar las demás
							</button>
						</div>

						<Show when={!sessions.loading} fallback={<span class="loading loading-spinner" />}>
							<SessionList sessions={sessions() ?? []} onClose={closeSession} />
						</Show>
					</div>
				</div>
			</div>

			<confirm.Dialog />
		</>
	);
}
