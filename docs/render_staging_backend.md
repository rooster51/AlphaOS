# AlphaOS staging research API on Render

`render.staging.yaml` defines a separate, read-only API service on the `web/research-api-integration` branch. It uses the existing Python API deployment entry point (`python -m alphaos_api`), the API-only dependency manifest, and `/health` as its process health check. It does not define, change, or deploy the production API or MCP service.

The blueprint allows a verified archive observation up to 24 hours old. Research remains dated to the archived observation and is not a live quote or actionable trading signal. Expired contracts and archive data outside this window continue to fail closed. Checksum, symbol/session identity, timestamps, and archive quality verification remain enforced by the existing archive reader.

## Render-managed secrets

Render prompts for these values when the staging blueprint is first created because each is declared with `sync: false`:

- `ALPHAOS_API_TOKEN` — staging API bearer token. Set the same staging-only value on the staging website as a server-side secret.
- `SUPABASE_URL` — private Supabase project URL for the existing archive.
- `SUPABASE_SERVICE_ROLE_KEY` — backend-only key used by the API's read-only archive path; never add it to the website service or client-visible variables.

Do not place secret values in this repository, blueprint, browser variables, or chat. The website staging service must have server-side `ALPHAOS_API_URL` set to the new API service URL and `ALPHAOS_API_TOKEN` set to the matching staging token. Do not use a `NEXT_PUBLIC_` name for either setting.

The custom blueprint path is `render.staging.yaml`; select that path when initializing the staging Blueprint. Service creation and secret configuration require an authorized Render operator. The free plan can sleep while idle, so allow for a cold start when checking the staging service.
