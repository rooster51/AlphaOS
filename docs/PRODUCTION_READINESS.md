# AlphaOS 2.0 production readiness

Audit date: 2026-10-06. Documentation only; no deployment, production smoke test,
configuration change, migration or journal implementation was performed.

## Decision and evidence

**NO-GO — BLOCKERS MUST BE RESOLVED**

Render is missing `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`. The new archive
workflow will fail closed without both. Also resolve runtime parity before approval:
CI uses Python 3.12, but the last Render build explicitly used default Python 3.14.3.
Both commits contain `runtime.txt` requesting `python-3.12`; that file demonstrably
did not select Render's runtime. Under separate approval, set a supported, fully
qualified Python 3.12 patch using `PYTHON_VERSION`, or validate the target dependency
set and complete regression suite on Render's actual runtime. Do not change it now.

### Repository runtime follow-up

The `alphaos2/production-runtime` branch resolves runtime selection in repository
configuration: root `.python-version` pins **3.12.14**, and the regression CI
workflow uses `python-version-file: '.python-version'`. This released 3.12 patch
matches the available local validation runtime. It is intentionally fixed rather
than floating to a later patch. Render documents `.python-version` as its native
repository selector; the existing service root is the repository root. A Render
`PYTHON_VERSION` environment override takes precedence, so verify it remains absent
or matches before a future deployment. No override was present in the audit.

Keep `runtime.txt` unchanged for compatibility with other historical consumers;
it still states the same 3.12 major/minor but is **not** the Render selector.
No Render configuration was changed. This fix must be reviewed/merged separately;
deploying original main `8147861` alone will not include the new pin. A future
deployment approval must name the new reviewed SHA containing this fix. The old
target/procedure below remains the preserved audit record, not authorization.

The user must configure `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` directly in
Render. **Never enter either value into ChatGPT, Codex, GitHub, source files or PR
comments.** Deployment remains blocked until Render reports both variables present.
Avoid configuration-save actions that also deploy; this task authorizes neither.

For the existing verified archive, these two variables are the only required
Supabase environment settings. `archive_client()` passes them to `create_client`.
The reader selects existing `public.option_snapshots` and downloads existing private
`market-archive` objects by metadata path. No bucket variable, anon key, database
password, new permission grant, RLS change or migration is required by this code.
This depends on using the same functioning archive project and its authorized
service-role key; code inspection cannot verify the user's future values or live
project permissions. Post-deployment read verification remains pending.

The REST sanitizer covers both values; MCP sanitizes the internal REST response
again. Health contains only configuration booleans, not values. Archive SDK errors
are replaced with safe errors without exception chaining; the API boundary catches
unexpected errors before Uvicorn receives a raw traceback. Protocol diagnostics
emit allowlisted categories, not tool argument values, secrets or raw exceptions.
Neither value is introduced into Git. Regression coverage now exercises both
synthetic Supabase values through REST and authenticated MCP responses.

Runtime follow-up validation on Python 3.12.14: full regression **624 tests plus
40 subtests passed** (138.37s); focused API/MCP/archive/market tests **106 passed**
(39.01s); standalone OAuth/MCP protocol suite **49 passed** (15.53s). The one-test
increase over the 623-test baseline is the second parameterized Supabase redaction
case. No application behavior changed. CI must also pass on the PR's final SHA.

Repository target and remote main: `81478618edd1757c3a509291c379badbcb3a6a01`.
PR #16 is merged; post-merge CI passed as recorded in the milestone handoff.
Render service: AlphaOS, `srv-daqillmgekts73ak0mj0`, native Python, Free tier,
Virginia, `https://alphaos.onrender.com`.
Live commit: `4ef8d5bb1487af1612d8be33cf53f2b2c3be7124`.
Last successful deployment: `dep-dauhqu5g1s2s73d0abmg`, September 30, 2026,
10:32:24 AM EDT, duration 1m10s. Dashboard shows manually selected commit;
automatic deployment is disabled. Linked branch remains `phase8-mcp`.

## Configuration inventory

Statuses indicate configuration presence, not successful live credential validation.
Secret contents were not displayed or changed.

| Item | Status |
|---|---|
| ALPHAOS_API_TOKEN | PRESENT |
| ALPHAOS_PUBLIC_URL | OPTIONAL |
| PUBLIC_API_SECRET | PRESENT |
| PUBLIC_ACCOUNT_NUMBER | PRESENT |
| SUPABASE_URL | MISSING |
| SUPABASE_SERVICE_ROLE_KEY | MISSING |
| ALPHAOS_ARCHIVE_MAX_AGE_SECONDS | OPTIONAL |
| PORT override | OPTIONAL |
| Python runtime | PRESENT |
| PYTHON_VERSION override | OPTIONAL |
| Build command | PRESENT |
| Startup command | PRESENT |
| API/MCP dependency manifest | PRESENT |
| HTTP health-check path | OPTIONAL |
| Pre-deploy migration command | NOT REQUIRED |
| Ledger migration | NOT REQUIRED |

