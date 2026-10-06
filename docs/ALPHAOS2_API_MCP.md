# AlphaOS 2.0 API/MCP integration

Development branch only: no deployment, migration or live verification is implied.
Integration base: main `249be6e` (PR #12). All research access is read-only.

## New interface

| MCP tool | Authenticated REST POST | Input |
| --- | --- | --- |
| `run_market` | `/v1/research/market` | `symbol` (QQQ/SPY), optional ISO `expiration`, `available_capital`, `objective`, `width` (default 5 points) |
| `research_structure` | `/v1/research/structure` | MCP `structure` object; REST body directly |
| `compare_structures` | `/v1/research/structures/compare` | MCP `comparison` object; REST body directly with `structures`, optional `thesis` |

Run example: `{"symbol":"QQQ","available_capital":300}`.
Resolve ambiguous dates like Friday into an explicit ISO date with the user.
Omitted expiration uses the first requested expiration in the latest archive,
as selected by the existing archive adapter. Unavailable explicit expirations
fail; the server never substitutes another date. Objective/thesis is recorded
context, not classifier evidence, a direction override or a candidate filter.

Explicit structure example:

```json
{"symbol":"QQQ","expiration":"2030-01-02","as_of":"2030-01-02",
 "spot":500,"credit":-1.2,"fees":0,
 "legs":[{"type":"Call","strike":500,"qty":1},
         {"type":"Call","strike":505,"qty":-1}]}
```

Positive quantities are long; negative quantities are short. `credit` is signed
package cashflow per share including quantities (debit negative); fees are dollars.
Standard 100-share contracts only. Inputs are user-supplied scenarios, not verified
quotes or fills. Explicit research supports long calls/puts and the existing
same-expiration debit/credit spreads, butterflies/BWBs and iron condors through
`research_position`. Structure recognition and payoff calculations stay in modules.
Comparison researches each supplied structure and retains input order and individual
contexts. Different dates, symbols and spots are not asserted to be equivalent.

## Exact Run QQQ flow

1. Scoped MCP OAuth -> MCP tool -> in-process authenticated REST request.
2. Pydantic contract validation -> `ArchiveResearchService.run`.
3. Existing `supabase_archive.archive_client` (lazy, server-side) and
   `read_latest_option_snapshot` select metadata and verify the private Storage
   payload's freshness, SHA-256, identity and availability. No writes or fallback
   to live option chains. Missing/stale/corrupt evidence returns safe HTTP 503.
4. Existing Public daily-history provider supplies completed-history input when
   available. Failure is disclosed and direction remains unknown; the core
   excludes incomplete/current sessions relative to the archive observation.
5. `run_latest_market` -> `run_market` -> archive adapter / NYSE session validation
   -> evidence classifier -> router -> existing constructors -> `research_position`
   -> max-loss capital eligibility -> `compare_strategy_research`.
6. JSON-safe interface envelope -> REST/MCP response -> ChatGPT. Invalid archive
   research context or unavailable expiration returns safe HTTP 422.

Capital and expiration pass directly through to `run_latest_market`. Capital is
an expiration max-loss ceiling, not buying power/margin. Same-day construction
keeps zero years and the AlphaOS-specific $0 credit floor; legacy default stays
$50. No POP at expiration, no artificial positive time, no fabricated regimes.

## Envelope and evidence

`schema_version=alphaos-interface-v2`, `request`, `read_only`, `research`,
`provenance`, `caveats`. `research` retains the entire engine payload and versions:

- `archive`: quality, rejected observations, failures, storage identity and freshness;
- `as_of` / `requested_as_of`: original observation versus API request time;
- `archive.observation`: slot, collection finish and chain response times;
- `research_session.market`: market/classification evidence and expected-move availability;
- `opportunity_state`, `strategy_routes`, `candidates`, `excluded`, `unavailable_routes`,
  `available_capital`, `comparison`, and caveats within `research_session`;
- candidate position legs retain provider quote timestamps and quality warnings.

Missing IV/Greeks/liquidity/regimes remain unknown. Unlimited long-call payoff is
the JSON string `unlimited`, not infinity or zero. Comparison's existing `winner`
and `recommendation` fields remain null. No scores or rankings are added. There is
no truncation of underlying research evidence to make the response shorter.

## Historical reconciliation / compatibility audit

Inspected Phase 7 `51289ce9`, Phase 8 `cd59c2c4`, Phase 9 index `4ef8d5bb`,
Phase 9 unified `92ed1104`, Phase 10a `c22366f6`, Phase 10b `3e9455c8`,
and Phase 10c `7755b7e2`. Reused the Phase 10a read-only API files and their
supporting provider/freshness/index/presentation modules, not whole branch history.
The historical Streamlit-only cache/selector/saved-trade freshness tests were not imported because those UI patches are not part of this integration. Existing main UI tests remain intact. Tool-list expectations add the three new tools; auth assertions are unchanged.
Index symbol validation and provider-response mapping are the narrow reconciliations
in shared history/structure modules; no payoff/classifier changes were imported.

| Existing tool(s) | Classification / decision |
| --- | --- |
| `market_snapshot` | Reusable unchanged: completed-session legacy market context |
| `price_structure` | Reusable unchanged: legacy historical structure |
| `forward_distribution` | Reusable unchanged: observed-session distribution |
| `live_quote` | Reusable unchanged: legacy quote timestamp/freshness contract |
| `option_expirations` | Reusable unchanged: provider expiration discovery |
| `scan_credit_spreads` | Reusable unchanged: legacy live PCS/CCS scan and candidate IDs |
| `research_candidate` | Reusable unchanged: saved legacy scan evidence, no silent repricing |
| `research_vertical` | Reusable unchanged: explicit live vertical |
| `research_explicit_trade` | Reusable unchanged: legacy explicit credit vertical scenario |
| `compare_trades` | Reusable unchanged: legacy common-context vertical scenario comparison |
| `run_symbol_research` | Superseded as default for general Run SPY/QQQ; remains backwards compatible for explicitly requested legacy live vertical/index workflows |
| `unified_candidate_research`, `unified_vertical_research`, `unified_explicit_trade_research` | Reusable unchanged: legacy Phase 9 five-section presentation |
| Phase 10b/10c position, monitoring, journal tools | Deferred, not registered or imported; not declared obsolete |

Legacy comparison is not redirected to cross-strategy comparison: its scenario
EV/common-horizon contract is materially different. New `compare_structures`
exposes the new engine without changing that contract. None of the listed read-only
tools were removed or renamed. Legacy engines remain explicit compatibility paths;
the new workflow never invokes their scan or scenario-research orchestration.
Existing index tools remain supported; new archive workflow supports SPY/QQQ only.

## Authentication and safety boundary

`mcp_auth.py` is byte-for-byte identical to approved Phase 8 `cd59c2c4`.
CIMD, DCR compatibility, process-local grants, fail-closed restart, PKCE, consent
CSRF/cookies/CSP, scope/resource validation and revocation remain unchanged.
Transport stays stateless Streamable HTTP with JSON responses, existing origin/host
checks and body limits. All 17 exposed tools are read-only research tools.
Response sanitization additionally redacts Supabase key/URL values. Secrets are
never tool parameters. No journal writes, ledger SQL, broker orders or production
mutations are enabled. Historical diagnostic scripts are retained for regression
compatibility; they are not automatically invoked or exposed as MCP tools.

## Server wiring and deferred verification

Install `requirements-api.txt` in the standalone server environment. CI installs
both application and API requirements so existing/new tests run together.

Existing environment: `ALPHAOS_API_TOKEN`, `ALPHAOS_PUBLIC_URL`,
`PUBLIC_API_SECRET`, `PUBLIC_ACCOUNT_NUMBER`. New archive wiring reads existing
`SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` environment variables through the
existing client. No secrets were created, read from local secret files, or changed
for development. `ALPHAOS_ARCHIVE_MAX_AGE_SECONDS` defaults to 600 seconds;
set a finite nonnegative value to choose the server's freshness policy. Age is
measured from collection start, not quote time. Invalid configuration fails closed.
After-hours/weekend requests generally have no fresh archive and may return 503;
there is no silent historical fallback or claim of executable quote freshness.

Production wiring is implemented lazily and tested using injected clients. Live
Supabase/Public access, real ChatGPT authorization/tool invocation, deployment,
and operational tuning are deferred. Single-process OAuth grant semantics remain
required. Ledger SQL stays unapplied; conversational journal/position mutations,
backfill and execution remain outside this milestone.


## Deterministic verification

- New API/MCP integration: 27 passed, including QQQ/SPY through actual REST and OAuth MCP, verified fake-storage reads, timestamp/quality preservation, invalid archive failure, capital/expiration delegation, zero-time/$0 constructor arguments, unknown evidence, scenario structure/ordered comparison, safe errors and read-only tool registration.
- Historical API/MCP compatibility: 191 passed, including 49 MCP/auth/protocol tests. Auth assertions are unchanged; tool-list assertions include the new tools.
- Focused rerun after compatibility reconciliation: 64 passed.
- Complete repository suite: 623 passed plus 40 subtests. No production credentials or live service calls required.
- Final-commit GitHub CI is recorded in the draft PR/completion report. Passing deterministic tests does not claim live ChatGPT verification.
