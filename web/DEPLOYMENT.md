# Web hosting

Current service, backend and dependency ownership is documented in
[the audited deployment map](../docs/DEPLOYMENT.md) and
[architecture inventory](../docs/ARCHITECTURE.md). The live website service is
named `alphaos-web-staging`; its name alone does not identify an unused preview.
This document describes setup, not authorization to deploy or change settings.

Run this app as a Node.js 22 Next.js web service. Do not configure a static
export: server-rendered pages and the `/api` routes need a server runtime.
Render is the simplest fit with the existing backend; configure the web service
to run `npm run build` and `npm start`, preferably in the backend's region.

Set these server-side environment variables in the hosting provider:

| Variable | Requirement |
| --- | --- |
| `ALPHAOS_API_URL` | HTTPS base URL of the AlphaOS API. |
| `ALPHAOS_API_TOKEN` | Required secret bearer token; never expose it as `NEXT_PUBLIC_*`. |
| `ALPHAOS_DEMO_MODE` | Optional; set to `true` only when intentionally showing labeled synthetic fixtures. Leave unset or `false` for normal read-only use. |

`NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` are present in
`.env.example` for a future integration but are not used by the current web
foundation. Do not configure them as a substitute for authenticated account
integration. `/api/health` confirms only that the web process responds; it does
not verify backend credentials, account access, or current market evidence.

## Netlify Free compatibility

The root `netlify.toml` targets only `web/` as the build base. Netlify therefore
runs `npm ci` and `npm run build:netlify` from the Next.js project instead of
detecting the repository-root `.python-version` and `requirements*.txt`. The
Next.js OpenNext adapter is detected and managed by Netlify; do not install or
pin `@netlify/plugin-nextjs`. The published Next output is `.next`, and the
build uses Node.js 22.23.0.

The Netlify build uses `tsconfig.netlify.json` to omit the Cloudflare Worker,
Cloudflare runtime shim, and Vite/Worker config from Next's type-check. The
application itself continues to use the Node runtime binding (`process.env`);
the Cloudflare config and Worker entrypoint are retained for the existing
Cloudflare branch. No Python, trading engine, archive, or Supabase code is
included in the site build.

The Netlify Edge Function `10-auth-gate` applies the existing
`protectWebsite` checks to every request before assets, pages, and API routes
are served. It reads secrets from Netlify's Functions environment and keeps
the HTTPS redirect, signed `__Host-` session cookie, exact-origin CSRF checks,
remote Render password verification, no-store headers, and protected research
API. `00-login-rate-limit` runs first for `/auth/login` and applies a 5-request
per-60-second limit per domain and client IP.

**Rate-limit limitation:** Netlify's Free plan supports code-defined rate
limits per domain and IP, not a shared per-domain limit across all clients.
Enforcement may take up to 10 seconds to begin blocking. This is weaker than
the existing Cloudflare shared bucket and can be bypassed by distributing
attempts across source IPs. The Render verifier's bounded bcrypt concurrency
remains in place, but this does not restore the shared login-attempt limit.
Do not treat the migration as equivalent security until this tradeoff is
accepted or a no-cost shared limiter is separately approved and provided.

### Netlify setup (manual; no deploy is performed by this change)

1. After reviewing the stacked UI and hosting changes, create a Netlify site
   from `rooster51/AlphaOS` on the branch that contains this change. Use the
   Free plan. The checked-in `netlify.toml` selects the `web` base directory,
   build command, Node version, and publish output; do not override those
   settings with repository-root build commands.
2. In the site's environment-variable settings, add the existing server-side
   values `ALPHAOS_API_URL`, `ALPHAOS_API_TOKEN`, `ALPHAOS_PASSWORD_HASH`,
   `ALPHAOS_SESSION_KEY`, and `ALPHAOS_DEMO_MODE=false`. Give secret values
   Functions scope where Netlify offers scopes. Reuse the approved values from
   the current website/API configuration; do not commit them, put them in
   `netlify.toml`, or expose them as `NEXT_PUBLIC_*`. The Edge Functions set
   the explicit external-limiter option in the auth gate; no limiter-mode
   environment variable should be added.
3. Keep the site on HTTPS and confirm the Netlify deploy uses these runtime
   variables. The login gate fails closed if auth secrets are missing, while
   research API configuration failures remain unavailable rather than falling
   back to synthetic or stale data.
4. Before directing users to the site, separately approve the per-IP versus
   shared rate-limit difference. Then verify anonymous pages and APIs redirect
   or return 401, a valid login issues the hardened cookie, logout clears it,
   authenticated research still calls the existing Render API, and stale or
   missing archive evidence stays unavailable. Do not test real password
   guesses against a production endpoint.

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