The dashboard has no environment-variable rows or linked environment groups. Its
three secret filenames are `ALPHAOS_API_TOKEN`, `PUBLIC_API_SECRET`, and
`Public_Account`. The existing loader recognizes the last as an account-number
alias. Presence does not establish credential validity. The Supabase client reads
environment variables directly: configure both missing variables in the Render
service environment under separate approval; GitHub/Streamlit secrets do not
automatically propagate. Do not substitute the Public secret for the API token.

The default public origin is the production URL. Archive age defaults to 600
seconds; changing it changes evidence eligibility and should be intentional.
The server binds `0.0.0.0` using platform PORT (fallback 8000), one worker.
Render currently builds with `pip install -r requirements-api.txt` and starts
`python -m alphaos_api`; root directory and pre-deploy command are empty.

Existing configuration covers the 14 legacy tools. New `research_structure` and
`compare_structures` need no market/archive credentials beyond authenticated
service access. New `run_market` and verified archive reads are NOT configured.
Public history is optional supplementary evidence for that workflow; unavailable
history remains unknown. Supabase access from Render remains untested.

## Production delta: deployed commit to approved target

| Area | Classification | Effect |
|---|---|---|
| API/MCP integration | expected/read-only | Adds `run_market`, `research_structure`, `compare_structures`, and three POST research endpoints; preserves 14 legacy tools |
| Research engine | expected/read-only | Normalization, classification, routing, construction, economics, capital eligibility and descriptive comparison use existing AlphaOS 2 modules |
| Archive reader | expected/read-only | Lazy verified Supabase metadata selection and private archive download; checksum, identity, timestamps and freshness enforced; no live-chain fallback |
| Supabase credentials | configuration requirement | Two missing environment variables needed for archive research; service-role key stays server-side |
| Public access | expected/read-only | Existing provider retained; archive research optionally uses completed daily bars, not a new collector |
| Legacy service quality | expected/read-only | Shared timestamp normalization, refreshed cached-chain quality, consumed-contract quality for spread/scan research |
| Premium economics boundary | expected/read-only | Time validation allows zero years (`< 0` instead of `<= 0`); no brokerage behavior |
| API dependencies | potential deployment risk | Adds `supabase>=2.6.0,<3`; MCP remains 2.2.0, Public SDK 0.1.17; broad dependency ranges are not a reproducible lock |
| Runtime | potential deployment risk | Render 3.14.3 versus CI 3.12; existing runtime.txt was ineffective |
| Startup | configuration requirement | Existing explicit build/start remains correct despite removed Procfile; single-process server, no collector or migration entry point |
| OAuth/auth | expected/read-only | Approved implementation unchanged; process replacement invalidates grants |
| Collector modules/scripts | intentionally inactive | API startup does not invoke intraday collectors or persistence writers |
| Scheduled collection | external infrastructure effect | Existing external scheduler/workflow-dispatch is separate from Render; deploying this web service does not trigger or reconfigure it |
| GitHub Actions | external infrastructure effect | Target already has manual intraday dispatch, disabled legacy daily automatic schedule, CI updates and removal of obsolete branch-specific index validation workflows; Render deploy does not run them |
| SQL artifacts | intentionally inactive | Standalone archive/slot/ledger SQL files are not startup migrations |
| Streamlit/UI changes | intentionally inactive | Present in repository delta, not served by `python -m alphaos_api` |
| Journal / execution | intentionally inactive | Foundation only; no new persistence or brokerage tools/routes |

Changed API files are `app.py`, `mcp_server.py`, `service.py`, and new `research2.py`.
The API provider, config, startup entry point, contracts, cache and OAuth files
remain unchanged. Public provider/history and existing archive payload generation
are reused. `public_observations.py` is not a substitute collector for the API.

New REST paths:

- POST `/v1/research/market`
- POST `/v1/research/structure`
- POST `/v1/research/structures/compare`

`available_capital` and `expiration` pass through to `run_latest_market`.
Capital is expiration maximum-loss eligibility, not broker margin. Objective is
context only and does not rewrite evidence or filter routes. Comparisons preserve
input order and return no winner, ranking or recommendation.

## Storage and OAuth safety

