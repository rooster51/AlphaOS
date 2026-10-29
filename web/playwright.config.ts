import { defineConfig, devices } from "@playwright/test";
import { setupWorkerBrowserAuth } from "./tests/browser-auth-setup.mjs";

const workers = process.env.ALPHAOS_TEST_WORKERS === "true";

export default defineConfig({
  testDir: "./tests/browser",
  fullyParallel: true,
  reporter: "list",
  globalTeardown: workers ? "./tests/browser-auth-setup.mjs" : undefined,
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    storageState: workers ? setupWorkerBrowserAuth() : undefined,
    extraHTTPHeaders: workers ? { Origin: "http://127.0.0.1:3000" } : undefined,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    command: process.env.ALPHAOS_TEST_WORKERS === "true"
      ? "node tests/worker-browser-server.mjs"
      : "npm run start -- --hostname 127.0.0.1",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: false,
    timeout: 30_000,
    env: {
      ALPHAOS_API_TOKEN: "",
      ALPHAOS_API_URL: "",
      ALPHAOS_DEMO_MODE: "false",
    },
  },
});
