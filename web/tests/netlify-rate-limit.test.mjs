import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { consumeSharedLoginAttempt } from "../netlify/edge-functions/10-auth-gate.ts";

const originalFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = originalFetch;
});

const bindings = {
  ALPHAOS_API_URL: "https://api.alphaos.example",
  ALPHAOS_API_TOKEN: "synthetic-server-token",
};

test("Netlify shared limiter calls the authenticated Render endpoint and validates its decision", async () => {
  globalThis.fetch = async (input, init) => {
    assert.equal(String(input), "https://api.alphaos.example/v1/website-auth/rate-limit");
    assert.equal(init.method, "POST");
    assert.equal(init.redirect, "manual");
    assert.equal(init.cache, "no-store");
    assert.equal(init.headers.Authorization, "Bearer synthetic-server-token");
    assert.equal(init.body, "{}");
    return Response.json({ allowed: false, retry_after_seconds: 31 });
  };
  assert.deepEqual(await consumeSharedLoginAttempt(bindings), {
    allowed: false,
    retryAfterSeconds: 31,
  });
});

test("Netlify fails closed on missing configuration, endpoint failures, and malformed outcomes", async () => {
  await assert.rejects(consumeSharedLoginAttempt({ ...bindings, ALPHAOS_API_TOKEN: undefined }));
  await assert.rejects(consumeSharedLoginAttempt({ ...bindings, ALPHAOS_API_URL: "http://api.example" }));
  for (const response of [
    new Response("redirect", { status: 307, headers: { Location: "https://attacker.example" } }),
    new Response("unavailable", { status: 503 }),
    Response.json({ allowed: "true", retry_after_seconds: 0 }),
    Response.json({ allowed: false, retry_after_seconds: 0 }),
    Response.json({ allowed: true, retry_after_seconds: 1 }),
    new Response("x".repeat(513)),
  ]) {
    globalThis.fetch = async () => response;
    await assert.rejects(consumeSharedLoginAttempt(bindings));
  }
});
