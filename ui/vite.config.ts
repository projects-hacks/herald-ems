/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "node:path";

// Dev: `npm run dev`, then open http://localhost:5173 through an SSH port forward (the mic needs localhost).
// /api and /ws go to your own Herald server (AGENTS.md: ports 8101..8104; 8100 is the demo instance).
const API = process.env.HERALD_API ?? "http://127.0.0.1:8101";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": resolve(import.meta.dirname, "src") } },
  build: {
    outDir: "dist",
    rolldownOptions: {
      // The ED screen (ed.html, UX_PLAN §3.4) is added here by U9.
      input: { now: resolve(import.meta.dirname, "index.html") },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": API,
      "/classic": API,
      "/ws": { target: API.replace("http", "ws"), ws: true },
    },
  },
  test: { environment: "jsdom", include: ["src/test/**/*.test.{ts,tsx,mjs}"] },
});
