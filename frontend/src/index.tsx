import { Router, type RouteDefinition } from "@solidjs/router";
import { ErrorBoundary, lazy } from "solid-js";
import { render } from "solid-js/web";
import { Toaster } from "solid-toast";
import { CrashNotice, ProtectedRoute } from "@/components/layout";
import { ServerStatusGate } from "@/components/ServerStatusGate";
import { ApiError, reportError } from "@/core/api";
import { auth } from "@/core/auth";
import "./index.css";

const Account = lazy(() => import("@/pages/Account"));
const Audit = lazy(() => import("@/pages/Audit"));
const Debug = lazy(() => import("@/pages/Debug"));
const Home = lazy(() => import("@/pages/Home"));
const Login = lazy(() => import("@/pages/Login"));
const NotFound = lazy(() => import("@/pages/NotFound"));
const Roles = lazy(() => import("@/pages/Roles"));
const Users = lazy(() => import("@/pages/Users"));

/**
 * Todas las rutas, a la vista. Una página nueva se importa arriba y se añade aquí; si debe
 * salir en el menú, también en `NAV` de `components/layout.tsx`.
 *
 * `ServerStatusGate` vigila la conexión en todas; `ProtectedRoute` exige sesión y pone la
 * barra superior en las de dentro; `NotFound` atiende cualquier otra dirección.
 */
const routes: RouteDefinition[] = [
	{
		component: ServerStatusGate,
		children: [
			{ path: "/login", component: Login },
			{
				component: ProtectedRoute,
				children: [
					{ path: "/", component: Home },
					{ path: "/users", component: Users },
					{ path: "/roles", component: Roles },
					{ path: "/audit", component: Audit },
					{ path: "/debug", component: Debug },
					{ path: "/account", component: Account },
				],
			},
			{ path: "*", component: NotFound },
		],
	},
];

auth.load();

window.addEventListener("unhandledrejection", (event) => {
	if (event.reason instanceof ApiError) event.preventDefault();
	else reportError(event.reason);
});

render(
	() => (
		<>
			<Toaster />
			<ErrorBoundary
				fallback={(error, reset) => (
					<div class="mx-auto max-w-xl p-4">
						<CrashNotice error={error} reset={reset} />
					</div>
				)}
			>
				<Router>{routes}</Router>
			</ErrorBoundary>
		</>
	),
	document.getElementById("root")!,
);
