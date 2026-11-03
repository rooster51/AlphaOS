# Native version upload compatibility — 2026-10-29

**No production version was uploaded or deployed during this investigation.**
Only synthetic credentials were used for CLI validation. The website, auth
implementation, Worker configuration, Render/MCP, trading code and infrastructure
are unchanged. No owner credential file was read for these tests.

## Exact rejection and cause

Wrangler **4.155.0** deliberately rejects this project's native build output:

> Cloudflare Build Output was found at `.cloudflare/output/v0`. Deploying it
> with Wrangler reads a different configuration, so it may target the wrong Worker.
> Please run `cf workers versions create` instead.

This is its `assertNoCloudflareBuildOutput` safety guard, called before the
versions-upload handler builds or sends an upload. It was reproduced locally
with synthetic authentication and external network access blocked. It is not a
bad password, missing API token, malformed Worker, or instruction to run deploy.

Installed/locked application tooling:

| Component | Version / role |
| --- | --- |
| `cf` | `1.0.0-beta.23`, the native build-output consumer |
| vinext | `1.3.1` |
| `@vinext/cloudflare` | `1.2.1` |
| `@cloudflare/vite-plugin` | `2.0.0-beta.v.5`, build-output producer |
| Wrangler | `4.155.0`, transient diagnostic only; not added to the application |

The source of truth is `web/cloudflare.config.ts`; the output is
`.cloudflare/output/v0/config.json` plus `workers/default/worker.config.json`,
server modules and public assets. This is not a Wrangler configuration.
Do not delete the output, copy/repackage its modules into a legacy project,
invent a Wrangler config, downgrade Wrangler, suppress the guard, or deploy a
placeholder to make versions upload work. Those would evade the compatibility
check rather than resolve the producer/consumer mismatch.

Cloudflare documents `cf workers versions create` as the native **upload without
deployment** command. A separate `cf workers deployments create` changes active
traffic. Neither that deployment command nor triggers deploy is part of upload.

## Supported procedure for a later authorized upload

From `web`, use Node **22.23.0** and the existing lockfile. Keep real credentials
out of build variables and local `.env`/`.dev.vars` files used by the build.

```sh
npm ci
npm run typecheck
npm test
npm run build:vinext
npm run check:workers
node scripts/check-worker-assets.mjs
npm run test:workers
npm run preflight:upload:workers
```

Unset `CLOUDFLARE_PREVIEW_BUILD` and preview environment selection before building.
Confirm `buildContext.isPreview=false`, `buildContext.mode=production`, target
`alphaos-web`, custom guarded entrypoint, the four secret declarations, demo
`false`, and the native limiter. Do not use Preview output. Mode must match the
recorded artifact: the upload script now explicitly pins both mode and target.

`preflight:upload:workers` uses only temporary **synthetic** JSON credentials.
It is not an upload to Cloudflare: the dry run sends zero API requests, and
the non-dry path is exercised only against an in-process loopback mock API.
The spawned CLI has external sockets/fetch blocked and synthetic authentication
forced; the mock rejects any other authentication. No owner secrets or local
OAuth session are used. The mock has no deployments or existing secrets and
models the already-created `alphaos-web` service (created with the Preview).
It checks one version POST, no deployment/routing/settings writes, four
`secret_text` bindings, unchanged entrypoint bytes, demo false, native limiter,
and absence of secret values in CLI output. Wrong mode/target fail before API
calls. Preview artifacts must be rejected, not uploaded with a production command.

Only after separate production-upload authorization:

1. Confirm `cf` authentication for the correct account. Wrangler and cf have
   separate login stores; a successful Wrangler whoami is not proof of cf login.
   Use `npm exec -- cf auth whoami`; owner sign-in, if needed, is
   `npm exec -- cf auth login`. Do not extract cached OAuth tokens, request a
   token in chat, or silently switch accounts.
2. Confirm the Worker still has no active production deployment. Require passing
   CI on the exact approved SHA. Record the current version/deployment lists.
3. Use the private owner file and local API credentials to prepare a private
   **JSON** file outside the repository with exactly `ALPHAOS_API_URL`,
   `ALPHAOS_API_TOKEN`, `ALPHAOS_PASSWORD_HASH`, `ALPHAOS_SESSION_KEY`.
   Set a restrictive Windows ACL; do not rely on POSIX mode alone. Never print,
   log, commit, or pass values in arguments/environment. Keep demo false in the
   committed text binding. JSON avoids dotenv interpolation of bcrypt dollar signs.
4. Upload the already-tested production artifact, exactly once:

   ```sh
   npm run upload:workers -- --secrets-file "<PRIVATE_JSON_FILE>" --tag "<APPROVED_SHA>"
   ```

   This expands to:

   ```sh
   cf workers versions create --prebuilt --mode production --worker alphaos-web --secrets-file "<PRIVATE_JSON_FILE>" --tag "<APPROVED_SHA>"
   ```

5. Record the returned version ID. Inspect only safe metadata: target, tag,
   binding names/types, demo false, limiter, and version/deployment lists.
   Confirm there is **still no production deployment**. Do not dump complete
   metadata (it can include asset tokens) or private files. Securely discard any
   temporary combined file after the approved operation.

## Boundaries and remaining risks

- This investigation validates the pinned client's request flow, redaction and
  local auth/runtime tests. It does **not** prove the real Cloudflare service will
  accept the first version, the production credential pair is correct, or that
  remote asset uploads and account permissions will succeed. No remote mutation
  was performed to test those facts. Stop on any actual upload failure; never
  fall back to `deploy`, `secret put`, trigger changes, or a placeholder release.
- The first version is of an already-created Worker resource. Do not extrapolate
  the mock result to creating a brand-new Worker/project or bootstrap production
  through legacy script-upload APIs.
- A version URL can serve requests without an active production deployment.
  The password guard and all runtime bindings must be included in that first
  version; verify anonymous API 401/page redirects and successful owner login
  before claiming the uploaded candidate works. No public routing is authorized.
- Check cost-12 bcrypt login against the existing plan's CPU allowance during a
  future authorized candidate check; do not weaken hashing or upgrade the plan
  automatically. Preserve fail-closed research and non-executable archive labels.
- The native CLI/build plugin remain pinned beta tooling. Re-run these tests
  after upgrades. Do not replace the working Preview or modify `alphaos`.

**Recommendation:** the compatibility blocker has a supported native CLI path
and a passing offline preflight. This permits a *future explicitly authorized
upload attempt*, not a claim that a production version exists or is deploy-ready.
The owner must accept the native cf path; retaining Wrangler as a hard requirement
remains blocked without a separately reviewed toolchain migration. No migration
is necessary or performed here. PR #67 remains open and unmerged.

Actual local checks: typecheck and production/Preview builds passed; 201 website
unit tests passed; production has 14 passing Worker/preflight tests; Preview has
13 passing tests plus one inapplicable production-upload simulation (its
production-command rejection is tested). Both contexts have 47 passing browser
tests and 23 public assets passed credential-reference scans. The 164 Python
provenance/entry/research/MCP integration tests passed; dependency audit found
zero vulnerabilities. These tests used no production secrets or remote uploads.

References: [native version creation](https://developers.cloudflare.com/cf/projects/#upload-a-version),
[build context and modes](https://developers.cloudflare.com/cf/projects/#deploy-a-prebuilt-build),
[Wrangler/cf mapping](https://developers.cloudflare.com/cf/wrangler/reference/).
