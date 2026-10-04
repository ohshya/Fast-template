import { crud } from "@/core/api";

export type Role = {
	id: string;
	name: string;
	description: string;
	permissions: number[];
	users_count: number;
	created_at: string;
	updated_at: string;
	deleted_at: string | null;
};

export type RoleCreate = {
	name: string;
	description?: string;
	permissions: number[];
};

export const RolesApi = crud<Role, RoleCreate>("/roles");
