import { IoArrowDown, IoArrowUp, IoSwapVertical } from "solid-icons/io";
import {
	type JSX,
	For,
	Show,
	batch,
	createEffect,
	createResource,
	createSignal,
	onCleanup,
} from "solid-js";
import type { History } from "@/components/history";
import { Can } from "@/components/layout";
import type { Confirm } from "@/components/ui";
import { ApiError, type ListParams, type Message, type Page, reportError } from "@/core/api";
import { toLocalInput, toUtcIso } from "@/core/format";
import { LIMITS } from "@/core/limits";
import { notify } from "@/core/notify";

export type FilterValue = string | boolean | string[] | undefined;

type ListQuery = {
	search: string;
	deleted: boolean;
	filters: Record<string, FilterValue>;
	sort: string | undefined;
};

type ListOptions = {
	/** Filas por página (máximo 100). */
	size?: number;
	/** Orden inicial (`columna` o `-columna`); sin él, el propio del recurso. */
	sort?: string;
	/** `false` en recursos sin borrado lógico: no se envía `deleted` ni se ofrece "Ver eliminados". */
	trash?: boolean;
	/** Mientras devuelva `false` no se pide nada (por ejemplo, si falta un permiso). */
	enabled?: () => boolean;
};

/**
 * Estado de un listado paginado: búsqueda con espera, filtros, orden, eliminados y página.
 *
 *   const list = createCrudList(ProductsApi.list);
 *   <For each={list.items()}>...</For>
 *   <Pagination list={list} />
 *
 * Los filtros son los que declara el recurso en el backend: `list.filter("is_active", "true")`,
 * varios valores a la vez con un array (`role_id` A o B) y rangos con `<columna>_from` y
 * `<columna>_to` (ver `RangeFilter`). Cambiar la búsqueda, un filtro, el orden o ver eliminados
 * vuelve a la primera página; si la página actual deja de existir (se borró la última fila),
 * va a la última que quede. Si la petición falla, `error()` dice por qué y `refetch` reintenta.
 */
