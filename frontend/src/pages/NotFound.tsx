import { A } from "@solidjs/router";
import { FiHome } from "solid-icons/fi";

export default function NotFound() {
	return (
		<div class="flex min-h-screen items-center justify-center bg-base-200 p-4">
			<div class="w-full max-w-xs text-center">
				<p class="text-7xl font-black text-primary">404</p>
				<h1 class="mt-2 text-2xl font-bold">Página no encontrada</h1>
				<p class="mt-2 text-sm opacity-70">
					La dirección a la que intentas entrar no existe.
				</p>
				<A href="/" class="btn btn-primary mt-8 gap-2">
					<FiHome size={18} />
					Ir al inicio
				</A>
			</div>
		</div>
	);
}
