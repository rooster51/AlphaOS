# Web hosting

Current service, backend and dependency ownership is documented in
[the audited deployment map](../docs/DEPLOYMENT.md) and
[architecture inventory](../docs/ARCHITECTURE.md). The current frontend target is
Netlify; the API runs on Render and archive storage on Supabase. This document
describes setup, not authorization to deploy or change settings.

Build this app as a Node.js 22 Next.js web service on Netlify. Do not configure a
static export: server-rendered pages and the `/api` routes need a server runtime.

The AlphaOS API runs on Render as a Free instance, which spins down after 15
minutes without inbound traffic and takes about a minute to boot again. A public
`GET https://alphaos.onrender.com/health` keeps it warm without credentials; the
job specification, monthly Free instance-hour budget and its limits are in
[`docs/render_keepwarm.md`](../docs/render_keepwarm.md).

Set these server-side environment variables in the hosting provider:

| Variable | Requirement |
| --- | --- |
| `ALPHAOS_API_URL` | HTTPS base URL of the AlphaOS API. |
| `ALPHAOS_API_TOKEN` | Required secret bearer token; never expose it as `NEXT_PUBLIC_*`. |
| `ALPHAOS_DEMO_MODE` | Optional; set to `true` only when intentionally showing labeled synthetic fixtures. Leave unset or `false` for normal read-only use. |
| `ALPHAOS_CANDLE_CHART_ENABLED` | Native Public candle display is **disabled by default**. Leave unset or `false` to serve the legacy external TradingView fallback at `/market/chart`. Set to `true` only after Public grants explicit written authorization for authenticated website display and the entitlement reference is recorded. |

`NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` are present in
`.env.example` for a future integration but are not used by the current web
foundation. Do not configure them as a substitute for authenticated account
integration. `/api/health` confirms only that the web process responds; it does
not verify backend credentials, account access, or current market evidence.

## Netlify Free compatibility

The root `netlify.toml` targets only `web/` as the build base. Netlify therefore
runs `npm ci` and `npm run build:netlify` from the Next.js project instead of
detecting the repository-root `.python-version` and `requirements*.txt`. The
Next.js OpenNext adapter normally installs automatically. The live deploy did
not include its server runtime (Netlify reported no functions deployed), so
this repository explicitly installs the adapter as a build plugin to ensure
SSR, route handlers, and App Router routes are packaged. The base and package
directories are `web/`; the build command is `npm run build:netlify`, the Next
build output is `.next`, and the build uses Node.js 22.23.0. Keep the adapter
package version in `web/package.json` and the plugin declaration in the root
`netlify.toml` in sync.

The Netlify build uses `tsconfig.netlify.json`, which extends the application's
TypeScript config. The application uses the Node runtime binding (`process.env`).
No Python, trading engine, archive, or Supabase code is included in the site
build.

The Netlify Edge Function `10-auth-gate` applies the existing
`protectWebsite` checks to every request before assets, pages, and API routes
are served. It reads secrets from Netlify's Functions environment and keeps
the HTTPS redirect, signed `__Host-` session cookie, exact-origin CSRF checks,
remote Render password verification, no-store headers, and protected research
API. `00-login-rate-limit` runs first for `/auth/login` and applies a 5-request
per-60-second limit per domain and client IP.

After the per-IP rule, the gate calls the authenticated Render
`/v1/website-auth/rate-limit` endpoint. Render invokes the
`consume_website_login_attempt` Supabase RPC with its existing service-role
secret. The RPC serializes login attempts under a database row lock and
enforces a shared rolling 5-attempt/60-second window across client IPs.
Expired attempts are removed during each call. The SQL migration enables RLS,
denies direct table access, and grants RPC execution only to `service_role`.
The shared limiter fails closed on missing configuration, transport failures,
unexpected status, or invalid responses. No client IP or authentication
credential is stored in the attempt table.

The [migration](../supabase/migrations/20261103000000_website_login_shared_rate_limit.sql)
is reviewed source only and is **not applied to production** by this change.
Do not enable the Netlify site until the migration is applied to the intended
Supabase project and its role grants are verified. The backend uses the
existing Render `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` environment
variables; do not copy either secret into Netlify or source control. Render's
existing bounded bcrypt concurrency remains independent protection.

