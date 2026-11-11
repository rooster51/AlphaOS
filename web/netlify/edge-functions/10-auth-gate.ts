import { protectWebsite, type AuthBindings } from "../../src/lib/website-auth.ts";

type EdgeContext = {
  next(): Promise<Response>;
};

declare const Netlify: {
  env: {
    get(name: string): string | undefined;
  };
};

export async function consumeSharedLoginAttempt(bindings: AuthBindings) {
  const base = bindings.ALPHAOS_API_URL;
  const token = bindings.ALPHAOS_API_TOKEN;
  if (!base || !token) throw new Error("Shared login limiter is not configured");
  const parsed = new URL(base);
  if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error("Shared login limiter configuration is invalid");
  }
  const response = await fetch(new URL("/v1/website-auth/rate-limit", parsed), {
    method: "POST",
    redirect: "manual",
    cache: "no-store",
    signal: AbortSignal.timeout(6000),
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: "{}",
  });
  if (response.status !== 200) {
    await response.body?.cancel();
    throw new Error("Shared login limiter is unavailable");
  }
  const reader = response.body?.getReader();
  if (!reader) throw new Error("Shared login limiter response is invalid");
  const chunks: Uint8Array[] = [];
  let length = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.length;
      if (length > 512) {
        await reader.cancel();
        throw new Error("Shared login limiter response is too large");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.length;
  }
  const result: unknown = JSON.parse(new TextDecoder().decode(bytes));
  if (!result || typeof result !== "object" || Array.isArray(result)) {
    throw new Error("Shared login limiter response is invalid");
  }
  const outcome = result as Record<string, unknown>;
  if (Object.keys(outcome).length !== 2 ||
      typeof outcome.allowed !== "boolean" ||
      typeof outcome.retry_after_seconds !== "number" ||
      !Number.isInteger(outcome.retry_after_seconds) ||
      outcome.retry_after_seconds < 0 ||
      outcome.retry_after_seconds > 60 ||
      (outcome.allowed && outcome.retry_after_seconds !== 0) ||
      (!outcome.allowed && outcome.retry_after_seconds === 0)) {
    throw new Error("Shared login limiter response is invalid");
  }
  return { allowed: outcome.allowed, retryAfterSeconds: outcome.retry_after_seconds };
}

export default function authGate(request: Request, context: EdgeContext) {
  const bindings: AuthBindings = {
    ALPHAOS_API_URL: Netlify.env.get("ALPHAOS_API_URL"),
    ALPHAOS_API_TOKEN: Netlify.env.get("ALPHAOS_API_TOKEN"),
    ALPHAOS_PASSWORD_HASH: Netlify.env.get("ALPHAOS_PASSWORD_HASH"),
    ALPHAOS_SESSION_KEY: Netlify.env.get("ALPHAOS_SESSION_KEY"),
  };
  return protectWebsite(request, bindings, () => context.next(), {
    externalLoginRateLimiter: { limit: () => consumeSharedLoginAttempt(bindings) },
  });
}

export const config = {
  path: "/*",
};
