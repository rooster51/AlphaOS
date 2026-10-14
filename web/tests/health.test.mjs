import assert from "node:assert/strict";
import { test } from "node:test";
import { GET } from "../src/app/api/health/route.ts";

test("health endpoint reports process health without claiming backend or market health", async () => {
  const response = await GET();
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(body.status, "ok");
  assert.equal(body.backend_verification, "not_assessed");
  assert.equal(body.market_freshness, "not_assessed");
  assert.equal(body.account_access, "disabled");
});
