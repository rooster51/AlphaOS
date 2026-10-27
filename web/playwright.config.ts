import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser",
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    command: process.env.ALPHAOS_TEST_WORKERS === "true"
      ? "npm run start:vinext -- --host 127.0.0.1 --port 3000"
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