export function createCrudList<T>(
	fetchPage: (params: ListParams) => Promise<Page<T>>,
	options: ListOptions = {},
) {
	const { size = 20, trash = true } = options;
	const [query, setQuery] = createSignal<ListQuery>({
		search: "",
		deleted: false,
		filters: {},
		sort: options.sort,
	});
	const [typed, setTyped] = createSignal("");
	const [page, setPage] = createSignal(1);
	const [failure, setFailure] = createSignal<ApiError | null>(null);
	const empty: Page<T> = { items: [], total: 0, page: 1, size, pages: 0 };
	const [data, { refetch }] = createResource(
		() =>
			options.enabled?.() === false
				? false
				: {
						...query().filters,
						search: query().search || undefined,
						deleted: trash ? query().deleted : undefined,
						sort: query().sort,
						page: page(),
						size,
					},
		async (params) => {
			try {
				const result = await fetchPage(params);
				setFailure(null);
				return result;
			} catch (error) {
				if (error instanceof ApiError) setFailure(error);
				else reportError(error);
				return empty;
			}
		},
	);
	let timer: ReturnType<typeof setTimeout> | undefined;
	onCleanup(() => clearTimeout(timer));

	function update(changes: Partial<ListQuery>) {
		batch(() => {
			setQuery((current) => ({ ...current, ...changes }));
			setPage(1);
		});
	}

	const pages = () => Math.max(data.latest?.pages ?? 1, 1);

	createEffect(() => {
		if (page() > pages()) setPage(pages());
	});

	return {
		items: () => data.latest?.items ?? [],
		total: () => data.latest?.total ?? 0,
		loading: () => data.loading,
		/** Por qué falló la última petición (el primer error de campo o el mensaje), o `null`. */
		error: () => {
			const error = failure();
			return error ? (Object.values(error.fields)[0] ?? error.message) : null;
		},
		page,
		pages,
		trash,
		deleted: () => query().deleted,
		filters: () => query().filters,
		sort: () => query().sort,
		/** Lo que hay escrito en el cuadro de búsqueda, aunque aún no se haya aplicado. */
		searchText: typed,
		refetch,

		/** Cuántas condiciones hay puestas: búsqueda, filtros y ver eliminados. */
		activeFilters: () =>
			(query().search ? 1 : 0) +
			Object.keys(query().filters).length +
			(trash && query().deleted ? 1 : 0),

		goTo(target: number) {
			setPage(Math.min(Math.max(1, target), pages()));
		},

		search(text: string) {
			setTyped(text);
			clearTimeout(timer);
			timer = setTimeout(() => update({ search: text.trim() }), 300);
		},

		showDeleted(value: boolean) {
			update({ deleted: value });
		},

		/** Pone o quita un filtro; un valor vacío (`""`, `undefined` o `[]`) lo quita. */
		filter(name: string, value: FilterValue | null) {
			const next = { ...query().filters };
			if (value === undefined || value === null || value === "" || (Array.isArray(value) && !value.length)) {
				delete next[name];
			} else {
				next[name] = value;
			}
			update({ filters: next });
		},

		/** Alterna el orden de una columna: ascendente, descendente y el orden propio del recurso. */
		toggleSort(column: string) {
			const current = query().sort;
			update({ sort: current === column ? `-${column}` : current === `-${column}` ? undefined : column });
		},

		/** Cómo está ordenada una columna, o `null` si no lo está. */
		sortOf(column: string): "asc" | "desc" | null {
			if (query().sort === column) return "asc";
			if (query().sort === `-${column}`) return "desc";
			return null;
		},

		/** Quita la búsqueda, los filtros y "ver eliminados"; el orden se queda. */
		clearFilters() {
			clearTimeout(timer);
			setTyped("");
			update({ search: "", deleted: false, filters: {} });
		},
	};
}

export type CrudList<T> = ReturnType<typeof createCrudList<T>>;

/** Búsqueda, filtros propios y conmutador de eliminados encima de un listado. */
export function ListToolbar<T>(props: {
	list: CrudList<T>;
	placeholder?: string;
	/** Longitud máxima de la búsqueda; por defecto la de `search` en los recursos (100). */
	maxLength?: number;
	children?: JSX.Element;
}) {
	return (
		<div class="flex flex-col gap-3 rounded-box bg-base-100 p-3 shadow-sm sm:flex-row sm:flex-wrap sm:items-center">
			<input
				type="search"
				class="input input-sm w-full sm:w-64"
				placeholder={props.placeholder ?? "Buscar"}
				aria-label={props.placeholder ?? "Buscar"}
				maxLength={props.maxLength ?? LIMITS.search}
				value={props.list.searchText()}
				onInput={(event) => props.list.search(event.currentTarget.value)}
			/>
			{props.children}
			<div class="flex items-center gap-3 sm:ml-auto">
				<Show when={props.list.activeFilters() > 0}>
					<button type="button" class="btn btn-ghost btn-xs" onClick={props.list.clearFilters}>
						Limpiar filtros ({props.list.activeFilters()})
					</button>
				</Show>
				<Show when={props.list.trash}>
					<label class="label cursor-pointer gap-2 text-sm">
						<input
							type="checkbox"
							class="toggle toggle-sm"
							checked={props.list.deleted()}
							onChange={(event) => props.list.showDeleted(event.currentTarget.checked)}
						/>
						Ver eliminados
					</label>
				</Show>
			</div>
		</div>
	);
}

export type FilterOption = { value: string; label: string };

