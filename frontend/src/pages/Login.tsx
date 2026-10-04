import { useNavigate, useSearchParams } from "@solidjs/router";
import { Show, createEffect } from "solid-js";
import { Input, PasswordInput } from "@/components/ui";
import { APP_NAME } from "@/core/app";
import { auth } from "@/core/auth";
import { createForm } from "@/core/form";
import { LIMITS } from "@/core/limits";
import { safeNext } from "@/core/routes";

export default function Login() {
	const navigate = useNavigate();
	const [params] = useSearchParams();
	const form = createForm({ username: "", password: "" });
	const destination = () => safeNext(typeof params.next === "string" ? params.next : null);

	createEffect(() => {
		if (auth.isLoggedIn()) navigate(destination(), { replace: true });
	});

	async function enter(event: SubmitEvent) {
		event.preventDefault();
		await form.submit((values) => auth.login(values.username.trim(), values.password));
	}

	return (
		<div class="flex min-h-screen items-center justify-center bg-base-200 p-4">
			<Show
				when={!auth.loading() && !auth.isLoggedIn()}
				fallback={<span class="loading loading-spinner loading-lg" />}
			>
				<form onSubmit={enter} class="card w-full max-w-sm bg-base-100 shadow-xl">
					<div class="card-body">
						<h1 class="card-title justify-center text-2xl">{APP_NAME}</h1>
						<p class="text-center text-sm opacity-60">Inicia sesión para continuar</p>
						<Show when={auth.pendingLogout()}>
							<div role="status" class="alert alert-warning alert-soft text-sm">
								Tu última sesión aún no se cerró en el servidor; se cerrará sola al volver la conexión.
							</div>
						</Show>
						<Show when={auth.expired()}>
							<div role="alert" class="alert alert-info alert-soft text-sm">
								Tu sesión ha terminado. Inicia sesión de nuevo.
							</div>
						</Show>

						<Input
							label="Usuario"
							maxLength={LIMITS.username}
							autocomplete="username"
							autocapitalize="none"
							spellcheck={false}
							value={form.values().username}
							error={form.errors().username}
							loading={form.saving()}
							onInput={(event) => form.set("username", event.currentTarget.value)}
							required
						/>
						<PasswordInput
							label="Contraseña"
							maxLength={LIMITS.password}
							autocomplete="current-password"
							value={form.values().password}
							error={form.errors().password}
							loading={form.saving()}
							onInput={(event) => form.set("password", event.currentTarget.value)}
							required
						/>

						<button type="submit" class="btn btn-primary mt-4" disabled={form.saving()}>
							{form.saving() ? "Entrando..." : "Entrar"}
						</button>
					</div>
				</form>
			</Show>
		</div>
	);
}
