// End-to-end tests (DEV_SPEC §14.4). They run against a backend that serves the built frontend
// (`npm run build`) with mock providers, so the recorded agent outputs make every run deterministic:
//   cd backend && LLM_PROVIDER=mock STT_PROVIDER=mock uv run uvicorn app.main:create_app --factory --port 8002
//   cd frontend && npm run e2e
// E2E_START=1 starts that backend automatically. E2E_BASE points the tests elsewhere (e.g. real models).
// The bundled Chromium cannot start on the dev machine (OS policy), so the installed Edge is used.
import { defineConfig } from "@playwright/test";

const BASE = process.env.E2E_BASE ?? "http://127.0.0.1:8002";

export default defineConfig({
  testDir: "e2e",
  testMatch: "*.spec.ts",
  timeout: 8 * 60_000,
  expect: { timeout: 15_000 },
  workers: 1,
  fullyParallel: false,
  retries: 0,
  outputDir: "test-results",
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: BASE,
    // D-479: Playwright's bundled Chromium unless PW_CHANNEL is set; launching the installed Edge on this Entra-joined
    // PC tries a Windows sign-in that fails, and the user's account got locked (10/16)
    channel: process.env.PW_CHANNEL || undefined,
    viewport: { width: 1920, height: 1080 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 15_000,
  },
  webServer: process.env.E2E_START
    ? {
        command: "uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8002",
        cwd: "../backend",
        url: `${BASE}/api/health`,
        env: { LLM_PROVIDER: "mock", STT_PROVIDER: "mock", LOG_LEVEL: "WARNING" },
        reuseExistingServer: false,
        timeout: 60_000,
      }
    : undefined,
});