`ArchiveResearchService` lazily calls the existing `archive_client` and
`read_latest_option_snapshot`. Metadata reads and private Storage downloads are
read-only. A failed archive read returns sanitized `503 archive_unavailable`;
it never silently switches to a live option chain. Writer functions in the same
archive module are invoked by the separate collector, not these API routes.

The inspected build/start commands, API import/lifespan paths and GitHub workflows
do not execute SQL, Supabase CLI migrations, backfills or journal initialization.
There is no `supabase/migrations`, `supabase/config.toml`, or Edge Function deployment
path. `supabase/alphaos2_trade_ledger.sql`, `market_archive.sql` and
`intraday_slot.sql` are standalone artifacts. Deployment does not create ledger
tables, change `public.trades`, archive schemas or RLS, write journal data, or
modify stored market data. No ledger SQL was applied in this milestone.

The Supabase Preview check was successful but its authenticated dashboard was
unavailable. Exact Preview actions and live database schema state were not
independently inspected. This does not prevent establishing the absence of a
repository/Render migration path. Do not infer that no ledger tables exist merely
from an unapplied artifact in this workflow.

`alphaos_api/mcp_auth.py` is byte-identical in deployed production, approved Phase
8 (`cd59c2c4026a9505ecd25e1976da241b2dc4c534`) and the target:
SHA256 `7af54ccbacd3738f2b2cb1a1b1f67819ecf42536983283c36f671824a75904aa`.
CIMD, owner consent, PKCE, process-local grants and fail-closed restart remain.
No persistent grant database, identity redesign or brokerage-secret exposure is
introduced. Deployment/restart requires clients to reconnect through OAuth.

## Procedure after separate explicit approval only

1. Resolve missing Render archive environment settings and runtime parity under
   separately approved configuration work. Preserve existing token/Public files;
   never print values. Confirm configuration saves have not inadvertently deployed.
2. Reconfirm approved target SHA and CI. Keep auto-deploy disabled. Do not select
   Deploy latest commit: the service's linked branch is still phase8-mcp.
3. In Render AlphaOS, select **Manual Deploy -> Deploy a specific commit**, paste
   `81478618edd1757c3a509291c379badbcb3a6a01`, verify the SHA, then Deploy Commit.
4. Confirm build uses `requirements-api.txt`, expected runtime, and start command
   `python -m alphaos_api`. Record deploy ID, timestamp and full deployed SHA.
5. Wait for Live, then run the tests below. The configured health path is empty,
   so Render uses TCP readiness; Live alone does not prove archive readiness.

Render starts a replacement process; existing OAuth grants and process caches
are lost. Do not promise uninterrupted sessions or exact downtime on this Free
service. No application collector/background job or database action starts.
Failed builds/readiness retain the previous deployment; once traffic switches,
application-level failure still requires explicit rollback.

Rollback: Manual Deploy -> Deploy a specific commit ->
`4ef8d5bb1487af1612d8be33cf53f2b2c3be7124` -> Deploy Commit. Confirm Live and the
full old SHA, then health and legacy MCP access. Reconnect OAuth again. Rolling
back code does not restore changed environment settings or dependency versions;
retain a secure pre-change configuration record and explicitly approve any
restoration. No database rollback is needed because this release runs no migration.

## Prepared read-only smoke tests (NOT RUN)

Run market tests during an active NYSE session with a recent completed archive.
Outside that window stale data may correctly fail closed; do not relax the age
limit to manufacture success. Use server-held credentials, never log headers,
tokens, consent values or connection strings. Record sanitized status, schema,
timestamps and provenance alongside the exact deployed SHA.

REST requests use `Authorization: Bearer <existing owner API credential>`;
JSON bodies use `Content-Type: application/json`. Angle-bracket text is a
placeholder, never a suggested credential. MCP uses the OAuth-issued access token,
not the owner credential as a replacement OAuth grant.

1. GET `/health`: 200; `read_only=true`, `authentication_configured=true`,
   `schema_version=alphaos-research-v1`. The existing health schema stays v1;
   new research envelopes use `alphaos-interface-v2`. Health does not query storage.
2. POST `/v1/research/market` body `{"symbol":"QQQ"}`, then `{"symbol":"SPY"}`.
   Require a verified archive response, not mocked evidence. Inspect provenance,
   checksum/identity enforcement via the verified reader path, freshness, and
   separate slot/observation/collection/request timestamps. Confirm normalization,
   classification, routing, supported candidates, economics and comparison;
   unknown evidence stays unknown and winner/recommendation remain null. Empty
   supported opportunities are a valid research result when exclusions explain it.
   A 503 is not a successful archive test; do not claim its generic error pinpoints
   checksum versus configuration. Never corrupt production archives to test failure.
