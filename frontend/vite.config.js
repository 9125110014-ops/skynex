import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// The browser talks to /api on the same address; Vite forwards it to the backend.
const target = process.env.BACKEND_URL || "http://backend:8000";
export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: true,
    proxy: { "/api": { target, changeOrigin: true, ws: true, rewrite: p => p.replace(/^\/api/, "") } },
  },
});
