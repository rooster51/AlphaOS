# AlphaOS remote MCP — Phase 8

Production target: **https://alphaos.onrender.com/mcp**.

This is a thin research interface on the existing FastAPI process. Each tool
dispatches through the existing REST routes using an in-process ASGI request,
so validation, Public access, snapshots, research calculations and response
sanitization remain shared. Streamlit remains its own application.

## ChatGPT setup

1. Enable Developer Mode in ChatGPT **Settings → Security and login → Developer
   Mode**, if available for your account/workspace.
2. Open **Plugins → + → New plugin / Create MCP App**. Enter:

   | Field | Value |
   | --- | --- |
   | Name | `AlphaOS Research` |
   | Description | `Read-only SPY/QQQ market and options research; no execution or trade ranking.` |
   | Server URL | `https://alphaos.onrender.com/mcp` |
   | Authentication | **OAuth** |
   | OAuth Client ID | Leave blank for automatic discovery |
   | OAuth Client Secret | Leave blank for automatic discovery |
   | Registration method, if shown | **CIMD** |

3. Connect. ChatGPT discovers the authorization server and uses its published
   Client ID Metadata Document (CIMD) identity.
   On the **AlphaOS** consent page, enter your existing `ALPHAOS_API_TOKEN` in
   the password field and select **Allow research access**. Enter it only on
   `https://alphaos.onrender.com/oauth/consent`, never in a conversation. Do not
   enter the Public API secret. ChatGPT receives a separate scoped OAuth token.
4. Enable/select AlphaOS in a normal conversation. Ask: “Use AlphaOS live_quote
   for QQQ. Show the returned spot, quote timestamp and caveats.” Confirm an
   actual tool invocation and result, rather than an answer from general knowledge.
5. Then try market_snapshot and reuse its snapshot_id for price_structure and
   forward_distribution. For a scan, research a returned candidate_id promptly.

OAuth is required here; do not select No Authentication or Mixed Authentication,
and do not paste the REST token into the OAuth Client Secret field. The OpenAPI
URL is a REST schema, not the MCP Server URL. If an account/workspace does not
offer custom apps, that account's access must be resolved separately.

The preferred flow uses CIMD with public-client authentication (`none`) and
mandatory PKCE. DCR remains a legacy alternative; use CIMD for a client identity
that can be recovered after restarts. The server advertises issuer identification
and accepts the official `https://chatgpt.com/connector_platform_oauth_redirect`
callback and `https://chatgpt.com/connector/oauth/{callback_id}` form. Redirects
are registered and compared exactly; arbitrary callback domains are rejected.

