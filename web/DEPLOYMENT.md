# Web hosting

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