/** Desplegable de un filtro por igualdad con una sola opción: `list.filter(name, valor)`. */
export function FilterSelect<T>(props: {
	list: CrudList<T>;
	name: string;
	label: string;
	options: FilterOption[];
	class?: string;
}) {
	const current = () => String(props.list.filters()[props.name] ?? "");

	return (
		<select
			class={`select select-sm w-full sm:w-48 ${props.class ?? ""}`}
			aria-label={props.label}
			onChange={(event) => props.list.filter(props.name, event.currentTarget.value)}
		>
			<option value="" selected={current() === ""}>
				{props.label}
			</option>
			<For each={props.options}>
				{(option) => (
					<option value={option.value} selected={current() === option.value}>
						{option.label}
					</option>
				)}
			</For>
		</select>
	);
}

/** Filtro por igualdad con varias opciones a la vez (una u otra): envía el parámetro repetido. */
export function FilterMulti<T>(props: {
	list: CrudList<T>;
	name: string;
	label: string;
	options: FilterOption[];
}) {
	const selected = () => {
		const value = props.list.filters()[props.name];
		return Array.isArray(value) ? value : [];
	};

	function toggle(value: string, on: boolean) {
		props.list.filter(
			props.name,
			on ? [...selected(), value] : selected().filter((item) => item !== value),
		);
	}

	return (
		<div class="dropdown">
			<div tabindex="0" role="button" class="btn btn-outline btn-sm gap-2 font-normal">
				{props.label}
				<Show when={selected().length > 0}>
					<span class="badge badge-primary badge-xs">{selected().length}</span>
				</Show>
			</div>
			<div
				tabindex="0"
				class="dropdown-content z-10 mt-1 max-h-64 w-64 overflow-y-auto rounded-box bg-base-100 p-2 shadow"
			>
				<For
					each={props.options}
					fallback={<p class="p-2 text-sm opacity-60">No hay opciones.</p>}
				>
					{(option) => (
						<label class="label cursor-pointer justify-start gap-2 px-2 py-1 text-sm">
							<input
								type="checkbox"
								class="checkbox checkbox-xs"
								checked={selected().includes(option.value)}
								onChange={(event) => toggle(option.value, event.currentTarget.checked)}
							/>
							<span class="truncate">{option.label}</span>
						</label>
					)}
				</For>
			</div>
		</div>
	);
}

/** Campo de texto de un filtro por igualdad exacta; se aplica al salir del campo o con Intro. */
export function FilterText<T>(props: {
	list: CrudList<T>;
	name: string;
	label: string;
	maxLength: number;
}) {
	return (
		<input
			class="input input-sm w-full"
			placeholder={props.label}
			aria-label={props.label}
			maxLength={props.maxLength}
			value={String(props.list.filters()[props.name] ?? "")}
			onChange={(event) => props.list.filter(props.name, event.currentTarget.value.trim())}
		/>
	);
}

/**
 * Rango de fechas de una columna que el recurso declara en `range_fields`:
 * envía `<name>_from` y `<name>_to`, con zona horaria y los dos extremos incluidos.
 */
export function RangeFilter<T>(props: { list: CrudList<T>; name: string; label: string }) {
	const from = () => String(props.list.filters()[`${props.name}_from`] ?? "");
	const to = () => String(props.list.filters()[`${props.name}_to`] ?? "");
	const reversed = () => from() !== "" && to() !== "" && from() > to();

	return (
		<fieldset class="flex flex-wrap items-center gap-1 text-sm">
			<legend class="sr-only">{props.label}</legend>
			<span class="opacity-70" aria-hidden="true">
				{props.label}
			</span>
			<input
				type="datetime-local"
				class="input input-sm w-44"
				classList={{ "input-error": reversed() }}
				aria-label={`${props.label}: desde`}
				value={toLocalInput(from())}
				onChange={(event) =>
					props.list.filter(`${props.name}_from`, toUtcIso(event.currentTarget.value))
				}
			/>
			<span aria-hidden="true">–</span>
			<input
				type="datetime-local"
				class="input input-sm w-44"
				classList={{ "input-error": reversed() }}
				aria-label={`${props.label}: hasta`}
				value={toLocalInput(to())}
				onChange={(event) =>
					props.list.filter(`${props.name}_to`, toUtcIso(event.currentTarget.value, true))
				}
			/>
			<Show when={reversed()}>
				<span class="text-error" role="alert">
					«Hasta» es anterior a «Desde»
				</span>
			</Show>
		</fieldset>
	);
}