### Netlify setup (manual; no deploy is performed by this change)

1. Review and approve the SQL migration, then apply it to the intended Supabase
   project under its normal migration procedure. Verify the `service_role`
   can execute the RPC and cannot directly read the limiter tables. Do not
   grant the function to `anon` or `authenticated`. This change does not run
   migrations or modify production data.
2. Verify the existing Render API has its current `SUPABASE_URL` and
   `SUPABASE_SERVICE_ROLE_KEY` environment values and deploy the API change
   through its separately approved release process. The rate-limit endpoint
   fails closed until those values and the RPC are available.
3. Configure the existing Netlify site from `rooster51/AlphaOS` on the
   release-candidate branch. Set the base and package directories to `web/`;
   use `npm run build:netlify` and publish `.next`. The checked-in
   `netlify.toml` selects these settings and installs the Next.js runtime;
   do not override them with repository-root build commands or disable the
   adapter.
4. In the site's environment-variable settings, add the existing server-side
   values `ALPHAOS_API_URL`, `ALPHAOS_API_TOKEN`, `ALPHAOS_PASSWORD_HASH`,
   `ALPHAOS_SESSION_KEY`, and `ALPHAOS_DEMO_MODE=false`. Give secret values
   Functions scope where Netlify offers scopes. Reuse the approved values from
   the current website/API configuration; do not commit them, put them in
   `netlify.toml`, or expose them as `NEXT_PUBLIC_*`. No limiter-mode
   environment variable should be added.
5. Once explicitly authorized, create a Netlify deploy preview and verify its
   runtime environment, anonymous denial, login/logout, CSRF rejection, Render
   connectivity, and shared limit across separate client IPs. Confirm missing
   or stale research evidence remains unavailable before any production
   decision. Do not test real password guesses against production.

Local checks from `web/`:

```sh
npm ci
npm run build:netlify
npm run typecheck
npm test
npm run test:e2e
```

The Edge Function rate policy is configured in source and available on all
Netlify plans. Exceeding any Free-tier included usage limits can affect site
availability; monitor usage and do not enable paid upgrades or paid add-ons.

## Release 1 candidate research parity

`/market` and `/strategies` share the same research controls and candidate view.
The initial $150 is editable; submitted positive decimal amounts are forwarded as
`available_capital`. Expirations come only from verified research diagnostics.
An omitted expiration uses the backend selection; an explicit unavailable date
is never replaced. Default width remains the backend/MCP default of five points.

The authenticated `/api/research/market` bridge retains the full v2 envelope.
The legacy `/api/strategies` URL now delegates to that bridge (explicit SPY/QQQ;
no `ALL` aggregate or legacy fixture candidate schema). Capital exclusions remain
visible with their backend research objects. Capital eligibility is distinct from
historical evidence eligibility, execution readiness, and broker buying power.
All backend warnings remain available; missing metrics remain unavailable.

### Historical PR #42 deployment note

The paragraph below records the website-only scope of PR #42. Later PRs #43/#44
changed the shared backend contract; do not use this dated note to decide that
a future release needs only a website deployment. Review the current dependency
map and both service commits before a separately authorized deployment.

After review and approval, publish this feature commit and deploy the website
only using `cd web && npm ci && npm run build` and `cd web && npm start`.
Verify its existing server-side `ALPHAOS_API_URL` targets
`https://alphaos.onrender.com`, its token matches that API, and demo mode is off.
Any required environment change needs separate approval. No backend deployment,
collector change, migration, freshness adjustment or new dependency is needed.
Retain the prior website deployment for rollback.

Validate SPY $150 then $500, QQQ, archived expirations, and equivalent MCP inputs
during a session with fresh archive data. The bridge retains its 12-second timeout.
The tests/fixtures/market-parity.json records synthetic backend test outputs,
validated against actual REST and OAuth MCP handlers; it is never imported by
application code and does not certify live market or deployment acceptance.
