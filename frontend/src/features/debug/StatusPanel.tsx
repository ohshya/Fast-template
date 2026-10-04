import { For, type JSX, Show, createResource, createSignal, onCleanup } from "solid-js";
import { reportError, withFallback } from "@/core/api";
import { auth } from "@/core/auth";
import { formatDate, timeAgo } from "@/core/format";
import { notify } from "@/core/notify";
import { checkServerStatus, markOffline, serverStatus } from "@/core/serverStatus";
import { AuthApi, type Session } from "@/modules/auth";
import { type Health, SystemApi } from "@/modules/system";

function Row(props: { title: string; children: JSX.Element }) {
	return (
		<>
			<dt class="opacity-60">{props.title}</dt>
			<dd class="break-all">{props.children}</dd>
		</>
	);
}

function Card(props: { title: string; children: JSX.Element; actions?: JSX.Element }) {
	return (
		<section class="card bg-base-100 shadow-sm">
			<div class="card-body gap-3">
				<h2 class="card-title text-base">{props.title}</h2>
				{props.children}
				<Show when={props.actions}>
					<div class="card-actions">{props.actions}</div>
				</Show>
			</div>
		</section>
	);
}

/** Dibuja un valor sí/no como insignia. */
function Flag(props: { on: boolean | undefined; yes?: string; no?: string }) {
	return (
		<span class="badge badge-sm" classList={{ "badge-success": !!props.on, "badge-ghost": !props.on }}>
			{props.on ? (props.yes ?? "sí") : (props.no ?? "no")}
		</span>
	);
}

