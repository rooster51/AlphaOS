import { bindings, defineConfig, defineWorker } from "cf/config";

export default defineConfig({
  worker: defineWorker({
    name: "alphaos-web",
    entrypoint: "vinext/server/fetch-handler",
    compatibilityDate: "2026-10-26",
    compatibilityFlags: ["nodejs_compat"],
    observability: {
      enabled: true,
      logs: { enabled: true },
      traces: { enabled: true, headSamplingRate: 0.01 },
    },
    assets: {
      htmlHandling: "none",
      notFoundHandling: "none",
      runWorkerFirst: ["/*", "!/_next/static/*", "!/*/_next/static/*"],
    },
    env: {
      ASSETS: bindings.assets(),
      // Values are supplied only at runtime, separately for production/previews.
      ALPHAOS_API_URL: bindings.secret(),
      ALPHAOS_API_TOKEN: bindings.secret(),
      ALPHAOS_DEMO_MODE: { type: "text", value: "false" },
    },
  }),
});