3. Repeat QQQ body with `"available_capital":200`. Confirm no included structure
   exceeds the max-loss ceiling and exclusions explain ineligible structures.
   Add an `expiration` actually present in the verified snapshot and confirm it is
   retained by the engine; an unavailable expiration must not silently substitute.
4. Repeat with `"objective":"Bullish thesis regardless of evidence"`, choosing a
   conflicting thesis after observing baseline. Compare the same archive identity
   and history context; classification must remain evidence-based. Changing market
   observations between calls is not evidence of an objective override.
5. POST `/v1/research/structure` using scenario A below. Require v2/read-only,
   supplied-scenario provenance, debit-spread economics (120-dollar loss ceiling
   and 380-dollar profit ceiling with zero fees), with no provider/archive lookup.
6. POST `/v1/research/structures/compare` with
   `{"structures":[A,B],"thesis":"Compare supplied scenarios"}` replacing A/B
   with the JSON objects below. Preserve A then B, null winner/recommendation,
   no scores/ranking. Long-call unbounded profit must serialize as `"unlimited"`.

Scenario A (fixed dates are explicit research inputs, not current quotes):

```json
{"symbol":"SPY","expiration":"2026-10-09","as_of":"2026-10-06","spot":500,"credit":-1.2,"fees":0,"legs":[{"type":"Call","strike":500,"qty":1},{"type":"Call","strike":505,"qty":-1}]}
```

Scenario B:

```json
{"symbol":"SPY","expiration":"2026-10-09","as_of":"2026-10-06","spot":500,"credit":-2.2,"fees":0,"legs":[{"type":"Call","strike":500,"qty":1}]}
```

MCP protocol checks after authorized deployment:

- Unauthenticated POST `/mcp` must challenge with OAuth resource metadata rather
  than return tools. Follow its `resource_metadata` URI and authorization-server
  metadata; verify production issuer/resource and unchanged CIMD/PKCE support.
- Complete real OAuth consent and initialize with `Content-Type: application/json`
  and `Accept: application/json, text/event-stream` using:
  `{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"alphaos-readiness","version":"1.0"}}}`.
  Honor negotiated protocol, send `notifications/initialized`, then
  `{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}`.
- Expect 17 tools: three new plus legacy `market_snapshot`, `price_structure`,
  `forward_distribution`, `live_quote`, `option_expirations`, `scan_credit_spreads`,
  `research_candidate`, `research_vertical`, `research_explicit_trade`,
  `compare_trades`, `run_symbol_research`, `unified_candidate_research`,
  `unified_vertical_research`, `unified_explicit_trade_research`.
  No journal/trade mutation tools should appear.
- Call `run_market` with arguments from steps 2-4. For `research_structure`, wrap
  scenario A as `{"structure":A}`; for `compare_structures`, wrap the comparison
  body as `{"comparison":{"structures":[A,B]}}`. Use `tools/call` and inspect
  the real structured result/error, not only an HTTP 200.

## Actual ChatGPT verification (later, user involved)

Only after REST/MCP checks pass, open ChatGPT's custom MCP connection management,
add or reconnect AlphaOS with `https://alphaos.onrender.com/mcp` and OAuth, and
complete owner consent. Refresh the tool list after deployment; expired
process-local grants require reauthorization. Do not expose the owner credential
in chat. In a new chat select the AlphaOS connection and issue, in order:

1. `Run QQQ`
2. `Run QQQ with $200 available`
3. `Run SPY`

Inspect actual tool invocations and archive-backed responses. The intended path
is ChatGPT -> OAuth -> MCP -> authenticated REST -> verified Supabase archive ->
run_latest_market -> normalization/classification -> routing -> economics/capital
filtering -> descriptive comparison -> MCP -> ChatGPT. Chat text alone is not
proof. No successful actual ChatGPT verification is claimed by this audit.

## Documentation validation and references

The original audit changed Markdown only. It did not rerun the already-approved code's
full suite or execute production smoke tests. Validate the diff with
`git diff --check` and confirm only the three intended documentation files change.
Existing integration test results belong to the prior approved milestone, not a
new run in this audit.

- [Render manual deployments](https://render.com/docs/deploys)
- [Render Python version selection](https://render.com/docs/python-version)
- [Render health checks](https://render.com/docs/health-checks)
- [Supabase GitHub integration and migrations](https://supabase.com/docs/guides/deployment/branching/github-integration)
- [OpenAI custom MCP server documentation](https://developers.openai.com/api/docs/guides/custom-mcp-server)
- [Future journal design](alphaos2_trade_ledger.md)

All deployment and test steps above are prepared instructions, not executed actions.
