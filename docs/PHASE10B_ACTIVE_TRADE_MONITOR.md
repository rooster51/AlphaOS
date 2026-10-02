# Phase 10B — Active Trade Monitor

## Lineage and scope

Branch `phase10b-active-trade-monitor` starts at deployed Phase 9 index support
`4ef8d5bb1487af1612d8be33cf53f2b2c3be7124`. The previous development branch,
`phase10a-intraday-engine`, ended at `c22366f6237e19a7d88196a1dc5f7f384edad004`
with draft PR #9 intentionally unmerged. Its two commits follow the Phase 9 baseline.
Only the chain-quality changes from `635305a656633c87293ed85e353c2faec9e2fccc`
were copied: service integration, shared option-quality helper, and seven tests.
That isolated baseline passed 452 tests plus 40 subtests before tracking was added.
No historical intraday engine or Phase 10A capability gate was carried forward.

## Architecture

`alphaos_api/positions.py` contains validated entry/close requests, an independent
SQLite store, exact-contract observation and deterministic monitoring. The existing
provider, symbol registry, freshness functions and research engine remain authoritative.
PCS/CCS on SPY, QQQ, SPX (SPXW contracts), and XSP only; multiplier comes from the
registry (100). There are no execution or brokerage-position calls.

Recording requires a user-declared entry and a caller-generated UUID `request_id`.
Retry the same request with the same UUID; changed content returns 409. Expiration,
strike orientation, quantity, finite credit below width and timezone-aware entry time
are validated. New records require currently retrievable, uniquely identified exact
contracts. The selected OCC identity, root, expiration, side and strike are validated;
monitoring must match those stored contract identifiers, never substitute contracts.
Already expired entries cannot be newly recorded via this initial version.

Entry JSON is inserted once and has no update path. It contains the declared economics,
contract identifiers and immutable `entry_snapshot`. Evidence is observed at recording
time, not reconstructed at a backdated execution time. It includes raw quote/leg
observations, timestamps, quality, natural pricing, Greeks where supplied, signed
distances, completed-session structure and unified research/provenance when available.
Unavailable research is explicitly marked; it does not invent evidence or change the
declared entry basis. Entry and snapshot capture times are separate.

Monitoring fetches underlying and exact selected contracts through the existing chain
provider. Full-chain coverage is informational; consumed-leg quality governs valuation.
It never calls the historical provider or reruns analog/option research. If the existing
five-minute completed-history cache is available, it recomputes inexpensive structure
anchored to the observed spot. Otherwise current structure is explicitly unavailable;
frozen entry structure remains visible. Request fresh research through the existing
research tools if needed; this never overwrites entry evidence.

## Economics and descriptors

All quote prices are per share. Natural close debit = short ask minus long bid.
Optional midpoint = (short bid + short ask - long bid - long ask) / 2.
Raw inputs and raw calculated values are retained without clamping. Missing, crossed,
stale, future-dated or out-of-bounds quotes do not produce estimated P/L. Underlying
must also pass the existing live-quote gate. Provider Greeks have no independent
verified freshness guarantee; they are optional reported observations.

* Entry maximum profit = entry credit × multiplier × quantity.
* Entry maximum loss = (width − entry credit) × multiplier × quantity.
* PCS breakeven = short strike − entry credit; CCS = short strike + entry credit.
* Estimated P/L = (entry credit − estimated close debit) × multiplier × quantity.
* Percent maximum profit captured = 100 × (entry credit − close debit) / entry credit.
* Remaining maximum loss exposure = (width − close debit) × multiplier × quantity:
  additional theoretical loss from this quoted valuation to full-width terminal loss,
  distinct from entry maximum loss. No fees or assignment effects are modeled.

These are hypothetical quote valuations, not fills. Closure is explicitly user-declared
with debit/credit amount and timestamp. Credit closure becomes negative signed debit.
Closed records retain original entry JSON and declared P/L; closure is atomic and
identical retries are idempotent, conflicting closure returns 409. Expiration, missing
quotes and process restarts never imply closure.

Rule version `explicit-boundaries-and-buffers-v1`:

* `BOUNDARY_BREACHED`: fresh underlying is at/beyond short, breakeven or long boundary;
  report every reached boundary. PCS uses spot ≤ boundary; CCS uses spot ≥ boundary.
* `UNDER_PRESSURE`: an initially positive short/breakeven buffer has halved (both
  underlying observations live), absolute short delta increased at least 0.10 (both
  snapshots have valid quote quality), or quote quality deteriorated from valid entry
  observations. Report each condition individually; no weighted score.
* `THESIS_INTACT`: none of those conditions and current observations pass quality gates.
  Missing/stale inputs instead yield incomplete assessment, with null state unless
  a separately observable boundary/pressure condition exists. Always retain limitations.

Descriptors are not recommendations or probabilities. Structure is contextual evidence,
not a heuristic pressure trigger. Comparison reports observed spot/value/delta/distance
changes, paired dated structure/quality, credit captured, and elapsed time from both
declared entry and snapshot capture. No historical entry research is recomputed.

## Additive REST and MCP contracts

Existing 14 MCP tools and Phase 9 routes retain their contracts. Five tools are added:

| Tool | REST | Input |
| --- | --- | --- |
| `record_position` | POST `/v1/positions` | `entry`: request_id UUID, symbol, strategy PCS/CCS, expiration, short_strike, long_strike, quantity, entry_credit, entry_timestamp, optional note |
| `get_active_positions` | GET `/v1/positions` | optional symbol; returns all matches and requires_selection when multiple |
| `monitor_position` | GET `/v1/positions/{position_id}/monitor` | explicit position_id UUID |
| `close_position` | POST `/v1/positions/{position_id}/close` | explicit position_id and `closure`: amount, cashflow debit/credit (default debit), timestamp |
| `get_position` | GET `/v1/positions/{position_id}` | explicit position_id UUID, active or closed |

REST bodies are the entry/closure object directly; MCP nests them as named above.
Record/get/close return a position object. Monitor returns `position`, `current_snapshot`,
`entry_vs_current`, `monitoring_state` and `monitor_latency_ms`. List returns `positions`,
`match_count`, `requires_selection`. Errors use the existing sanitized API contract.
Ambiguous requests must list matches and obtain selection; mutation requires an ID.
Record and close have `readOnlyHint=false`, `idempotentHint=true` and
`destructiveHint=false` (records retained); other tools remain read-only.

Authentication remains the existing single-owner boundary. Legacy OAuth scope name
`research:read` is unchanged for compatibility, not a new fine-grained authorization
system. Consent text now explicitly discloses local tracking changes. No token, PKCE,
CIMD, DCR, CSP, security-header or OAuth-persistence behavior was changed. The health
endpoint retains legacy `read_only=true` for market/brokerage access, with additive
`local_position_tracking` and `read_only_scope` fields clarifying local writes.

## Storage and UI

`ALPHAOS_POSITIONS_DB` selects a SQLite file, default `data/active-positions.sqlite3`
(gitignored). Parameterized SQL, unique request IDs, transactional inserts/closure and
separate immutable entry/close JSON support reloads and process restarts. The store
opens only for tracking requests. It is separate from OAuth state and contains user
position data, not credentials. Back up the file using SQLite's backup mechanism.
Initial design is for one owner and one service instance, not multi-tenant storage.

`pages/12_Active_Trades.py` and `modules/active_trades_workspace.py` provide explicit
entry/closure forms, position selection, primary valuation card, Since Entry, Entry
Evidence, Current Context and Data Quality. Refresh is user-triggered. Streamlit calls
the same HTTPS API using server-side `ALPHAOS_PUBLIC_URL` and `ALPHAOS_API_TOKEN` secrets;
no credential widget or separate Streamlit position database. UI timestamps require
explicit timezone, and the displayed refresh capture time prevents silent freshness claims.

## Validation and performance

Tests cover PCS/CCS, quantities, immutable/reloaded entry evidence, close/retry conflicts,
date separation, crossing equality, pressure reasons, stale/missing/crossed quotes,
identity changes, active-list ambiguity, expiry without closure, sanitized authenticated
MCP calls, no brokerage operations, UI checks and Phase 9 compatibility.

Local validation: focused position/OAuth/MCP/chain suite 89 passed, plus five
subsequent UI/economics/latency checks passed (94 focused checks combined).
Complete regression: **486 passed, 40 subtests passed**, 138.19 seconds.

Local deterministic benchmark (Windows, TestClient, mocked provider, October 1, 2026):
entry recording including full research 1306.08 ms; ten monitoring refreshes median
44.60 ms, maximum 48.29 ms; zero historical provider calls during monitoring. This measures
application work and SQLite/API overhead, **not live provider or Render latency**.
Reproduce with `python -m pytest -q -s tests/test_positions.py::test_fixture_latency_profile`.
The response's `monitor_latency_ms` measures live service work after deployment. Remote
chain fetch latency and cold-start overhead remain unmeasured for this undeployed branch.

## Exact recommended merge/deployment sequence — not performed

1. Review this branch's draft PR against `phase9-index-support` (the verified deployed
   baseline). Leave Phase 10A PR #9 unmerged. Confirm CI passes the exact Phase 10B SHA.
2. If releasing through main, first finish/review the existing Phase 9 lineage PRs in
   order; then retarget Phase 10B to that main and rerun CI. Do not merge abandoned 10A.
3. Before deploying tracking, provision a persistent Render disk for the single service
   instance (for example mount `/var/data`) and set
   `ALPHAOS_POSITIONS_DB=/var/data/alphaos/active-positions.sqlite3`. Render's ephemeral
   filesystem/free service is not durable across redeploy/replacement. Migrate any
   existing SQLite file with a consistent backup and verify ownership/permissions.
4. After explicit release approval, merge the reviewed PR, run CI on the resulting SHA,
   and manually deploy that exact passing SHA to Render. Keep auto-deploy disabled until
   the intended release branch is confirmed. Do not deploy this branch automatically.
5. Confirm Render SHA, `/health`, unchanged OAuth metadata, unauthenticated MCP 401, and
   authenticated tools/list with 19 tools and correct mutation annotations. Verify an
   explicitly labeled test record survives a service restart and can be explicitly closed.
6. Configure Streamlit's server token and HTTPS API URL; release the corresponding UI
   SHA. Refresh ChatGPT's tool definitions, verify consent disclosure, record/monitor/get/
   close a user-approved test position and measure real network latency. No broker calls.

Known limits: no automatic settlement/closure, no commissions, no execution verification,
no current intraday-history engine, no expiration-matched probability, optional/missing
Greeks, current structure depends on existing completed-history cache, no automatic
background monitoring, and no live production verification until an approved deployment.