/** Cabecera de columna que ordena el listado al pulsarla (`sort` del backend). */
export function SortHeader<T>(props: {
	list: CrudList<T>;
	column: string;
	children: JSX.Element;
	class?: string;
}) {
	const state = () => props.list.sortOf(props.column);

	return (
		<th
			class={props.class}
			aria-sort={state() === "asc" ? "ascending" : state() === "desc" ? "descending" : "none"}
		>
			<button
				type="button"
				class="inline-flex items-center gap-1 font-semibold hover:underline"
				onClick={() => props.list.toggleSort(props.column)}
			>
				{props.children}
				<span aria-hidden="true" classList={{ "opacity-30": state() === null }}>
					{state() === "asc" ? <IoArrowUp /> : state() === "desc" ? <IoArrowDown /> : <IoSwapVertical />}
				</span>
			</button>
		</th>
	);
}

/** Fila final de una tabla: cargando, error con "Reintentar" o "no hay resultados". */
function ListStatus<T>(props: { list: CrudList<T>; columns: number; empty: string }) {
	return (
		<Show
			when={props.list.error()}
			fallback={
				<Show
					when={!props.list.loading()}
					fallback={
						<Show when={props.list.items().length === 0}>
							<tr>
								<td colspan={props.columns} class="py-6 text-center">
									<span class="loading loading-spinner" />
								</td>
							</tr>
						</Show>
					}
				>
					<Show when={props.list.items().length === 0}>
						<tr>
							<td colspan={props.columns} class="py-6 text-center opacity-60">
								{props.list.activeFilters() > 0
									? "Ningún resultado con estos filtros."
									: props.empty}
							</td>
						</tr>
					</Show>
				</Show>
			}
		>
			{(message) => (
				<tr>
					<td colspan={props.columns} class="py-6 text-center">
						<span class="text-error">{message()}</span>
						<button type="button" class="btn btn-xs ml-3" onClick={() => props.list.refetch()}>
							Reintentar
						</button>
					</td>
				</tr>
			)}
		</Show>
	);
}

/**
 * Tabla de un listado: cabecera (`head`: las celdas `<th>` o `SortHeader`), filas (`children`)
 * y el estado de la carga debajo. Se atenúa mientras recarga.
 */
export function ListTable<T>(props: {
	list: CrudList<T>;
	columns: number;
	empty: string;
	head: JSX.Element;
	children: JSX.Element;
	class?: string;
}) {
	return (
		<div
			class="overflow-x-auto rounded-box bg-base-100 shadow-sm transition-opacity"
			classList={{ "opacity-60": props.list.loading() && props.list.items().length > 0 }}
			aria-busy={props.list.loading()}
		>
			<table class={`table table-sm ${props.class ?? ""}`}>
				<thead>
					<tr>{props.head}</tr>
				</thead>
				<tbody>
					{props.children}
					<ListStatus list={props.list} columns={props.columns} empty={props.empty} />
				</tbody>
			</table>
		</div>
	);
}

/** Total de registros y botones de página debajo de un listado. */
export function Pagination<T>(props: { list: CrudList<T> }) {
	return (
		<div class="flex flex-col items-center justify-between gap-2 sm:flex-row">
			<span class="text-sm opacity-60" aria-live="polite">
				{props.list.total()} {props.list.total() === 1 ? "registro" : "registros"}
			</span>
			<div class="join">
				<button
					type="button"
					class="join-item btn btn-sm"
					disabled={props.list.page() <= 1}
					onClick={() => props.list.goTo(props.list.page() - 1)}
					aria-label="Página anterior"
				>
					«
				</button>
				<span class="join-item btn btn-sm pointer-events-none">
					Página {props.list.page()} de {props.list.pages()}
				</span>
				<button
					type="button"
					class="join-item btn btn-sm"
					disabled={props.list.page() >= props.list.pages()}
					onClick={() => props.list.goTo(props.list.page() + 1)}
					aria-label="Página siguiente"
				>
					»
				</button>
			</div>
		</div>
	);
}

