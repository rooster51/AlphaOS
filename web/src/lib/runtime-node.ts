/** Next.js/Render only. Read on every call, never snapshot secrets at import time. */
export function readRuntimeBindings() {
  return { runtime: "node" as const, bindings: process.env };
}
