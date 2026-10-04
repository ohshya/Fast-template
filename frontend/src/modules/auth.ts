import { del, get, type Message, post, quiet } from "@/core/api";

export type Me = {
	id: string;
	username: string;
	is_active: boolean;
	dev: boolean;
	role_id: string | null;
	role_name: string | null;
	permissions: number[];
	permission_keys: string[];
	last_login_at: string | null;
};

export type Session = {
	id: string;
	device: string;
	ip_address: string | null;
	created_at: string;
	last_activity: string;
	expires_at: string;
	is_current: boolean;
};

export const AuthApi = {
	me: () => get<Me>("/auth/me"),
	login: (username: string, password: string) =>
		post<Me>("/auth/login", { username, password }),
	renew: () => post<unknown>("/auth/refresh"),
	logout: () => quiet<Message>("post", "/auth/logout"),
	sessions: () => get<Session[]>("/auth/sessions"),
	closeSession: (id: string) => del<Message>(`/auth/sessions/${id}`),
	closeOtherSessions: () => post<Message>("/auth/sessions/revoke-others"),
	changePassword: (current_password: string, new_password: string, key?: string) =>
		post<Message>("/auth/password", { current_password, new_password }, key),
};
