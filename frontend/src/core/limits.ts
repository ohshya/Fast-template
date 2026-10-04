/** Longitudes máximas de los campos de texto. Deben coincidir con los `max_length` de los esquemas del backend. */
export const LIMITS = {
	username: 50,
	password: 128,
	name: 100,
	description: 255,
	search: 100,
	label: 255,
	identifier: 50,
	errorCode: 20,
} as const;
