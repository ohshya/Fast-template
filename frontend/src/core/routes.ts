/** Destino tras iniciar sesión: solo rutas de esta misma aplicación, nunca otra web. */
export function safeNext(next: string | null | undefined): string {
	if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return "/";
	return next;
}
