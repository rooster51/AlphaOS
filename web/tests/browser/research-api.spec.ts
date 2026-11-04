import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

// These requests reach the actual server, including workerd in the Workers job.
// Successful research envelopes and forwarding are covered by route unit tests;
// browser scenario tests cover rendering without contacting the Render backend.
for (const [path, data] of [
  ["market", { symbol: "QQQ" }],
  ["structure", JSON.parse(readFileSync("tests/fixtures/structure-parity.json", "utf8")).request],
  ["structures/compare", JSON.parse(readFileSync("tests/fixtures/structure-compare-parity.json", "utf8")).request],
] as const) {
  test(`${path} validates requests and fails closed without backend credentials`, async ({ request }) => {
    const invalid = await request.post(`/api/research/${path}`, { data: {} });
    expect(invalid.status()).toBe(400);
    const response = await request.post(`/api/research/${path}`, { data });
    expect(response.status()).toBe(503);
    expect(response.headers()["cache-control"]).toBe(process.env.ALPHAOS_TEST_WORKERS === "true" ? "private, no-store, max-age=0" : "no-store");
    expect(await response.json()).toMatchObject({ status: "unavailable", code: "backend_not_configured" });
  });
}

test("health remains independent of backend and market health", async ({ request }) => {
  const response = await request.get("/api/health");
  expect(response.ok()).toBe(true);
  expect(await response.json()).toMatchObject({ status: "ok", backend_verification: "not_assessed" });
});
