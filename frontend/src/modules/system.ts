import { get, quiet } from "@/core/api";

export type Health = { status: string; database: string };

export type SystemInfo = {
	name: string;
	version: string;
	debug: boolean;
	access_expire_minutes: number;
	refresh_expire_days: number;
	max_sessions_per_user: number;
	password_min_length: number;
	login_attempts: number;
	login_attempts_per_ip: number;
	login_window_seconds: number;
};

export type PermissionInfo = {
	id: number;
	key: string;
	group: string;
	description: string;
	scope: "public" | "authenticated" | "role" | "dev";
	assignable: boolean;
	endpoint: string | null;
	granted: boolean;
};

export type ErrorInfo = {
	code: string;
	status: number;
	message: string;
	toast: boolean;
	severity: string;
	persist: boolean;
	hint: string;
};

export const SystemApi = {
	health: () => quiet<Health>("get", "/system/health"),
	info: () => get<SystemInfo>("/system/info"),
	permissions: () => get<PermissionInfo[]>("/system/permissions"),
	errors: () => get<ErrorInfo[]>("/system/errors"),
	testError: (status: number, toast: boolean) =>
		get<unknown>(`/system/test-error/${status}`, { toast }),
};
