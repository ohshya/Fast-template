import { crud, del, get, type Message, post } from "@/core/api";
import type { Session } from "@/modules/auth";

export type User = {
	id: string;
	username: string;
	is_active: boolean;
	dev: boolean;
	role_id: string | null;
	role_name: string | null;
	created_at: string;
	updated_at: string;
	deleted_at: string | null;
	last_login_at: string | null;
};

export type UserCreate = {
	username: string;
	password: string;
	role_id?: string | null;
	is_active?: boolean;
	dev?: boolean;
};

export type UserUpdate = {
	username?: string;
	role_id?: string | null;
	is_active?: boolean;
	dev?: boolean;
};

export const UsersApi = {
	...crud<User, UserCreate, UserUpdate>("/users"),
	resetPassword: (id: string, new_password: string, key?: string) =>
		post<Message>(`/users/${id}/password`, { new_password }, key),
	sessions: (id: string) => get<Session[]>(`/users/${id}/sessions`),
	closeSessions: (id: string) => del<Message>(`/users/${id}/sessions`),
};