/** Conexión con el servidor, cuenta, políticas y entorno del navegador, con acciones para probarlos. */
export function StatusPanel() {
	const [health, { refetch: refetchHealth }] = createResource(() =>
		withFallback(SystemApi.health(), null as Health | null),
	);
	const [sessions, { refetch: refetchSessions }] = createResource(() =>
		withFallback(AuthApi.sessions(), [] as Session[]),
	);
	const [busy, setBusy] = createSignal<string | null>(null);
	const [browserOnline, setBrowserOnline] = createSignal(navigator.onLine);
	const [viewport, setViewport] = createSignal(`${window.innerWidth} × ${window.innerHeight}`);

	const onOnline = () => setBrowserOnline(true);
	const onOffline = () => setBrowserOnline(false);
	const onResize = () => setViewport(`${window.innerWidth} × ${window.innerHeight}`);
	window.addEventListener("online", onOnline);
	window.addEventListener("offline", onOffline);
	window.addEventListener("resize", onResize);
	onCleanup(() => {
		window.removeEventListener("online", onOnline);
		window.removeEventListener("offline", onOffline);
		window.removeEventListener("resize", onResize);
	});

	/** Ejecuta una acción de prueba mostrando que está en curso y avisando de un fallo del navegador. */
	async function run(name: string, action: () => Promise<unknown>, done?: string) {
		setBusy(name);
		try {
			await action();
			if (done) notify.success(done);
		} catch (error) {
			reportError(error);
		} finally {
			setBusy(null);
		}
	}

	const me = () => auth.user();
	const info = () => auth.info();

	return (
		<div class="space-y-4">
			<div class="stats stats-vertical w-full bg-base-100 shadow-sm sm:stats-horizontal">
				<div class="stat">
					<div class="stat-title">Servidor</div>
					<div class="stat-value flex items-center gap-2 text-xl">
						<span
							class="status status-lg"
							classList={{
								"status-success": serverStatus.online(),
								"status-error": !serverStatus.online(),
							}}
						/>
						{serverStatus.online() ? "En línea" : "Sin conexión"}
					</div>
					<div class="stat-desc">{serverStatus.reason() ?? "Responde con normalidad"}</div>
				</div>
				<div class="stat">
					<div class="stat-title">Latencia</div>
					<div class="stat-value text-xl">
						{serverStatus.latency() === null ? "—" : `${serverStatus.latency()} ms`}
					</div>
					<div class="stat-desc">de la última comprobación de /system/health</div>
				</div>
				<div class="stat">
					<div class="stat-title">Última respuesta</div>
					<div class="stat-value text-xl">{timeAgo(serverStatus.checkedAt())}</div>
					<div class="stat-desc">
						{serverStatus.nextCheckAt()
							? `próxima comprobación: ${formatDate(new Date(serverStatus.nextCheckAt() ?? 0).toISOString())}`
							: "sin comprobación programada"}
					</div>
				</div>
			</div>

			<div class="grid gap-4 lg:grid-cols-2">
				<Card
					title="Conexión"
					actions={
						<>
							<button
								type="button"
								class="btn btn-sm"
								disabled={busy() !== null}
								onClick={() =>
									run("check", async () => {
										await checkServerStatus();
										await refetchHealth();
									})
								}
							>
								Comprobar ahora
							</button>
							<button
								type="button"
								class="btn btn-sm btn-warning btn-outline"
								onClick={() =>
									markOffline("Prueba desde Debug: la pantalla se quita sola al volver a responder el servidor.")
								}
							>
								Probar pantalla sin conexión
							</button>
						</>
					}
				>
					<dl class="grid grid-cols-[10rem_1fr] gap-y-1 text-sm">
						<Row title="GET /system/health">
							<Show when={health()} fallback="sin respuesta">
								{(data) => (
									<>
										{data().status} · base de datos {data().database}
									</>
								)}
							</Show>
						</Row>
						<Row title="Sondeo">cada 15 s en línea; caído, cada 2 s y duplicando hasta 15 s</Row>
						<Row title="Navegador en línea">
							<Flag on={browserOnline()} yes="sí" no="no (sin red)" />
						</Row>
						<Row title="Cierre pendiente">
							<Flag on={auth.pendingLogout()} yes="sí: se enviará al volver la conexión" no="no" />
						</Row>
					</dl>
				</Card>

				<Card
					title="Servidor"
					actions={
						<button
							type="button"
							class="btn btn-sm"
							disabled={busy() !== null}
							onClick={() => run("info", () => auth.refresh(), "Políticas y cuenta releídas")}
						>
							Releer
						</button>
					}
				>
					<Show when={info()} fallback={<p class="text-sm opacity-60">Sin datos todavía.</p>}>
						{(data) => (
							<dl class="grid grid-cols-[10rem_1fr] gap-y-1 text-sm">
								<Row title="Aplicación">
									{data().name} {data().version}
								</Row>
								<Row title="Modo desarrollo">
									<Flag on={data().debug} />
								</Row>
								<Row title="Token de acceso">{data().access_expire_minutes} min</Row>
								<Row title="Token de refresco">{data().refresh_expire_days} días</Row>
								<Row title="Sesiones por usuario">{data().max_sessions_per_user}</Row>
								<Row title="Contraseña mínima">{data().password_min_length} caracteres</Row>
								<Row title="Intentos de login">
									{data().login_attempts} por usuario, {data().login_attempts_per_ip} por IP, cada{" "}
									{data().login_window_seconds / 60} min
								</Row>
							</dl>
						)}
					</Show>
				</Card>

				<Card
					title="Cuenta"
					actions={
						<>
							<button
								type="button"
								class="btn btn-sm"
								disabled={busy() !== null}
								onClick={() => run("me", () => auth.refresh(), "Cuenta releída")}
							>
								Releer /auth/me
							</button>
							<button
								type="button"
								class="btn btn-sm"
								disabled={busy() !== null}
								onClick={() =>
									run(
										"renew",
										async () => {
											await AuthApi.renew();
											await refetchSessions();
										},
										"Sesión renovada: los tokens rotaron",
									)
								}
							>
								Renovar sesión
							</button>
						</>
					}
				>
					<Show when={me()} fallback={<p class="text-sm opacity-60">Sin sesión.</p>}>
						{(user) => (
							<dl class="grid grid-cols-[10rem_1fr] gap-y-1 text-sm">
								<Row title="Usuario">
									{user().username} <Flag on={user().dev} yes="dev" no="normal" />
								</Row>
								<Row title="Identificador">
									<span class="font-mono text-xs">{user().id}</span>
								</Row>
								<Row title="Rol">{user().role_name ?? "Sin rol"}</Row>
								<Row title="Último acceso">{formatDate(user().last_login_at)}</Row>
								<Row title="Sesiones abiertas">{sessions()?.length ?? "—"}</Row>
								<Row title="Permisos">{user().permissions.length}</Row>
								<Row title="Sesión caducada">
									<Flag on={auth.expired()} />
								</Row>
							</dl>
						)}
					</Show>
				</Card>

				<Card title="Navegador">
					<dl class="grid grid-cols-[10rem_1fr] gap-y-1 text-sm">
						<Row title="Compilación">{import.meta.env.MODE}</Row>
						<Row title="Base de la API">/api (Vite lo reenvía al backend en desarrollo)</Row>
						<Row title="Ventana">{viewport()}</Row>
						<Row title="Zona horaria">{Intl.DateTimeFormat().resolvedOptions().timeZone}</Row>
						<Row title="Idioma">{navigator.language}</Row>
						<Row title="Entre pestañas">
							<Flag on={typeof BroadcastChannel !== "undefined"} yes="BroadcastChannel" no="no disponible" />{" "}
							<Flag on={!!globalThis.navigator?.locks} yes="bloqueos" no="sin bloqueos" />
						</Row>
						<Row title="Contexto seguro">
							<Flag on={window.isSecureContext} yes="sí (HTTPS o localhost)" no="no (HTTP)" />
						</Row>
						<Row title="Navegador">
							<span class="text-xs">{navigator.userAgent}</span>
						</Row>
					</dl>
				</Card>
			</div>

			<Show when={me()}>
				{(user) => (
					<Card title={`Permisos de la cuenta (${user().permission_keys.length})`}>
						<div class="flex flex-wrap gap-1">
							<For
								each={user().permission_keys}
								fallback={<span class="text-sm opacity-60">Ninguno asignable.</span>}
							>
								{(key) => <span class="badge badge-outline badge-sm font-mono">{key}</span>}
							</For>
						</div>
						<Show when={user().dev}>
							<p class="text-xs opacity-60">
								Una cuenta dev puede con todo: esta lista son los permisos asignables que se le reconocen.
							</p>
						</Show>
					</Card>
				)}
			</Show>
		</div>
	);
}
