# AlphaOS Research API — Phase 7

For ChatGPT Developer Mode, use the [Phase 8 MCP interface and OAuth setup](MCP.md).
The REST schema and static bearer configuration below remain available to REST
clients; they are not the remote MCP connection configuration.

Read-only SPY/QQQ research using the same Phase 1–6 engines and Public adapter
as Streamlit. It does not submit orders, select a winner, or rank candidates.
Streamlit remains a separate application. No hosting resource is created by
this repository. PR #4 must be reviewed before merging.

## Run independently

Use Python 3.12 and install `pip install -r requirements-api.txt` in a fresh
virtual environment. Streamlit, Supabase and UI secrets files are unnecessary.

| Environment variable | Purpose |
| --- | --- |
| `ALPHAOS_API_TOKEN` | Required private bearer token. Generate a long random value in a password manager; never reuse a brokerage credential. |
| `PUBLIC_API_SECRET` | Required for actual Public data; configure only in the server's secret manager. |
| `PUBLIC_ACCOUNT_NUMBER` | Optional account-selection preference; keep server-side. |
| `PORT` | Listening port, default 8000; use the host-provided value. |

Render **Secret Files** are also supported: `/etc/secrets/ALPHAOS_API_TOKEN`,
`/etc/secrets/PUBLIC_API_SECRET`, and `/etc/secrets/PUBLIC_ACCOUNT_NUMBER`.
The existing filename `Public_Account` is accepted for the account preference.
Each file must contain just its raw value or a single `NAME=value` line.
Environment variables take precedence, even when empty. The API startup loads
these explicit mounts into its process environment without logging contents.

Start from the repository root: `python -m alphaos_api`. The entry point starts
Uvicorn on `0.0.0.0`, uses one worker, disables access logs, and fails closed
without the API token. The equivalent explicit command is
`uvicorn alphaos_api.app:app --host 0.0.0.0 --port 8000 --workers 1 --no-access-log`.
If started directly without a token, all protected routes return 503.

`GET /health` is public and checks process liveness, **not** Public connectivity.
`/docs` and `/openapi.json` are public schemas without credentials. Every `/v1`
route requires `Authorization: Bearer <ALPHAOS_API_TOKEN>`. Missing credentials
return 401, incorrect credentials 403; comparison uses `hmac.compare_digest`.

`modules/public_provider.py` owns the existing SDK calls. The server reads
environment variables only. Streamlit's cached wrappers in `public_data.py`
call that same adapter and retain `st.secrets` fallback. Environment variables
take precedence, including an explicitly empty value. Restart both services
after changing Public credentials to clear cached sessions and data.

## Deploy separately from Streamlit

One small Python web service is sufficient. For example, on Render:

1. Create a Web Service connected to `rooster51/AlphaOS`, using Python 3.12.
   Select `phase7-research-api` for an explicitly approved preview; select
   `main` only after PR review and merge. Keep automatic deployment disabled
   until the branch and release are approved. Review the hosting price before
   creating a resource; no paid plan has been selected here.
2. Set build command `pip install -r requirements-api.txt` and start command
   `python -m alphaos_api`. Set health check path `/health`.
3. Add the environment secrets above through the host's secret settings.
   Keep **one instance and one worker** because snapshots are process-local.
4. Deploy and retain its stable HTTPS service URL. Confirm TLS and unauthenticated
   `/health`, then confirm protected endpoints reject missing/wrong bearer tokens.
5. With the correct token, check a quote, market snapshot, scan, and candidate
   using your Public entitlement. Verify symbol, quote timestamps, current spot,
   completed research session, exact contracts and natural credit. This live
   entitlement check cannot be replaced by mocked tests.
6. Configure the proxy to avoid logging authorization headers, bodies or query
   strings. Keep SDK/HTTP debug logging off. Restrict access to the intended
   private client; add host-side request limits before wider exposure.

