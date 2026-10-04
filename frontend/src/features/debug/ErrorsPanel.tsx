import { For, Show, createMemo, createResource, createSignal } from "solid-js";
import { Can } from "@/components/layout";
import { ApiError, withFallback } from "@/core/api";
import { type ErrorInfo, SystemApi } from "@/modules/system";

const ATAJOS = [400, 401, 403, 404, 409, 422, 500];

export function ErrorsPanel() {
	const [catalogo] = createResource(() =>
		withFallback(SystemApi.errors(), [] as ErrorInfo[]),
	);
	const [status, setStatus] = createSignal(500);
	const [conToast, setConToast] = createSignal(true);
	const [respuesta, setRespuesta] = createSignal<unknown>(null);
	const [enviando, setEnviando] = createSignal(false);
	const [buscar, setBuscar] = createSignal("");

	const visibles = createMemo(() => {
		const texto = buscar().trim().toLowerCase();
		return (catalogo() ?? []).filter(
			(error) =>
				!texto ||
				`${error.code} ${error.status} ${error.message} ${error.hint} ${error.severity}`
					.toLowerCase()
					.includes(texto),
		);
	});

	async function probar(codigo: number) {
		setStatus(codigo);
		setEnviando(true);
		setRespuesta(null);
		try {
			setRespuesta(await SystemApi.testError(codigo, conToast()));
		} catch (error) {
			setRespuesta(error instanceof ApiError ? error.payload : String(error));
		} finally {
			setEnviando(false);
		}
	}

	return (
		<div class="space-y-4">
			<Can
				permission="system.test_error"
				fallback={
					<div class="alert alert-info">
						Las pruebas de error están reservadas a los usuarios dev.
					</div>
				}
			>
				<div class="card bg-base-100 shadow-sm">
					<div class="card-body">
						<h2 class="card-title text-base">Provocar un error</h2>
						<p class="text-sm opacity-70">
							El backend responde siempre con la misma forma y el interceptor decide si
							mostrar un toast según el campo <code>toast</code>. Con 500 se lanza una
							excepción real, sin controlar.
						</p>

						<div class="flex flex-wrap items-end gap-2">
							<fieldset class="fieldset">
								<legend class="fieldset-legend">Código HTTP</legend>
								<input
									type="number"
									class="input input-sm w-28"
									value={status()}
									onInput={(event) => setStatus(Number(event.currentTarget.value))}
								/>
							</fieldset>
							<label class="label cursor-pointer gap-2">
								<input
									type="checkbox"
									class="toggle toggle-sm"
									checked={conToast()}
									onChange={(event) => setConToast(event.currentTarget.checked)}
								/>
								Pedir toast
							</label>
							<button
								type="button"
								class="btn btn-warning btn-sm"
								disabled={enviando()}
								onClick={() => probar(status())}
							>
								{enviando() ? "Enviando..." : "Lanzar"}
							</button>
							<div class="ml-auto flex gap-1">
								<For each={ATAJOS}>
									{(codigo) => (
										<button
											type="button"
											class="btn btn-ghost btn-xs"
											onClick={() => probar(codigo)}
										>
											{codigo}
										</button>
									)}
								</For>
							</div>
						</div>

						<Show when={respuesta()}>
							<pre class="mt-2 overflow-x-auto rounded-box bg-base-200 p-3 text-xs">
								{JSON.stringify(respuesta(), null, 2)}
							</pre>
						</Show>
					</div>
				</div>
			</Can>

			<Can permission="system.errors">
				<input
					type="search"
					class="input input-sm w-full sm:w-80"
					placeholder="Buscar por código, estado o texto"
					aria-label="Buscar en el catálogo de errores"
					value={buscar()}
					onInput={(event) => setBuscar(event.currentTarget.value)}
				/>
				<p class="text-sm opacity-70">
					{visibles().length} de {catalogo()?.length ?? 0} errores del catálogo
				</p>
				<div class="overflow-x-auto rounded-box bg-base-100 shadow-sm">
					<table class="table table-sm">
						<thead>
							<tr>
								<th>Código</th>
								<th>HTTP</th>
								<th>Mensaje</th>
								<th>Toast</th>
								<th>Gravedad</th>
								<th>Se guarda</th>
							</tr>
						</thead>
						<tbody>
							<For each={visibles()}>
								{(error) => (
									<tr>
										<td class="font-mono text-xs">{error.code}</td>
										<td>{error.status}</td>
										<td class="text-sm">
											{error.message}
											<Show when={error.hint}>
												<span class="block text-xs opacity-50">{error.hint}</span>
											</Show>
										</td>
										<td>{error.toast ? "sí" : "no"}</td>
										<td>{error.severity}</td>
										<td>{error.persist ? "sí" : "no"}</td>
									</tr>
								)}
							</For>
						</tbody>
					</table>
				</div>
			</Can>
		</div>
	);
}
