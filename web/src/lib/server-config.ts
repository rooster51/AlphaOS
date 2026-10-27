import { readRuntimeBindings } from "#alphaos-runtime";

export function getServerConfig() {
  const { runtime, bindings } = readRuntimeBindings();
  const values = bindings as Record<string, unknown>;
  const text = (name: string) => typeof values[name] === "string" && (values[name] as string).trim()
    ? values[name] as string : undefined;
  const base = text("ALPHAOS_API_URL");
  const token = text("ALPHAOS_API_TOKEN");
  const demoMode = text("ALPHAOS_DEMO_MODE");
  // Workers research never substitutes synthetic examples, even if misconfigured.
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
