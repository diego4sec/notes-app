import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Proxying /api keeps dev same-origin, so no CORS on the API. Keycloak is
    // deliberately NOT proxied: it must be reached at its real issuer URL or
    // the `iss` claim will not match what the API validates.
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
