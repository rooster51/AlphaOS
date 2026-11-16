import { readRuntimeBindings } from "#alphaos-runtime";

export type BackendTarget = "production" | "staging" | "other" | "unconfigured";

/** Classify the configured host without exposing the URL or a credential. */
function backendTarget(base: string | undefined): BackendTarget {
  if (!base) return "unconfigured";
  try {
    const hostname = new URL(base).hostname;
    if (hostname === "alphaos.onrender.com") return "production";
    if (hostname === "alphaos-api-staging.onrender.com") return "staging";
    return "other";
  } catch {
    return "other";
  }
}

export function getServerConfig() {
  const { runtime, bindings } = readRuntimeBindings();
  const values = bindings as Record<string, unknown>;
  const text = (name: string) => typeof values[name] === "string" && (values[name] as string).trim()
    ? values[name] as string : undefined;
  const base = text("ALPHAOS_API_URL");
  const token = text("ALPHAOS_API_TOKEN");
  const demoMode = text("ALPHAOS_DEMO_MODE");
  // Never substitute synthetic examples for research, even if misconfigured.
  const demo = runtime === "node" && demoMode === "true";
  let validUrl = false;
  if (base) {
    try {
      const url = new URL(base);
      validUrl = url.protocol === "https:" && !url.username && !url.password && !url.search && !url.hash;
    } catch { /* Only expose a status, never the value or parser exception. */ }
  }
  const diagnostics = {
    runtime,
    backend_target: backendTarget(base),
    bindings_present: {
      ALPHAOS_API_URL: Boolean(base),
      ALPHAOS_API_TOKEN: Boolean(token),
      ALPHAOS_DEMO_MODE: Boolean(demoMode),
    },
    configuration: !base || !token ? "missing" : validUrl ? "ready" : "invalid",
    demo_enabled: demo,
  };
  return { base, token, demo, diagnostics };
}
