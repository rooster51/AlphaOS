# AlphaOS website on Cloudflare Workers

Prepared from main `77ef046` (PR #66). This change does not deploy anything.
The existing Render website, Python/FastAPI API, MCP OAuth origin, collectors,
archive jobs, and data stores remain on Render/their existing infrastructure.

For the confirmed missing bindings in PR #67's active Preview and the exact
repair steps, see [Preview diagnostics](CLOUDFLARE_PREVIEW_DIAGNOSTICS.md).

## Runtime and compatibility

The website retains Next.js **16.4.1** and its existing `dev`, `build`, and
`start` commands for Render. The Workers path uses **vinext 1.3.1**, Cloudflare's
currently recommended Next.js 16 integration, with its native Vite plugin.
It implements the Next.js API surface rather than wrapping `next build` output.
See [Cloudflare's Next.js guide](https://developers.cloudflare.com/workers/framework-guides/web-apps/nextjs/)
and [vinext](https://github.com/cloudflare/vinext).

React/React DOM and RSC use 19.3.1, as required by vinext. Both build paths are
tested. The compatibility scan reports 96%: all used imports work; the partial
item is automatic App Router development StrictMode wrapping. The market request timeout remains
`AbortSignal.timeout(12000)`, including body reading and validation, as covered
by the existing route tests.

The generated `cloudflare.config.ts` uses the adapter's native entrypoint,
Node compatibility, static asset routing, logs and sampled traces. No KV, R2,
database, image optimization, or research response cache is introduced.
The cf CLI and Vite plugin currently use beta configuration APIs; their
versions are pinned and locked. Updates need both runtime test suites.

Use Node **22.23.0** (`web/.node-version`) or a supported version listed in
`web/package.json`. Transitive dependency overrides pin patched undici, fflate,
and postcss-selector-parser releases; the complete dependency audit now passes
without the former dev-tool advisory exception.

## Required runtime configuration

Supply these separately for production and Worker Previews in Cloudflare's
runtime Variables and Secrets settings. No credential values belong in source,
build variables, GitHub Actions, browser storage, or `NEXT_PUBLIC_*`/`VITE_*`.

| Name | Setting | Purpose |
| --- | --- | --- |
| `ALPHAOS_API_URL` | Secret binding (URL is not inherently sensitive) | Existing HTTPS Render API origin, with no userinfo, query or fragment. Use the intended Render backend for each environment. |
| `ALPHAOS_API_TOKEN` | Secret binding | Existing API bearer credential, available only to server handlers. Prefer a separate preview credential/backend. |
| `ALPHAOS_DEMO_MODE` | Text binding, committed as `false` | Keep normal research fail-closed; do not enable demos in production. |

Only the website-to-API credential belongs here. Public provider credentials,
Supabase service role keys, MCP OAuth secrets and collector credentials remain
on Render. Browser calls stay same-origin `/api/research/*`; server handlers
attach the token to the Render request. Missing runtime configuration returns
503 `backend_not_configured`. Health does not assert backend freshness.

For local Workers development only, use ignored `web/.dev.vars` with the two
runtime names above. Local files are not uploaded. Keep them absent during
automated tests, which deliberately run without credentials or live research.

## GitHub integration: manual setup after approval

Do **not** connect/enable automatic builds until deployment is authorized:
connecting a repository or triggering a build can immediately deploy it.
No Cloudflare dashboard resources were changed by this branch.

1. Create/select the intended Workers project named **alphaos-web**. Connect
   GitHub repository **rooster51/AlphaOS**, granting access to that repository.
   Use **Workers**, not a Pages static export.
2. Set root directory **web**, production branch **main**, and build Node
   version **22.23.0** (set `NODE_VERSION` if required by the build image).
3. Build command: `npm ci && npm run cf-typegen && npm run typecheck && npm test && npm run build:vinext && npm run check:workers`.
   Production deploy command: `npm run deploy:workers` (`cf deploy --prebuilt`),
   only for approved main production builds. `check:workers` validates artifacts
   locally and never invokes a deployment command in either output context.
4. Enable **Worker Preview builds** for non-production branches/PRs and GitHub
   PR comments. Preview command: `npm run preview:workers` (`cf previews deploy`).
   This command builds in Preview context itself; do not pass `--prebuilt` to
   reuse a production-context artifact. Configure runtime secrets separately
   for Previews; they do not inherit production settings. Do not leave the
   default Wrangler preview command with this cf configuration.
5. Restrict preview branches to trusted contributors as appropriate. Preview
   URLs are public unless Cloudflare Access is configured. A server-side bearer
   token is hidden from browsers, but published research routes remain callable.
   Do not give untrusted PR code production credentials.
6. Supply runtime secrets from the credential manager directly in Cloudflare,
   without printing or copying values into an issue/PR. Use Cloudflare's build
   integration token for upload authentication. Our GitHub checks need no
   `CLOUDFLARE_API_TOKEN` or account secret.
7. Require GitHub checks **tests / web**, **tests / pytest**, and **Workers checks /
   workers** before merging. Workers Builds is a separate deployment system;
   protect main with these checks before enabling automatic production builds.
8. Keep existing Render services and their deployment settings. Leave DNS and
   custom domains untouched until a later approved cutover. No MCP redirect or
   OAuth issuer changes are needed.

Dashboard labels may evolve; see [Build branches](https://developers.cloudflare.com/workers/ci-cd/builds/build-branches/)
and [cf project configuration](https://developers.cloudflare.com/cf/projects/cloudflare-config/).
Confirm the chosen account supports cf Preview commands in Workers Builds
before enabling the integration.

## Verification and later release checklist

From `web`, run:

```sh
npm ci
npm audit --audit-level=moderate
npm run cf-typegen
npm run typecheck
npm test
npm run build
npm run test:e2e
npm run build:vinext
npm run check:workers
# PowerShell: $env:ALPHAOS_TEST_WORKERS='true'
# POSIX: ALPHAOS_TEST_WORKERS=true npm run test:e2e
npm run test:e2e
```

The Workers workflow runs both production and Preview builds, local artifact validation, route tests and the full
Playwright suite in local workerd; it never uploads or deploys. The existing
workflow retains Next.js and Python regression checks. `typecheck` regenerates
Next.js types first because vinext also writes route types under `.next/types`.
The PostCSS config uses `.cjs` so both runtimes work with the ESM package.

Browser tests verify `/market`, `/structures`, scenario comparison, research
error states, desktop/mobile navigation and direct API request validation and
missing-credential responses. Existing unit tests verify authenticated request
forwarding, backend fixture envelopes, timeout handling and input validation.
These are local checks; they do not establish live Render/Cloudflare connectivity.

After explicit deployment approval, first inspect a PR Preview: check health,
static assets, navigation, `/market` for SPY/QQQ, `/structures`, and all three
research POST routes with a configured Render backend. Confirm archive
provenance/freshness labels, safe errors, no credential in browser requests or
assets, and the unchanged 12-second market timeout. An actual cold Render
response can still time out and must fail closed. Only then approve a main
deployment and any DNS cutover separately. Retain Render as rollback capacity.
