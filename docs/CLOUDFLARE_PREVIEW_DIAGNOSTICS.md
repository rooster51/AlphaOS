# PR #67: Preview research configuration

## Confirmed cause (October 27, 2026)

Read-only Cloudflare deployment metadata for `alphaos-web`, Preview
`codex/cloudflare-workers` (slug `codex-cloudflare-workers`), shows that **both
existing Preview deployments lack the API URL and token bindings**. The latest
deployment at `2026-10-27T15:06:42Z` contains only `ASSETS` and
`ALPHAOS_DEMO_MODE`. Only binding names were inspected; no values were printed.
The `alphaos-web` production Worker has no deployed version. No Cloudflare, Render,
MCP, or secret settings were changed during this investigation.

The message on QQQ/SPY is therefore an accurate fail-closed response before an
upstream request is made. A rebuild cannot create runtime secret values from
`bindings.secret()` declarations. Cloudflare Build variables, production
runtime secrets, and Preview runtime secrets are different settings. Moreover,
changes to **Previews Base secrets apply only to newly created Previews**;
rebuilding an existing Preview does not copy updated Base secrets into it.
There is also a confirmed project/scope mismatch: the GitHub build integration
is attached to the different Worker **alphaos**. Its production build settings
list both credential names as build environment variables; its runtime binding
list is empty. Its Preview build configuration has root `/`, no build command,
the default `npx wrangler preview` command, and no build variable names.
The source configuration and the actual rendering Preview target **alphaos-web**.
Settings on `alphaos` do not configure `alphaos-web`. These observations inspect
names/settings only, not secret values; other dashboard scopes were not audited.

