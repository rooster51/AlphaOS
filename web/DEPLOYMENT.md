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
