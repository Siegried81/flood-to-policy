import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Port 5190 so it never collides with the other projects' dev servers
// (grounded-rag runs on 5180). The proxy means the browser only ever talks to
// one origin, so there is no CORS to debug at 17:00 on a Friday.
// VITE_PORT and VITE_API override both for scripts/screenshots, which runs its
// own servers on other ports so it never collides with a demo already running.
//
// VITE_BASE sets the public path for a static deployment under a sub-path
// (GitHub Pages serves a project at /<repo>/); the default "/" is what the
// FastAPI mount and an HF Static Space expect. VITE_STATIC=1 builds the
// API-free variant: see `STATIC_BUILD` in src/api.js.
export default defineConfig({
  base: process.env.VITE_BASE || "/",
  plugins: [react()],
  server: {
    port: Number(process.env.VITE_PORT) || 5190,
    strictPort: Boolean(process.env.VITE_PORT),
    proxy: { "/api": process.env.VITE_API || "http://localhost:8010" },
  },
});