See [Cloudflare Preview secret configuration](https://developers.cloudflare.com/workers/previews/configuration/#secrets).

## Runtime fix and diagnostics

`getServerConfig()` now reads on every request. The package import
`#alphaos-runtime` resolves to `runtime-node.ts` for Next.js/Render, where it
reads Node `process.env` at call time. Vite explicitly aliases the same import
to `runtime-cloudflare.ts`, which reads native `env` from `cloudflare:workers`.
No process-environment fallback or module-level secret snapshot is used in
Workers. This follows [Cloudflare's vinext bindings guidance](https://developers.cloudflare.com/workers/framework-guides/web-apps/nextjs/#access-cloudflare-bindings).
The npm `prebuild` and `pretypecheck` hooks generate Cloudflare types locally,
so the Next.js/Render path also type-checks the Worker accessor on a clean
checkout without requiring a Cloudflare login or a remote API call.

Market research, structure research, comparison, health and the legacy market/
strategy helpers share this accessor. Render continues using its server-side
environment. Worker demo substitution is disabled even if
`ALPHAOS_DEMO_MODE=true`; no synthetic data replaces unavailable research.
The market deadline remains **12,000 ms**. Structure research retains its
separate existing budget. Existing response validation remains enforced.

`GET /api/health` adds `research_configuration`, reporting only:

- Runtime (`cloudflare` or `node`).
- Presence booleans for `ALPHAOS_API_URL`, `ALPHAOS_API_TOKEN`, `ALPHAOS_DEMO_MODE`.
- `configuration`: `missing`, `invalid`, or `ready`.
- `demo_enabled`: false in Workers.

These diagnostics are no-store. No URL, token, credential length, headers,
exception messages, or upstream response contents are exposed. Research logs
include the same safe configuration summary and existing correlation IDs.
`ready` means syntactically configured, not authenticated, connected, fresh,
or trading-verified. Process health can still be `ok` when research is unavailable.

| Research code | Meaning |
| --- | --- |
| `backend_not_configured` (503) | Required runtime binding absent/blank; no upstream request. |
| `invalid_backend_configuration` (503) | URL is not an allowed HTTPS backend URL. |
| `backend_authentication_required` / `backend_authentication_rejected` (502) | Bindings exist; Render returned 401 / 403. |
| `backend_unreachable` (502) | Network/transport failure after attempting an upstream request. |
| `backend_timeout` (502) | Upstream deadline exceeded, including response-body processing. |
| `archive_stale`, `archive_missing`, `archive_not_configured`, etc. (502) | Render/archive evidence error; no substitute evidence. |
| `response_schema_mismatch` (502) | Backend result did not satisfy the verified research contract. |

## Exact remaining Cloudflare steps

1. Use **alphaos-web** as the deployment target; that is the committed Worker
   name and the Worker hosting the existing rendering Preview. GitHub build
   settings currently on **alphaos** must not be mistaken for this Worker.
   Under **alphaos-web > Settings > Builds**, connect the repository/branch
   integration to this Worker, with production automatic deployment disabled
   until separately approved. Leave the separate `alphaos` Worker untouched;
   do not deploy/delete it or move production traffic as part of this fix.
2. Open **Workers & Pages > alphaos-web > Previews >
   codex/cloudflare-workers > Settings > Variables and secrets**. Select the
   **individual existing Preview**, not Production, not Build variables, and
   not only Previews Base. Add runtime secrets named `ALPHAOS_API_URL` and
   `ALPHAOS_API_TOKEN` from the credential manager. The URL must be the intended
   existing HTTPS Render API origin; the token must be accepted by that backend.
   Do not paste values into chat, commits, PR descriptions or build commands.
3. Keep `ALPHAOS_DEMO_MODE=false` (already declared as a text runtime binding).
   Set the same two secret names in **Previews Base** separately if future PR
   Previews should inherit them. Base updates do not repair active Previews.
4. In **alphaos-web** GitHub/Cloudflare Preview build settings set root **web**,
   Node **22.23.0**,
   production branch **main**. Use build command
   `npm ci && npm run cf-typegen && npm run typecheck && npm test && npm run build:vinext && npm run check:workers`.
   Set Preview command to **`npm run preview:workers`** (`cf previews deploy`).
   Never invoke `deploy:workers`, `deploy:vinext`, `upload:workers` or
   `cf deploy` against Preview output. Keep production deployment disabled
   until separately approved; no production or DNS cutover is needed here.
5. Rebuild **this existing Preview** from the updated PR head. `check:workers`
   now performs read-only artifact validation for either output context; the
   old `cf deploy --prebuilt --dry-run` incorrectly rejected Preview output.
   CI tests both `CLOUDFLARE_PREVIEW_BUILD=false` and `true`.
6. Open the Preview's `/api/health`. Require
   `research_configuration.runtime="cloudflare"`, both required presence flags
   `true`, `configuration="ready"`, and `demo_enabled=false`.
   The current URL is
   `https://codex-cloudflare-workers-alphaos-web.rfroux95.workers.dev`.
   If either flag is false, check the individual Preview runtime settings and
   deployment binding names again. Do not change authentication or timeouts to
   bypass the missing-binding error.
7. Retry QQQ/SPY and `/structures`. If a different error appears, use the code
   table and request correlation ID to distinguish authentication, network,
   timeout or archive state. Stale/unavailable research must remain unavailable.
   Leave Render API/MCP settings and provider/archive credentials untouched.

## Regression checks

`npm test` covers request-time Node configuration, safe health diagnostics,
existing proxy validation/auth/network errors and the original 12-second timeout.
`npm run test:workers` runs the **actual compiled Worker** in local workerd,
with `process.env` population disabled and runtime-only test bindings. It checks
QQQ/SPY and structure/comparison forwarding, missing configuration, disabled
Worker demos, 401/403, backend errors and schema rejection. Its outbound service
is a deterministic fixture; it never contacts Render or market-data services.

For both production and Preview build contexts run `build:vinext`,
`check:workers`, `test:workers`, the public-asset credential scanner, and the full
Playwright suite. Also run the original Next.js build and Playwright suite.
Local fixtures prove wiring and contracts; live authentication/freshness is
verified only after the missing secrets are attached to the Preview.