This adapts [Render's FastAPI deployment instructions](https://render.com/docs/deploy-fastapi)
to AlphaOS's module entry point. No database, Redis or additional paid service
is required. Free-tier sleep/restarts, if applicable to the chosen plan, lose
all snapshot IDs. Multi-worker scaling requires a shared cache design first.

## HTTP/action contract

All paths below except health require bearer authentication. Symbols are SPY
and QQQ; observed-session horizons are **1, 2, 3, 5, 10**. Dates are ISO dates.

| Method and path | Operation ID / result |
| --- | --- |
| GET `/health` | Liveness, schema version, configured-auth boolean |
| GET `/v1/market/{symbol}` | `get_market_snapshot`: completed market state and current underlying quote |
| GET `/v1/structure/{symbol}` | `get_price_structure`: descriptive historical zones |
| GET `/v1/distribution/{symbol}` | `get_forward_distribution`: existing analog distribution |
| GET `/v1/quote/{symbol}` | `get_live_quote`: last available Public quote and timing |
| GET `/v1/options/{symbol}/expirations` | `get_option_expirations` |
| GET `/v1/options/{symbol}/chain/{expiration}` | `get_option_chain`: normalized contracts and quote quality |
| GET `/v1/options/{symbol}/vertical` | `research_trade`: exact live vertical and full research |
| GET `/v1/options/{symbol}/scan` | `scan_credit_spreads`: bounded unranked PCS/CCS candidates |
| GET `/v1/candidates/{candidate_id}` | `research_candidate`: full research on the saved scan observation |
| POST `/v1/trade/research` | `research_explicit_trade`: user-supplied spot, credit and exact legs |
| POST `/v1/trade/compare` | `compare_trades`: primary and candidate evidence in input order |

Market/structure/distribution accept `horizon`, optional explicit `spot`, and
optional `snapshot_id`. To preserve one observation, pass the returned ID with
the same symbol/horizon to the other two routes; mismatches return 409.

Vertical requires `expiration`, `option_type=put|call`, `short_strike`,
`long_strike`; optional `horizon=3`, `refresh=false`. It obtains one underlying
observation and one chain for that exact expiration (or their valid cache
entries), validates exact OSI identities and both bid/ask markets, and uses
**short bid minus long ask**. It never substitutes contracts or expirations.
Natural credit is a hypothetical fill, not an executable price guarantee.

Scan parameters: `strategy=pcs|ccs|both`, optional `expiration` (takes precedence
over DTE filters), `dte_min=1`, `dte_max=7`, `research_horizon=3`,
`maximum_short_distance=0.05` (fraction of spot), `minimum_credit=0.05`
(dollars per share), `maximum_candidates=20` (1–100), `wing_width=1`,
`refresh=false`. At most five expirations are allowed. Generator order is
preserved and capped from the front; `total_generated` and `truncated` report
the cap. The existing premium generator supplies spreads; no second generator
or composite score is added. An empty qualifying set is not a recommendation.

Example relative requests (use your HTTPS base URL and bearer header):

```text
GET /v1/market/QQQ?horizon=3
GET /v1/structure/QQQ?horizon=3&snapshot_id=<returned-id>
GET /v1/distribution/QQQ?horizon=3&snapshot_id=<returned-id>
GET /v1/options/QQQ/scan?strategy=ccs&dte_min=1&dte_max=7&research_horizon=3
GET /v1/candidates/<returned-candidate-id>
GET /v1/options/QQQ/vertical?expiration=<available-ISO-date>&option_type=call&short_strike=745&long_strike=746&horizon=3
```

Manual research body (replace date/prices with your intended observation):

```json
{
  "symbol": "QQQ", "expiration": "2026-09-25", "spot": 740,
  "credit": 0.25, "horizon": 3, "method": "tolerance",
  "legs": [
    {"type": "Call", "strike": 745, "qty": -1},
    {"type": "Call", "strike": 746, "qty": 1}
  ],
  "commission_per_contract": 0, "entry_slippage": 0, "terminal_friction": 0
}
```

This is a schema example, not a market observation. Expired dates fail. Only
one-lot vertical credit spreads are accepted. Comparison body is
`{"research_trade": <trade>, "candidates": [<trade>, ...]}` (1–20 candidates).
Symbol, spot, horizon, analog method and friction must match. Each candidate
gets its own threshold/payoff/robustness evaluation over the shared snapshot.
Manual prices are explicitly labeled and do not trigger a live quote lookup.

## Evidence, units and chronology

Responses use `{meta, evidence, caveats}`. `meta` always contains
`schema_version`, `generated_at`, `source`, `symbol`, `research_session`,
`research_close`, `quote_as_of`, `current_spot`, `observed_session_horizon`,
`snapshot_id`; non-applicable metadata on raw-data routes is null.

Research close is the latest completed daily session used for historical
state. The cutoff excludes the current New York date, even after market close;
it advances on the next date. Public five-year regular-market daily OHLC feeds
the existing dataset/feature/outcome engines. Current spot is a separate quote
observation (or explicit user input). Historical returns are reanchored to it
without changing the historical state. Provenance includes OHLC hash, cutoff,
analog configuration, audit and engine versions.

Historical terminal survival is favorable-side terminal frequency, not option
POP. Touch includes equality; finish-beyond is strict and terminal equality is
separate. Positive-payoff frequency applies the existing expiration payoff to
the selected observed-session scenario distribution. The research horizon is
**not automatically the option's calendar DTE**. No early exit/intraday path,
assignment, future option IV, forecast calibration, or attainable fill is
inferred. Overlapping observations and non-overlap diagnostics remain explicit.

Frequency and ratio values are fractions. Credit/strikes/spot are dollars per
share; payoff, max profit/loss, EV and friction are dollars per one-lot spread.
`EV_max_risk` uses Phase 5.2's entry max-risk denominator before extra friction.
Finite JSON is mandatory: undefined and infinite values serialize as null;
`profit_factor_unbounded` distinguishes a no-loss profit factor. Full evidence
includes net/non-overlap economics and fixed robustness populations.

Required credit uses the same scenario payoffs, fees/friction and denominator.
For observed credit `c`, net scenario EV `E` dollars, and entry max risk `R`
dollars: `c_zero = c - E/100`; `c_5pct = c + (0.05*R - E)/105`.
Changing credit by `d` changes payoff by `100*d` and risk by `-100*d`.
These algebraic thresholds are **not fair value**. Values are not clamped;
feasibility booleans state whether each lies strictly between zero and width.

## Cache, timestamps and errors

Bounded process-local caches: quotes/chains/context 30 seconds, history and
expiration lists 300 seconds, saved snapshots/scans 120 seconds from creation.
There are at most 96 data entries, 64 research snapshots and 32 scans. Entries
are copied on read and may be evicted earlier under load. History cache keys
include the New York cutoff date. Locks coalesce data loads.

Scan/candidate IDs hash their observation and parameters, preserving order.
A candidate reuses its saved underlying, history and chain even if the general
quote cache changes. `snapshot_valid_seconds` is the original maximum lifetime,
not a sliding remaining-time guarantee. Expired/evicted IDs return 410
`stale_snapshot`; the caller must explicitly rescan. `refresh=true` on scans
or exact verticals fetches new quote/chain observations; completed history may
still use its separately dated 300-second cache. Retrieval and provider quote
timestamps identify these observations; no silent candidate refresh occurs.

Quote timing reports missing timestamps, future timestamps and any quote older
than 15 minutes. Old quotes are flagged, not rejected; market closure and feed
delay are unverified. A chain response reports incomplete quote counts and
empty status. Malformed exact legs fail; a scan excludes unusable legs/candidates.

Errors use `{"schema_version":"alphaos-research-v1","error":{"code":...,"message":...}}`.
Codes include `unsupported_symbol`, `unsupported_horizon`,
`invalid_vertical_orientation`, `expired_option`, `expiration_unavailable`,
`contract_unavailable`, `contract_mismatch`, `missing_quote`, `crossed_market`,
`nonpositive_natural_credit`, `public_authentication_failure`,
`public_rate_limit`, `insufficient_historical_data`, `insufficient_analog_sample`,
`stale_snapshot`, `snapshot_mismatch`, `invalid_candidate_id`, and `invalid_request`.
Provider failures are sanitized; auth/config/provider availability failures
use 503, rate limiting 429, missing contracts 404, stale IDs 410. Raw SDK
exceptions, account data and credentials are never returned. Unexpected errors
receive a fixed 500 response without forwarding a raw traceback to Uvicorn.

## Future ChatGPT connection

The operation IDs above are the intended conversational contract. For a private
GPT Action, use the deployed `/openapi.json`, add its stable HTTPS URL to the
schema's `servers` array, and configure API-key authentication to send the
AlphaOS bearer token. Store that token in the action's authentication settings,
not prompts/schema examples; never provide Public credentials to the GPT.
OpenAI documents action authentication in its
[official guide](https://developers.openai.com/api/docs/actions/authentication).

Suggested instructions: state both research date/close and quote time/spot;
reuse returned snapshot and candidate IDs; resolve relative expirations to an
explicit available date; ask for missing strikes or horizon; distinguish
descriptive survival from positive payoff; present candidate order and evidence
without choosing a winner. A plugin/MCP wrapper can call the same HTTP methods
later; this release implements REST/OpenAPI, not that wrapper or GPT setup.

## Verification and remaining limits

Run `python -m pytest -q` with the repository/test dependencies installed.
API tests mock Public and require no brokerage credentials. They cover bearer
auth, safe errors, engine mapping, exact contract pricing, chronology, cache
reuse, expiration, scan ordering, required credit and independent server import.

This is a private single-token service, not multi-user OAuth or a public SaaS.
There is no per-user isolation, durable cache, API rate limiter, automated
trade execution or new forecast model. SDK history coverage/entitlements and
adjustment/calendar quality remain provider-dependent. Production TLS,
real Public connectivity/latency and GPT schema import require deployment
verification; none are claimed by a local or CI test pass.
