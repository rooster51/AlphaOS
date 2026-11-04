import assert from "node:assert/strict";
import { test } from "node:test";
import { getServerConfig } from "../src/lib/server-config.ts";
import { GET } from "../src/app/api/health/route.ts";

test("Render configuration is read at request time; diagnostics never include values", async () => {
  const names = ["ALPHAOS_API_URL", "ALPHAOS_API_TOKEN", "ALPHAOS_DEMO_MODE"];
  const saved = names.map(name => process.env[name]);
  try {
    names.forEach(name => delete process.env[name]);
    assert.equal(getServerConfig().diagnostics.configuration, "missing");
    process.env.ALPHAOS_API_URL = "https://runtime.example.test";
    process.env.ALPHAOS_API_TOKEN = "private-runtime-token";
    process.env.ALPHAOS_DEMO_MODE = "false";
    assert.equal(getServerConfig().token, "private-runtime-token");
    let response = await GET();
    const body = await response.json();
    assert.equal(body.research_configuration.configuration, "ready");
    assert.equal(body.backend_verification, "not_assessed");
    assert.equal(response.headers.get("cache-control"), "no-store");
    assert(!JSON.stringify(body).includes("private-runtime-token"));
    assert(!JSON.stringify(body).includes("runtime.example.test"));
    process.env.ALPHAOS_API_TOKEN = "changed-after-module-import";
    assert.equal(getServerConfig().token, "changed-after-module-import");
    process.env.ALPHAOS_API_URL = "https://user:password@example.test";
    assert.equal(getServerConfig().diagnostics.configuration, "invalid");
    process.env.ALPHAOS_API_TOKEN = " ";
    assert.equal(getServerConfig().diagnostics.configuration, "missing");
  } finally {
    names.forEach((name, i) => saved[i] === undefined ? delete process.env[name] : process.env[name] = saved[i]);
  }
});
