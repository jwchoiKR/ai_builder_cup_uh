import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Dev: the FastAPI backend runs on :8000; /api (REST and SSE) is proxied without buffering.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.API_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
        ws: true, // microphone audio WebSocket (P4)
        configure: (proxy) => {
          proxy.on("proxyRes", (res) => {
            if (String(res.headers["content-type"] ?? "").startsWith("text/event-stream")) {
              res.headers["cache-control"] = "no-cache";
              res.headers["x-accel-buffering"] = "no";
            }
          });
        },
      },
    },
  },
  build: { outDir: "dist", emptyOutDir: true, sourcemap: true },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: { modules: { classNameStrategy: "non-scoped" } },
  },
});
