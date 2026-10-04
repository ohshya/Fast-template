import { useSearchParams } from "@solidjs/router";
import { For, Match, Show, Switch } from "solid-js";
import { NoAccess, canUseDebug } from "@/components/layout";
import { PageHeader } from "@/components/ui";
import { ErrorsPanel } from "@/features/debug/ErrorsPanel";
import { PermissionsPanel } from "@/features/debug/PermissionsPanel";
import { RequestsPanel } from "@/features/debug/RequestsPanel";
import { StatusPanel } from "@/features/debug/StatusPanel";

const TABS = [
	{ id: "status", title: "Estado" },
	{ id: "requests", title: "Peticiones" },
	{ id: "errors", title: "Errores" },
	{ id: "permissions", title: "Permisos" },
] as const;

/**
 * Herramientas de la plantilla para desarrolladores: estado de la conexión y de la cuenta,
 * registro de peticiones, circuito de errores y catálogo de permisos. Solo la ven los dev y
 * solo con el servidor en modo desarrollo (`DEBUG=true`): en producción ni el menú ni la ruta
 * la ofrecen. La pestaña activa va en la dirección (`/debug?tab=requests`).
 */
export default function Debug() {
	const [params, setParams] = useSearchParams();
	const active = () => TABS.find((tab) => tab.id === params.tab)?.id ?? TABS[0].id;

	return (
		<Show when={canUseDebug()} fallback={<NoAccess />}>
			<PageHeader title="Debug" subtitle="Herramientas para desarrollar sobre la plantilla." />

			<div role="tablist" class="tabs tabs-border">
				<For each={TABS}>
					{(tab) => (
						<button
							type="button"
							role="tab"
							class="tab"
							classList={{ "tab-active": active() === tab.id }}
							aria-selected={active() === tab.id}
							onClick={() => setParams({ tab: tab.id })}
						>
							{tab.title}
						</button>
					)}
				</For>
			</div>

			<Switch>
				<Match when={active() === "status"}>
					<StatusPanel />
				</Match>
				<Match when={active() === "requests"}>
					<RequestsPanel />
				</Match>
				<Match when={active() === "errors"}>
					<ErrorsPanel />
				</Match>
				<Match when={active() === "permissions"}>
					<PermissionsPanel />
				</Match>
			</Switch>
		</Show>
	);
}
