import { A, Navigate, type RouteSectionProps, useLocation, useNavigate } from "@solidjs/router";
import { AiOutlineLogout } from "solid-icons/ai";
import { ErrorBoundary, For, type JSX, Show } from "solid-js";
import { APP_NAME } from "@/core/app";
import { StatusBadge } from "@/components/StatusBadge";
import { auth } from "@/core/auth";

export type NavItem = {
	href: string;
	label: string;
	permission?: string;
	/** Condición extra para mostrar el enlace, además del permiso. */
	when?: () => boolean;
};

/** Enlaces del menú principal. Una página nueva que deba aparecer en el menú se añade aquí. */
export const NAV: NavItem[] = [
	{ href: "/users", label: "Usuarios", permission: "users.list" },
	{ href: "/roles", label: "Roles", permission: "roles.list" },
	{ href: "/audit", label: "Auditoría", permission: "events.list" },
	{ href: "/debug", label: "Debug", when: canUseDebug },
];

/** Debug es solo para desarrolladores y solo mientras el servidor está en modo desarrollo. */
export function canUseDebug(): boolean {
	return auth.isDev() && auth.info()?.debug === true;
}

/** Enlaces del menú que el usuario conectado puede abrir. */
export function visibleNav(): NavItem[] {
	return NAV.filter(
		(item) => (!item.permission || auth.can(item.permission)) && (!item.when || item.when()),
	);
}

/** Cierra el desplegable <details> que contiene al elemento pulsado. */
function closeDropdown(event: MouseEvent) {
	(event.currentTarget as HTMLElement).closest("details")?.removeAttribute("open");
}

/** Barra superior común a todas las páginas con sesión. */
export function AppShell(props: { children: JSX.Element }) {
	const navigate = useNavigate();
	const location = useLocation();

	async function salir() {
		await auth.logout();
		navigate("/login", { replace: true });
	}

	return (
		<div class="min-h-screen bg-base-200">
			<header class="navbar sticky top-0 z-40 bg-base-100 px-4 shadow-sm">
				<div class="navbar-start gap-1">
					<details class="dropdown lg:hidden">
						<summary class="btn btn-ghost btn-sm">Menú</summary>
						<ul class="menu dropdown-content z-50 mt-2 w-52 rounded-box bg-base-100 p-2 shadow">
							<For each={visibleNav()}>
								{(item) => (
									<li>
										<A href={item.href} onClick={closeDropdown}>
											{item.label}
										</A>
									</li>
								)}
							</For>
						</ul>
					</details>
					<A href="/" class="btn btn-ghost text-lg font-bold">
						{APP_NAME}
					</A>
				</div>

				<nav class="navbar-center hidden lg:flex">
					<ul class="menu menu-horizontal gap-1">
						<For each={visibleNav()}>
							{(item) => (
								<li>
									<A href={item.href} activeClass="menu-active">
										{item.label}
									</A>
								</li>
							)}
						</For>
					</ul>
				</nav>

				<div class="navbar-end gap-2">
					<StatusBadge />
					<details class="dropdown dropdown-end">
						<summary class="btn btn-ghost btn-sm gap-2">
							{auth.user()?.username}
							<Show when={auth.isDev()}>
								<span class="badge badge-warning badge-xs">dev</span>
							</Show>
						</summary>
						<ul class="menu dropdown-content z-50 mt-2 w-56 rounded-box bg-base-100 p-2 shadow">
							<li class="menu-title">{auth.user()?.role_name ?? "Sin rol"}</li>
							<li>
								<A href="/account" onClick={closeDropdown}>
									Mi cuenta
								</A>
							</li>
							<li>
								<button type="button" class="text-error" onClick={salir}>
									<AiOutlineLogout /> Cerrar sesión
								</button>
							</li>
						</ul>
					</details>
				</div>
			</header>

			<main class="mx-auto max-w-7xl space-y-4 p-4 lg:p-6">
				<Show when={location.pathname} keyed>
					{(_path) => (
						<ErrorBoundary fallback={(error, reset) => <CrashNotice error={error} reset={reset} />}>
							{props.children}
						</ErrorBoundary>
					)}
				</Show>
			</main>
		</div>
	);
}

/** Envuelve las rutas que exigen sesión; sin ella, manda al login y vuelve después. */
export function ProtectedRoute(props: RouteSectionProps) {
	const location = useLocation();
	const loginUrl = () => `/login?next=${encodeURIComponent(location.pathname + location.search)}`;

	return (
		<Show
			when={!auth.loading()}
			fallback={
				<div class="flex min-h-screen items-center justify-center">
					<span class="loading loading-spinner loading-lg" />
				</div>
			}
		>
			<Show when={auth.isLoggedIn()} fallback={<Navigate href={loginUrl()} />}>
				<AppShell>{props.children}</AppShell>
			</Show>
		</Show>
	);
}

/** Muestra su contenido solo si el usuario tiene el permiso con esa clave, p. ej. "users.create". */
export function Can(props: { permission: string; fallback?: JSX.Element; children: JSX.Element }) {
	return (
		<Show when={auth.can(props.permission)} fallback={props.fallback}>
			{props.children}
		</Show>
	);
}

/** Pantalla de un fallo inesperado del navegador, con la opción de reintentar o recargar. */
export function CrashNotice(props: { error: unknown; reset: () => void }) {
	return (
		<div role="alert" class="alert alert-error alert-vertical sm:alert-horizontal">
			<div>
				<h2 class="font-bold">Algo salió mal en esta pantalla</h2>
				<p class="text-sm">Puedes reintentar o recargar la página. Si se repite, avisa a quien mantiene la aplicación.</p>
				<Show when={import.meta.env.DEV}>
					<pre class="mt-2 whitespace-pre-wrap text-xs">{String(props.error)}</pre>
				</Show>
			</div>
			<div class="flex gap-2">
				<button type="button" class="btn btn-sm" onClick={props.reset}>
					Reintentar
				</button>
				<button type="button" class="btn btn-sm" onClick={() => location.reload()}>
					Recargar
				</button>
			</div>
		</div>
	);
}

/** Aviso para una página entera a la que el usuario no tiene acceso. */
export function NoAccess() {
	return (
		<div role="alert" class="alert alert-warning">
			No tienes permiso para ver esta página.
		</div>
	);
}