type Deletable = { id: string; deleted_at: string | null };

type RecordApi = {
	remove: (id: string) => Promise<Message>;
	restore: (id: string) => Promise<unknown>;
	hardDelete: (id: string) => Promise<Message>;
};

/**
 * Acciones de una fila: historial, editar, eliminar, restaurar y borrar definitivamente.
 *
 * Cada botón aparece solo con su permiso (`<resource>.update`, `<resource>.delete`...).
 * `resource` es la clave de `crud_permissions`; `entityType`, la tabla del historial,
 * que por convención coincide con ella. `children` añade acciones propias.
 * `deleteBlocked` deja "Eliminar" desactivado y explica por qué (la propia cuenta, un rol en uso).
 */
export function RowActions<T extends Deletable>(props: {
	item: T;
	label: string;
	resource: string;
	entityType?: string;
	api: RecordApi;
	confirm: Confirm;
	history: History;
	onEdit?: (item: T) => void;
	onChanged: () => void;
	deleteBlocked?: string;
	children?: JSX.Element;
}) {
	const key = (action: string) => `${props.resource}.${action}`;

	function eliminar() {
		props.confirm.ask({
			title: `Eliminar ${props.label}`,
			message: "Dejará de aparecer en los listados. Se puede restaurar después.",
			confirmLabel: "Eliminar",
			action: async () => {
				notify.success((await props.api.remove(props.item.id)).detail);
				props.onChanged();
			},
		});
	}

	async function restaurar() {
		try {
			await props.api.restore(props.item.id);
		} catch (error) {
			reportError(error);
			return;
		}
		notify.success(`${props.label} restaurado`);
		props.onChanged();
	}

	function borrar() {
		props.confirm.ask({
			title: `Borrar ${props.label} para siempre`,
			message: "La fila desaparece de la base de datos. Solo queda su rastro en la auditoría.",
			confirmLabel: "Borrar definitivamente",
			action: async () => {
				notify.success((await props.api.hardDelete(props.item.id)).detail);
				props.onChanged();
			},
		});
	}

	return (
		<div class="flex flex-wrap justify-end gap-1">
			<Can permission="events.history">
				<button
					type="button"
					class="btn btn-ghost btn-xs"
					onClick={() =>
						props.history.open(props.entityType ?? props.resource, props.item.id, props.label)
					}
				>
					Historial
				</button>
			</Can>
			<Show
				when={!props.item.deleted_at}
				fallback={
					<>
						<Can permission={key("restore")}>
							<button type="button" class="btn btn-ghost btn-xs text-success" onClick={restaurar}>
								Restaurar
							</button>
						</Can>
						<Can permission={key("hard_delete")}>
							<button type="button" class="btn btn-ghost btn-xs text-error" onClick={borrar}>
								Borrar
							</button>
						</Can>
					</>
				}
			>
				<Show when={props.onEdit}>
					{(editar) => (
						<Can permission={key("update")}>
							<button
								type="button"
								class="btn btn-ghost btn-xs"
								onClick={() => editar()(props.item)}
							>
								Editar
							</button>
						</Can>
					)}
				</Show>
				{props.children}
				<Can permission={key("delete")}>
					<button
						type="button"
						class="btn btn-ghost btn-xs text-error"
						disabled={!!props.deleteBlocked}
						title={props.deleteBlocked}
						onClick={eliminar}
					>
						Eliminar
					</button>
				</Can>
			</Show>
		</div>
	);
}
