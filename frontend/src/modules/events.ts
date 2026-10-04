import { get, type ListParams, type Page } from "@/core/api";

export type EventCategory = "domain" | "security" | "error" | "system";

export type Change = { before: unknown; after: unknown };

export type AuditEvent = {
	id: string;
	sequence: number;
	created_at: string;
	category: EventCategory;
	action: string;
	severity: string;
	message: string;
	actor_id: string | null;
	actor_username: string | null;
	actor_role_id: string | null;
	entity_type: string | null;
	entity_id: string | null;
	entity_label: string | null;
	changes: Record<string, Change> | null;
	error_code: string | null;
	status_code: number | null;
	permission_id: number | null;
	method: string | null;
	path: string | null;
	request_id: string | null;
	ip: string | null;
};

export type AuditEventDetail = AuditEvent & {
	snapshot: Record<string, unknown> | null;
	context: Record<string, unknown> | null;
	user_agent: string | null;
	prev_hash: string | null;
	hash: string;
	is_intact: boolean;
};

export type EventStats = {
	total: number;
	by_category: Record<string, number>;
	by_action: Record<string, number>;
	by_severity: Record<string, number>;
	last_event_at: string | null;
};

export type IntegrityReport = {
	total: number;
	checked: number;
	intact: boolean;
	first_broken_id: string | null;
	detail: string;
	append_only: boolean;
};

/** Qué verificar: toda la cadena (sin nada), un periodo (fechas en ISO con zona horaria) o un evento. */
export type VerifyParams = { date_from?: string; date_to?: string; event_id?: string };

/** Categorías de un evento y cómo se llaman en pantalla. */
export const EVENT_CATEGORIES: Record<EventCategory, string> = {
	domain: "Cambios de datos",
	security: "Seguridad",
	error: "Errores",
	system: "Sistema",
};

/** Acciones de un evento (`EventAction` del backend) y cómo se llaman en pantalla. */
export const EVENT_ACTIONS: Record<string, string> = {
	create: "Creación",
	update: "Edición",
	delete: "Eliminación",
	restore: "Restauración",
	hard_delete: "Borrado definitivo",
	login: "Inicio de sesión",
	logout: "Cierre de sesión",
	session_revoked: "Sesión cerrada",
	password_change: "Cambio de contraseña",
	access_denied: "Acceso denegado",
	error: "Error",
	system: "Sistema",
};

/** Gravedades de un evento (de menos a más). */
export const EVENT_SEVERITIES = ["info", "warning", "error", "critical"] as const;

/**
 * Filtros de `list` (todos opcionales y combinables): `category`, `action`, `severity`,
 * `actor_id`, `actor_username`, `role_id` (rol del actor entonces), `current_role_id`
 * (rol del actor ahora), `entity_type`, `entity_id`, `error_code`, `request_id`,
 * `permission_id`, `method`, `path`, `ip`, `search` (texto del mensaje), `date_from` y
 * `date_to` (ISO con zona horaria: usa `toUtcIso`), `only_changes` y `order`
 * (`recent` u `oldest`), además de `page` y `size`.
 */
export const EventsApi = {
	list: (filters: ListParams = {}) => get<Page<AuditEvent>>("/events/", filters),
	read: (id: string) => get<AuditEventDetail>(`/events/${id}`),
	history: (entityType: string, entityId: string, params: ListParams = {}) =>
		get<Page<AuditEventDetail>>(`/events/history/${entityType}/${entityId}`, params),
	stats: () => get<EventStats>("/events/stats"),
	verify: (params: VerifyParams = {}) => get<IntegrityReport>("/events/verify", params),
};
