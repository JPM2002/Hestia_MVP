import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const target = "http://127.0.0.1:5000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Auth: /auth/login -> /login, /auth/logout -> /logout
      "/auth": {
        target,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/auth/, ""),
      },

      // Ops: /ops/tickets/... -> /tickets/...
      "/ops": {
        target,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/ops/, ""),
      },

      // API: /api/recepcion/list -> /api/recepcion/list
      "/api": {
        target,
        changeOrigin: true,
      },
    },
  },
});