These settings follow the [official Developer Mode guide](https://developers.openai.com/api/docs/guides/developer-mode)
and [OpenAI OAuth guidance](https://developers.openai.com/plugins/build/auth).
An HTTP smoke test alone does **not** establish a working ChatGPT integration:
the connection is verified only after ChatGPT initializes MCP and invokes a tool.

## Transport and deployment

The official Python MCP SDK is pinned to `mcp==2.2.0`. It serves stateless
**Streamable HTTP**, with JSON responses, at `/mcp`. Tests cover the current
2026-07-28 request metadata protocol and the 2025-11-25 initialize handshake.
The SDK handles protocol negotiation; no hand-written substitute transport is
used. See the [official SDK](https://github.com/modelcontextprotocol/python-sdk)
and [MCP authorization specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization).

Use the existing Render service, with no extra service or paid plan:

| Setting | Value |
| --- | --- |
| Preview branch | `phase8-mcp` (review without merging) |
| Build command | `pip install -r requirements-api.txt` |
| Start command | `python -m alphaos_api` |
| Health check | `/health` |
| Workers / instances | One / one |
| Public origin | `ALPHAOS_PUBLIC_URL=https://alphaos.onrender.com` (default) |

The public origin must be an HTTPS origin without a path. Change it only when
hosting at another stable domain. The existing `ALPHAOS_API_TOKEN`,
`PUBLIC_API_SECRET` and optional account preference remain server-side. Existing
Render Secret Files continue to work; see [REST deployment](RESEARCH_API.md).
There is no additional OAuth signing secret or OpenAI API key to configure.
Python 3.12 is the CI target. Startup disables access logs; leave SDK/HTTP debug
logging off and do not log request bodies, query strings or authorization headers.

The CIMD identity is ChatGPT's stable HTTPS metadata URL. AlphaOS re-fetches and
validates it after restart; its local metadata cache is disposable, not a client
registry. A CIMD connection needs no app recreation when Render restarts.

OAuth grants, pending consent/PKCE state, authorization codes and research
snapshots remain in memory. A deploy, crash or free-tier sleep invalidates them.
Reconnect and sign in again after restart. Refresh tokens fail closed with
`invalid_grant`; old tokens are never silently restored. Durable state would
still be needed for uninterrupted login/refresh across restarts. Do not add
workers or instances without shared authorization/cache storage.

Legacy DCR registrations remain process-local and expire after 24 hours. An
existing DCR app must be recreated once with CIMD to remove that dependency.
Durable DCR would require a shared database or persistent volume; the free Render
filesystem is not a durable solution. No paid storage has been provisioned.
Rolling back the service to `phase7-research-api` removes MCP and retains REST.

## Authentication architecture

- `/mcp` requires an opaque OAuth access token with `research:read`, bound to
  the exact `/mcp` resource. The REST owner token is rejected by MCP.
- REST `/v1` continues to require the existing bearer token; OAuth tokens do not
  authenticate REST. Public credentials never become client credentials.
- Discovery is at `/.well-known/oauth-protected-resource/mcp` and
  `/.well-known/oauth-authorization-server`. `/register`, `/authorize`, `/token`,
  `/revoke` and `/oauth/consent` implement the private authorization flow.
- The SDK validates client authentication, exact redirect matching and PKCE S256.
  AlphaOS additionally enforces the resource indicator, owner consent, scope,
  fixed callbacks and bounded storage. Public and confidential registered clients
  are supported; there is no client-credentials grant.
- CIMD fetches are restricted to the exact official `https://chatgpt.com/oauth/client.json`
  and callback-specific `/oauth/{callback_id}/client.json` locations. Redirects
  are not followed, TLS verification stays enabled, response size/time are
  bounded, and identity, callback, grants and public authentication support are
  validated. No arbitrary URL or JWKS URL is fetched. Cache-Control is respected
  with a maximum five-minute metadata cache.
- All issuer strings use the exact public origin without a trailing slash.
  HTTP Basic credentials can be supplied solely in the Authorization header;
  the adapter supplies the SDK's internal form field while retaining its checks.
- Consent requires the owner token, an exact same-origin POST, a one-use pending
  request and a CSRF value bound to a Secure/HttpOnly/SameSite cookie. No third-party
  assets load on that page. Client text is escaped and responses are not cached.
- Consent requests last 5 minutes; authorization codes last 60 seconds and can
  be exchanged once. Access tokens last 15 minutes. Refresh tokens rotate and
  last 8 hours; replay revokes the token family. Revocation also revokes the family.
  Changing the owner token invalidates existing codes and grants.
- Registration, authorization, token and revocation endpoints allow 30 requests
  per minute each, globally; consent submissions allow 10. These conservative
  bounds are intended for one owner. Request bodies are limited to 128 KiB.
- Errors omit provider exceptions, input values and OAuth error descriptions.
  Existing response sanitization removes configured credential values and
  sensitive fields. Keep credentials out of tool arguments and prompts.
- Production OAuth diagnostics log only fixed stage names and status codes,
  never client IDs, queries, headers, bodies, codes or credentials.

## Read-only tools and contracts

All ten tools declare `readOnlyHint=true`, `destructiveHint=false`,
`idempotentHint=true`, and `openWorldHint=true`. “Idempotent” does not imply frozen
market data: refreshes and elapsed cache lifetimes can change observations.
There are no trading, account-transfer, portfolio-access or recommendation tools.

| Tool | Inputs / existing REST operation |
| --- | --- |
| `market_snapshot` | symbol, horizon=3, optional snapshot_id; `/v1/market/{symbol}` |
| `price_structure` | symbol, levels=3, horizon=3, optional snapshot_id; `/v1/structure/{symbol}` |
| `forward_distribution` | symbol, horizon=3, optional snapshot_id; `/v1/distribution/{symbol}` |
| `live_quote` | symbol; `/v1/quote/{symbol}` |
| `option_expirations` | symbol; `/v1/options/{symbol}/expirations` |
| `scan_credit_spreads` | symbol, strategy=both, optional expiration, dte_min=1, dte_max=7, research_horizon=3, maximum_short_distance=0.05, minimum_credit=0.05, maximum_candidates=20, wing_width=1, refresh=false |
| `research_candidate` | candidate_id; `/v1/candidates/{candidate_id}` |
| `research_vertical` | symbol, expiration, option_type, short_strike, long_strike, horizon=3, refresh=false |
| `research_explicit_trade` | `trade`: existing TradeRequest object |
| `compare_trades` | `comparison`: existing CompareRequest object |

Symbols remain SPY/QQQ and horizons 1, 2, 3, 5 or 10 observed sessions. Dates
are ISO dates; credit is dollars per share, wing width is dollars, and maximum
short distance is a fraction of spot. Explicit expiration overrides DTE filters.
Trade and comparison body examples and field bounds are in [RESEARCH_API.md](RESEARCH_API.md)
and the existing `/openapi.json`; the MCP tool input schemas expose the same models.

Each success has `structuredContent` containing the existing REST JSON, mirrored
as JSON text for clients. It preserves `meta`, `evidence`, `caveats`, schema version,
generation/source data, research session/close, quote timestamp/current spot,
observed-session horizon, samples and applicable snapshot/candidate IDs. Missing
fields remain missing as in the original endpoint; MCP invents no new evidence.
Tool errors have `isError=true` and a sanitized structured error. Expired IDs
return an explicit stale-snapshot error; the adapter never silently reprices them.

## Interpretation

Candidate order is generator order, not ranking. Historical frequencies are
descriptive, not calibrated forecasts. Threshold survival is not option POP.
Scenario EV is historical scenario economics, not guaranteed expectancy.
Current quotes and completed research sessions have separate timestamps.
Calendar DTE and observed-session horizons are different: **0–2 DTE with
research_horizon=3 is not expiration-matched profitability evidence**.
Support/resistance describes history, not guaranteed price barriers; daily OHLC
does not reconstruct exact intraday paths. Preserve sample sizes and caveats.
These instructions are present in MCP server/tool descriptions as well as here.

## Verification

Run `python -m pytest -q` with the full `requirements.txt` and pytest installed.
`tests/test_mcp_api.py` exercises discovery, unauthorized access, legacy initialize,
current-protocol list/call, all research workflows, input/provider errors, exact
tool inventory, REST parity, PKCE, redirects/resources, consent CSRF, confidential
clients, expiry, code replay, refresh replay, revocation, scope, rate limits and
host/origin/body limits. Providers are mocked and credentials are test values.
Regression tests also compare issuer strings exactly, exercise header-only Basic,
and rebuild the server to verify CIMD identity recovery while old grants remain
invalid. CIMD metadata and network failures fail closed.
The existing suite separately covers Streamlit and the research engines.

Deployment checks must test authenticated initialization, tools/list and a real
Public quote through tools/call, plus retained REST health/auth behavior. Record
the deployed commit and distinguish these protocol checks from the final actual
ChatGPT connection/tool-call test. Never put credentials or OAuth tokens in test
reports, checked-in scripts, screenshots or conversations.
