import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import solid from "vite-plugin-solid";
import { defineConfig } from "vite";

export default defineConfig({
	plugins: [tailwindcss(), solid()],
	resolve: {
		alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
	},
	server: {
		proxy: {
			"/api": {
				target: process.env.BACKEND_URL ?? "http://127.0.0.1:8000",
				changeOrigin: false,
			},
		},
	},
});
