# Phase 8 connection audit — 2026-09-24

Audited deployed commit `2ecda4ab179b2c1a6c2ad3b93d809b4f7c39fc98` before editing.
The earlier error was “Couldn't create MCP app. Try again.” Its exact failing
request is not recoverable from available historical logs. Confirmed defects
below must not be presented as conclusive attribution of that generic error.

## Production observations before the fix

| Check | Observation |
| --- | --- |
| GET `/health` | 200, authentication configured, read-only research schema |
| GET/POST `/mcp` without token | 401, Bearer challenge pointing to `/.well-known/oauth-protected-resource/mcp` |
| GET/POST `/mcp/` | 307 to the configured `/mcp` URL |
| Resource-specific metadata | 200; resource `https://alphaos.onrender.com/mcp`; authorization server `https://alphaos.onrender.com`; scope `research:read` |
| Root protected-resource metadata | 404; resource-specific URL remains discoverable through the challenge |
| Authorization-server metadata | 200; issuer **`https://alphaos.onrender.com/`**; correct `/authorize`, `/token`, `/register` endpoints; S256 advertised |
| DCR, both documented ChatGPT callbacks | 201; public and confidential registrations accepted |
| Authorization / owner consent | 302 / 303; callback issuer **`https://alphaos.onrender.com`** |
| Header-only HTTP Basic token exchange | **401 invalid_client**, despite advertising client_secret_basic |
| Same valid grant with redundant form client_id | 200; test grant subsequently revoked |
| Invalid authorize / token request | 400, safe OAuth errors |

The SDK's AnyHttpUrl conversion added a slash only to authorization-server
metadata. Existing tests compared the callback to a constant rather than the
published issuer, missing this exact-string mismatch. The SDK authenticator
also required body client_id before reading Basic credentials from the header.

During this audit, ChatGPT progressed through Create MCP App and Continue to
AlphaOS Research, reaching the AlphaOS consent page. Thus creation/discovery and
authorization could progress at that time; the earlier error was not reproduced.
This is not proof of a successful authenticated tool invocation. The plugin
directory also displayed unrelated “Failed to fetch” messages.

Render logs showed a process start at 17:00:42 in the displayed timezone, but
request logs were unavailable. Application access logging was intentionally
disabled, leaving no historical path/status trace of the failed request.
Cold starts can add latency, but a timeout or proxy/CORS failure was not proven.

## State and scoped corrections

All original stores were process-local: DCR client IDs/metadata, pending consent
and PKCE, authorization codes, access/refresh tokens, refresh replay records,
and rate limits. Stateless MCP has no persistent session. Lost grants safely
force sign-in; losing ChatGPT's reused DCR identity forces app recreation.

The fix makes the published issuer match the existing exact origin and adapts
header-only Basic requests while retaining SDK credential/mismatch validation.
ChatGPT CIMD resolution addresses the separate client-identity persistence defect
without adding storage or replacing REST/MCP. Its published identity can be
reconstructed after restart. Grants remain ephemeral and fail closed on restart;
uninterrupted refresh would require durable state. Legacy DCR still requires
durable storage for restart recovery, so new connections should use CIMD.

Only the OAuth adapter, its tests and MCP documentation change. Ten tools,
transport, REST authentication and all quantitative calculations are retained.
New diagnostics record fixed OAuth stage/status pairs without request contents.

## Current requirements

OpenAI requires exact issuer agreement. It accepts CIMD public-client exchange
with mandatory PKCE; ChatGPT's published metadata offers `none` and
`private_key_jwt`, and AlphaOS supports `none`. The owner still consents before
any grant is issued. See [OpenAI OAuth requirements](https://developers.openai.com/plugins/build/auth),
[Developer Mode](https://developers.openai.com/api/docs/guides/developer-mode),
[ChatGPT metadata](https://chatgpt.com/oauth/client.json), and the
[MCP authorization specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization).

Final acceptance requires actual ChatGPT app creation and an authenticated tool
invocation. Independent HTTP smoke success is not a substitute.
