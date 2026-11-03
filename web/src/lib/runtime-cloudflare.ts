import { env } from "cloudflare:workers";

/** Vite resolves #alphaos-runtime here in server builds. No process.env fallback. */
export function readRuntimeBindings() {
  return { runtime: "cloudflare" as const, bindings: env };
}
