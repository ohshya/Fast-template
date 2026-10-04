import { A } from "@solidjs/router";
import { For, Show } from "solid-js";
import { visibleNav } from "@/components/layout";
import { APP_NAME } from "@/core/app";
import { auth } from "@/core/auth";

/** Página de inicio: saludo y accesos a las secciones que el usuario puede abrir. */
export default function Home() {
	return (
		<>
			<div>
				<h1 class="text-2xl font-bold">Hola, {auth.user()?.username}</h1>
				<p class="text-sm opacity-60">Bienvenido a {APP_NAME}.</p>
			</div>

			<Show
				when={visibleNav().length > 0}
				fallback={
					<div role="alert" class="alert">
						Tu cuenta aún no tiene un rol con acceso a ninguna sección.
					</div>
				}
			>
				<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
					<For each={visibleNav()}>
						{(item) => (
							<A href={item.href} class="card bg-base-100 shadow-sm transition hover:shadow-md">
								<div class="card-body">
									<h2 class="card-title text-base">{item.label}</h2>
								</div>
							</A>
						)}
					</For>
				</div>
			</Show>
		</>
	);
}
