import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const root = new URL("../../", import.meta.url);
const read = (path) => readFileSync(new URL(path, root), "utf8");

test("Netlify builds only the Next.js app with the pinned supported Node version", () => {
  const config = read("netlify.toml");
  const nextConfig = read("web/next.config.mjs");
  const packageJson = JSON.parse(read("web/package.json"));

  assert.match(config, /base\s*=\s*"web"/);
  assert.match(config, /command\s*=\s*"npm run build:netlify"/);
  assert.match(config, /publish\s*=\s*"\.next"/);
  assert.match(config, /NODE_VERSION\s*=\s*"22\.23\.0"/);
  assert.match(config, /ALPHAOS_NETLIFY_BUILD\s*=\s*"true"/);
  assert.match(config, /\[context\.deploy-preview\.environment\]\s+ALPHAOS_PREVIEW_DIAGNOSTICS\s*=\s*"true"/);
  assert.match(nextConfig, /ALPHAOS_PREVIEW_DIAGNOSTICS:\s*process\.env\.ALPHAOS_PREVIEW_DIAGNOSTICS\s*===\s*"true"/);
  assert.match(config, /\[\[plugins\]\]\s+package\s*=\s*"@netlify\/plugin-nextjs"/);
  assert.equal(packageJson.scripts["build:netlify"], "next build");
  assert.ok(packageJson.devDependencies["@netlify/plugin-nextjs"]);
});

test("Netlify auth runs before Next assets and rate-limits login by client IP", () => {
  const limiter = read("web/netlify/edge-functions/00-login-rate-limit.ts");
  const gate = read("web/netlify/edge-functions/10-auth-gate.ts");
  const nextConfig = read("web/next.config.mjs");
  const tsconfig = JSON.parse(read("web/tsconfig.netlify.json"));

  assert.match(limiter, /path:\s*"\/auth\/login"/);
  assert.match(limiter, /windowLimit:\s*5/);
  assert.match(limiter, /windowSize:\s*60/);
  assert.match(limiter, /aggregateBy:\s*\["ip",\s*"domain"\]/);
  assert.match(gate, /path:\s*"\/\*"/);
  assert.match(gate, /externalLoginRateLimiter:\s*\{\s*limit:/);
  assert.match(gate, /website-auth\/rate-limit/);
  assert.match(gate, /protectWebsite\(request,\s*bindings/);
  assert.match(nextConfig, /tsconfigPath:\s*process\.env\.ALPHAOS_NETLIFY_BUILD/);
  assert(tsconfig.exclude.includes("src/worker.ts"));
  assert(tsconfig.exclude.includes("src/lib/runtime-cloudflare.ts"));
  assert(tsconfig.exclude.includes("cloudflare.config.ts"));
  assert(tsconfig.exclude.includes("vite.config.ts"));
});
