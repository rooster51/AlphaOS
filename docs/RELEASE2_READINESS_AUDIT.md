# AlphaOS Release 2.0 readiness audit

Audit date: **2026-10-19** (America/New_York). Baseline: latest main fetched at
`aade8038132014e940b5dabce9ce23b46becc786` (Release 1.5C / PR #47).
Scope: SPY and QQQ, Python API, archive collector/storage, OAuth MCP and Next.js.
This branch changes only this report and [the reproducible test matrix](RELEASE2_TEST_MATRIX.md).
No feature, dependency, credential, database, scheduler or deployment change was made.

## Executive summary

**Not ready to represent a broadly available, probability/EV-qualified
multi-strategy options opportunity platform.** There is a useful, deliberately
conservative foundation for dated, read-only quote-supported structure research
and deterministic expiration payoff analysis. Those are narrower capabilities.
The distinction is material, not a request to fill unavailable metrics.

The strongest parts are shared backend contracts, archive identity/checksum
verification, explicit historical mode, deterministic signed-leg payoff/risk,
capital exclusions, authentication and stage-level diagnostics. The primary gaps
are entry-aligned historical evidence, incomplete regime/routing coverage,
execution/liquidity qualification, horizons beyond the short archive window,
MCP connection/schema drift and intermittent live delivery failures.

Live website-to-authenticated-backend probes succeeded after initial failures:
SPY produced two unclassified debit hypotheses; QQQ produced no structures despite
clean selected-expiration quotes. QQQ's observed routes resolved to **zero
supported families**, so construction/capital checks were never attempted.
Increasing capital cannot fix that stage. This is a routing/coverage observation,
not proof that all QQQ quotes or possible structures are invalid. No direction
was inferred or implementation changed to force candidates.

Every observed archive candidate remains research-only. `attach_market_economics`
rejects treating intraday archive entries as completed-session analog entries;
intraday option outcomes/early-exit repricing are unavailable. Historical mode
does not repair this evidence gap. No live POP/EV validation was established.

## Verification labels and evidence boundary

- **CODE VERIFIED (C):** traced current source/imports/contracts or runtime metadata.
- **FIXTURE VERIFIED (F):** executed deterministic offline tests/probes using
  existing fixtures. Some preexisting fixtures explicitly use synthetic demo
  chains; these are software examples, never actual market observations.
- **LIVE VERIFIED (L):** actually executed a dated request or read-only control-plane
  inspection. Limited to the returned result, not a trading recommendation.
- **NOT VERIFIED (NV):** missing evidence, failed/inaccessible request, unsupported
  workflow or unexecuted matrix cell. Never means PASS.

A passing payoff test does not establish quoted availability, liquidity,
expiration listing, forecast calibration, execution quality or broker approval.
Historical frequencies are not calibrated option POP. No old report's production
claim is upgraded to current L status without a request in this audit.

## Verified working capabilities

| Capability | Evidence and limit |
|---|---|
| Shared general research | C/F: `MarketResearchPanel` -> POST `/api/research/market` -> authenticated `/v1/research/market` -> `ArchiveResearchService.run` -> `run_latest_market/run_market`. MCP invokes the same REST handler through ASGI. L: successful website bridge responses carried that backend envelope; direct authenticated REST and live OAuth MCP were not independently verified. |
| Archive integrity | C/F: `supabase_archive.read_latest_option_snapshot` checks latest available row, path, compressed-object SHA-256, provider/symbol/session/slot, observation/creation/completion timestamps and quality consistency. Invalid/missing storage fails closed. L: successful responses exposed verified-reader provenance; this audit did not independently download private objects or inspect database policies. |
| Current/historical separation | C/F/L: current ceiling 600s by default; explicit historical permits age, not corrupt evidence or future availability. Both use the latest snapshot, not a search for a more favorable old archive. Successful requests in both modes preserve observation/request time and report current age ceiling versus historical null ceiling. Off-hours/weekend/holiday behavior is F, not a new L market-closed test. |
| Deterministic structures | C/F: signed legs, 100 multiplier, exact piecewise payoff landmarks, finite-risk checks for supported structures, debit/credit signs, quantities and fees. 22 additional fixture REST cases returned 200 without historical evidence; no live fills implied. |
| Small-account exclusion | C/F/L: capital is an expiration-max-loss ceiling; tested $150/$300/$500/$1,000. Positive risk can exceed budget without corrupting economics. Excluded structures/reasons remain visible. This is not broker margin or cash-balance verification. |
| Honest missing evidence | C/F/L: unknown classifications, zero construction, unavailable historical metrics and non-executable status survive the interface. Stage units distinguish contracts, families and structures. |
| Compatibility/authentication | C/F: 19 OpenAPI operations, 18 authenticated `/v1` operations, 17 read-only OAuth MCP tools retained. L: public backend health/OpenAPI worked; live paths matched local paths exactly. No credentials or secret values were read. |
| Website controls | C/F: SPY/QQQ, editable capital, explicit mode, returned archive expiration list and Run Research; backend-derived economics/exclusions. Market and Strategy Explorer share the renderer. |

## Partially implemented capabilities

- Automatic multi-strategy research: constructors exceed normal classifier/route
  coverage; positive supplied-state fixtures do not establish routine discovery.
- Quote and liquidity qualification: numeric/context gates and warnings exist,
  but executable timing, spread/depth/fill qualification is incomplete.
- Costs/risk: deterministic expiration loss and some fees/friction are implemented;
  public controls and lifecycle/broker-risk coverage differ across contracts.
- Historical research: validated completed-session examples work; entry-aligned
  archive intraday, 0DTE and early-exit economics remain unavailable.
- Interface parity: shared backend results where exposed, but website capability
  coverage is narrower and the live MCP connection/declaration needs verification.
- Operational readiness: fresh snapshots and live deployments observed, but
  intermittent research 502s and continuous collection coverage remain unresolved.

## Pipeline findings and evidence limits

### Collection, chain completeness and provenance

The actual writer is `scripts/run_intraday_snapshot`: NYSE session/slot gate ->
`DailyPublicProvider` raw Public responses -> `intraday_archive.collect_symbol`
and `options_archive.build_options_snapshot/normalize_contract` -> immutable gzip
Storage object plus snapshot metadata. Candles are a separate upsert path.
The collector writes; API/MCP/website research only read. Audit requests did not
invoke collector or storage writes.

Raw per-contract numeric/OSI/context defects are retained in rejected or
questionable buckets. Object upload uses no overwrite; recovery verifies the
existing object's identity. Reader verifies SHA-256 and metadata. This is strong
internal consistency, not independent authentication of provider prices or
proof of a tamper-proof external market feed. Live database/RLS and long-term
retention/restore guarantees are NV.

The configured archive covers **0–7 calendar DTE and a +/-5% strike band**, not
an exhaustive option universe. `quality_status=complete` denotes the collector's
request processing; it does not prove that the provider returned every listed
contract. Metadata received counts, retained bucket counts and selected-expiration
counts have different scopes. Sequential underlying/expiration/symbol requests
are not simultaneous. A full-day uninterrupted five-minute history is NV; fresh
observations prove individual collection successes, not scheduler uptime.

Archive age is collection-start age, not option bid/ask age. Prior-session or
missing underlying timestamps can produce warnings; raw collection does not
force all underlying observations to be current. Missing option timestamps and
questionable rows can remain researchable with limitations. `option_quality`
reports a 900s warning threshold; it is not a universal selected-leg rejection
gate. Canonical chain cleanup rejects invalid/crossed/nonfinite/ambiguous quotes,
but does not establish maximum spread, displayed size, depth, real-time
entitlement, reliable open-interest date or fill feasibility. Do not label this
execution-qualified liquidity.

### Classification, direction, structure and expected moves

`opportunity_classifier` uses completed close/EMA9/21/50 ordering and prior
20-session breakout evidence. Mixed/conflicting evidence stays unknown. This is
lagged daily descriptive bias, not a current intraday signal. Premium richness,
volatility regimes, range-bound, pin and large-move states have no calibrated
classification rules. Router vocabulary is larger than evidence producers.

Legacy `price_structure`, `historical_analogs`, `forward_distribution` and
`threshold_survival` implement S/R, ATR-scaled context, terminal/excursion
quantiles and threshold behavior over completed observed-session horizons
1/2/3/5/10. They are separate context/legacy APIs; the canonical archive page is
not a complete presentation of all of them. S/R is descriptive, not protection.
Expected-move comparison requires a matching explicit observation/expiry interval;
normal archive REST controls do not supply an expected-move feed. IV and realized
volatility alone do not become a calibrated expected move or rich/cheap regime.

Normal known direction with unknown premium can route debit spreads. Known
breakout direction can reach long options. Late-0DTE time routes can reach premium
structures. Constructor support with supplied rich/range/volatility fixture state
must not be advertised as routine classifier-generated opportunity coverage.
When there are no routes, existing call/put debit hypotheses may be tested as
`unclassified_quote_research`. A nonempty route list resolving to no supported
families does **not** get that fallback. The observed QQQ case is this latter path.

### Economics, fees, probability and holding horizon

Payoff/maximum loss/breakevens are deterministic expiration calculations, not
complete trade lifecycle economics. Long discovery uses ask; debit discovery uses
midpoint debit rounded to cents and can use nearest available rather than exact
requested width; actual legs/risk govern. Premium constructors use natural
bid/ask with $0.65 per contract. Long/debit defaults and explicit fees differ;
there is no common calibrated slippage/liquidity cost schedule in the archive API.
The website does not expose commission/slippage sensitivity controls.

Legacy explicit vertical APIs support commission, entry slippage and terminal
friction, and share their validated workflow after 1.5C. The canonical explicit
structure API accepts total fees, not an equivalent public slippage interface.
`historical_economics` can model package slippage internally; it does not prove
observed transaction costs. Assignment, early exercise, dividends, settlement,
broker approval and margin/cash timing are not comprehensive risk outputs.

Trusted completed-session scenarios require matching symbol/spot, verified
archive provenance, matured outcomes, an NYSE-matched supported session horizon
and minimum sample coverage. Positive F examples exist. Daily analog selection
is feature/date based, with future labels excluded from membership and mature
outcomes checked; overlap/non-overlap diagnostics and sample warnings exist.
Neither nearest-neighbor matching nor sample minimums establish out-of-sample
calibration. History adjustment/coverage limitations remain documented.

For **regular-session archive candidates**, `attach_market_economics` passes the
actual intraday observation to the completed-session gate. This systematically
leaves entry-aligned historical scenarios unavailable; it is not a sporadic UI
serialization defect. Early-exit marks and intraday option-outcome samples are
missing. 0DTE cannot be made valid by substituting a one-session distribution.
Monthly/LEAPS are holding labels in an evaluator, not evidence coverage: supported
session horizons remain 1/2/3/5/10. Touch statistics based on daily high/low describe
underlying threshold excursions, not option POP, path ordering or intraday option
P&L. Long-range, multi-expiry repricing and calibrated POP are missing.

## Missing capabilities

No supported multi-expiry calendar/diagonal valuation workflow; no canonical long
straddle/strangle research adapter/discovery; no verified archive coverage beyond
7 DTE; no complete intraday option-outcome or early-exit repricing dataset; no
calibrated POP/forecast validation; no established premium-richness/volatility/
range/pin/large-move classifier; no independently verified liquidity/fill or
broker-buying-power integration. Website explicit structure/compare forms and
full context/horizon exploration are absent. These omissions are not authorization
to implement them or substitutes for the evidence gates.

## Strategy-by-strategy matrix

A = payoff math; B = explicit canonical structure research; C = automatic discovery;
D = quote/evidence enforcement; E = risk/reward/friction completeness;
F = historical probability/EV defensibility; G = interface accessibility.
“Partial” is deliberately not “fully working.” Rows apply to SPY and QQQ.

| Strategy | A | B | C | D | E | F | G |
|---|---|---|---|---|---|---|---|
| Long call | C/F yes, unlimited upside preserved | C/F yes | C/F constructor; normal route conditional on evidence (e.g. directional breakout), not every market | Ask/finite/identity gates; liquidity/timing partial | Expiration premium/risk/fees yes; real costs/early exit partial | F completed-session scenarios possible; archive intraday EV unavailable; no calibrated POP | Explicit REST/MCP; website only returned archive candidates, no entry form; live candidate NV |
| Long put | C/F yes | C/F yes | Same conditional limitation | Same | Same; finite underlying-zero payoff | Same | Same |
| Call debit spread | C/F yes | C/F yes | C/F yes; routed or explicit unclassified hypothesis | Observed delta, unique quotes, geometry/debit checks; midpoint not fill | Finite loss/width yes; fees/slippage policy partial | Same intraday limitation | REST/MCP/code parity F; L website backend candidate where matrix succeeded |
| Put debit spread | C/F yes | C/F yes | Same | Same | Same | Same | Same |
| Put credit spread | C/F yes | C/F yes | C/F premium constructor; normal regime coverage limited, late-0DTE route possible | Natural bid/ask, protective legs, positive credit after fees; liquidity partial | Width/max loss/fees yes; execution/assignment partial | F same-expiry scenarios; archive intraday NV/unavailable | Legacy exact/scan + canonical REST/MCP; website conditional output; L candidate NV |
| Call credit spread | C/F yes | C/F yes | Same | Same | Same | Same | Same |
| Symmetric long call/put butterfly | C/F yes | C/F yes | **No automatic standard long butterfly** | Explicit signed inputs need not be quotes; missing provenance stays missing | Expiration roots/ratios/fees yes; liquidity/friction partial | F supported scenarios; live calibrated evidence NV | Explicit REST/MCP; website no explicit form, not automatic |
| Iron butterfly | C/F yes; normalized family `butterfly` | C/F yes | C/F existing premium constructor, conditional routes | Four valid legs/natural credit/fees; no execution proof | Expiration risk yes, lifecycle partial | As above | REST/MCP; conditional website output; L NV |
| Put bullish BWB | C/F supported 1:-2:1 orientation | C/F yes | C/F conditional existing constructor | Actual unequal wings/quotes and positive finite economics; liquidity partial | Ratio counts/unequal loss tails/fees yes; lifecycle partial | F scenario math; archive intraday unavailable | REST/MCP; conditional website output; L NV |
| Call bearish BWB | C/F corresponding orientation | C/F yes | Same | Same | Same | Same | Same |
| Iron condor | C/F yes, unequal wings supported explicitly | C/F yes | C/F premium constructor; neutral/volatility classifiers incomplete, late route possible | Credit/leg ordering/quotes/finite payoff; liquidity partial | Actual widest-wing risk/fees yes; lifecycle partial | F scenarios; no archive intraday EV | REST/MCP; conditional website output; L NV |
| Calendar | **No multi-expiry valuation** | No; same-expiry contract | Router name only; no supported factory | Mixed expiry rejected | Incomplete: surviving-leg value absent | NV | Unavailable as a supported canonical strategy |
| Diagonal | Same | No | Router names only | Same | Same | NV | Same |
| Long straddle | Generic same-expiry payoff math C; not a supported research family | Rejected by family adapter | Route name without constructor | No complete canonical contract | Generic payoff is not lifecycle support | NV | Python payoff only; no canonical REST/MCP/website strategy support |
| Long strangle | Same | Rejected | Same | Same | Same | NV | Same |
| Short straddle/strangle | Generic payoff + legacy premium constructor C; unbounded risks possible | Canonical family adapter rejects | Legacy-only generator; excluded from canonical supported map | Legacy numeric/natural-credit checks, not full risk qualification | Not complete for platform use | NV | Legacy Python/Streamlit context, not canonical strategy support |
| Covered call/covered strangle, cash-secured/short put, naked short call, call/put ratio spread | Present in generic payoff/legacy premium catalog C/F where existing tests exercise it | Canonical option-only/family restrictions reject these forms | Some legacy constructors; not canonical allowed map | Portfolio collateral and suitability not verified | Generic stock/option payoff only; naked tails may be unlimited | NV | Retained legacy code, not claimed as supported SPY/QQQ platform workflows |

A branch in `ROUTE_MATRIX`, a strategy catalog label or a holding-period enum is
not evidence of B/C/F/G support. The matrix is intentionally stricter than a
count of names in the repository.

## Expiration-by-strategy coverage

The detailed SPY/QQQ per-expiration/budget results and fixture dates are in
[RELEASE2_TEST_MATRIX.md](RELEASE2_TEST_MATRIX.md). The live archive reported
October **19, 20, 21, 22, 23 and 26, 2026** for both symbols: 0, 1, 2, 3, 4 and 7
calendar DTE on the audit date. No other listing was invented.

| Family / pathway (SPY and QQQ separately tested where noted) | 0DTE | 1DTE | 2–7 DTE | 8–45 DTE | Monthly | LEAPS |
|---|---|---|---|---|---|---|
| Call/put debit archive discovery | L successful SPY cells; QQQ L zero; failed cells NV | Same distinction | Same; only returned Oct 21/22/23/26 tested | NV: outside configured archive | NV live: no monthly returned | NV |
| Long calls/puts | F same-expiry math/conditional constructors; L candidates NV | F explicit QQQ 2030-01-18 example; L candidates NV | F explicit SPY/QQQ 2026-10-16 examples; L candidates NV | F selected legacy 30-day examples, not evidence coverage | F dated payoff/scenario example only; no live listing claim | NV; enum is not a test |
| Credit verticals / iron butterfly / BWB / condor | F conditional late/session constructors; L candidates NV | F selected explicit structure cases; not full discovery grid | F supported-family scenario cases; L candidates NV | F selected 30-day structures only | F supported math at Oct 16 fixture, no actual monthly-chain verification | NV |
| Symmetric long butterfly | F math only where matching fixtures; auto unsupported | F explicit | F explicit | F supplied 30-day case | F payoff example only | NV |
| Calendars/diagonals | Unsupported canonical pathway C; no L claim | Same | Same | Same | Same | Same |
| Long straddle/strangle | Generic payoff C only; full pathway NV | Same | Same | Same | Same | Same |
| Legacy catalog-only structures | Not canonical; L NV | Same | Same | Same | Same | Same |

This is **not** a rectangular all-strategy PASS: unexecuted family/date combinations
are NV. Fixture selection is explicitly enumerated in the test document. 8–45
DTE, monthly and LEAPS require actual archive/evidence support before acceptance,
not simply wider UI dropdowns. Calendar DTE and observed-session horizon differ.

## Small-account findings

Additional deterministic checks reused the 11 structure cases in
`tests/test_historical_economics.py` for each symbol (22 REST cases, 88 capital
comparisons). The supplied scenario is spot 100, expiration 2026-10-16, as_of
2026-10-09, with $1 total fee. These are **F examples, not current SPY/QQQ prices**.

| Existing fixture structure | Maximum loss incl. $1 fee | $150 | $300 | $500 | $1,000 |
|---|---:|---|---|---|---|
| Long call / long put | $201 | Ineligible | Within loss budget | Within | Within |
| Call / put $5 debit vertical | $201 | Ineligible | Within | Within | Within |
| Put / call $5 credit vertical | $301 | Ineligible | Ineligible | Within | Within |
| Call / put symmetric butterfly | $101 | Within | Within | Within | Within |
| Call / put BWB, wider wing $10 | $401 | Ineligible | Ineligible | Within | Within |
| Equal-wing iron condor | $301 | Ineligible | Ineligible | Within | Within |

That a butterfly fixture costs $101 does not establish a $150 executable
opportunity. Four-leg or ratio structures have more contracts/cost exposure.
Actual spread width, signed quantities and fees matter; requested width may be a
target in debit discovery. Broker margin, settled cash, assignment liquidity,
commissions at the user's broker and fill uncertainty remain NV.

Live successful SPY cells demonstrate actual capital exclusions, while QQQ's
observed zero occurred before capital. Results across requests are not controlled
price experiments: archives and quotes can advance. Only matching checksum/legs
permit a same-evidence capital comparison. No budget or evidence gate was relaxed.

## Website / MCP experience and parity

- **C/F:** Market Research and Strategy Explorer are the same archive workflow,
  not two independent engines. Capital/mode/expiration controls submit on Run.
  Expiration choices come from returned archive diagnostics; no manual fabricated
  date list. Excluded but researched structures can be displayed alongside accepted
  ones, with evidence-only and capital status distinguished.
- **C/F:** Candidate output preserves legs, side, quantity, actual strikes/expiration,
  entry cashflow, maximum loss/profit, provenance, timestamps and diagnostic counts.
  Some details are under collapsible evidence/constructor/outcome sections, but
  each candidate is a large expanded `<article>`. A compact per-candidate summary
  with an accessible expandable detail section is a reasonable UX milestone;
  collapse must never hide exclusion or non-executable status.
- **Partial:** No explicit multi-leg research/compare form, commission/slippage
  controls, common horizon/expected-move control, strategy selector, full analog
  distribution exploration or integrated S/R view on this canonical page. Changing
  objective/strategy labels must not substitute for evidence-based classification.
- **C/F:** Dashboard uses paired legacy market/structure context. It correctly says
  balances, P&L, guardrail enforcement and journal/account integration are unavailable.
  These are not missing fields to fill with examples. Live dashboard content NV;
  navigation/fail-closed behavior F.
- **C/F:** MCP has broader explicit structure/compare and legacy context/research
  capabilities than the website. Both share backend economics where exposed;
  identical capability coverage is **not** present. All 17 tools remain in local
  runtime metadata and fixture OAuth tests.
- **L failure:** Connected AlphaOS `run_market` returned connector `UNAUTHORIZED`
  for both symbols; no live OAuth research result. Its tool declaration lacks
  `research_mode`, although source/backend/website support it. This is an observed
  connection/declaration discrepancy; whether reconnect refreshes it is NV.
- **F:** Existing parity tests compare REST-generated envelopes through OAuth MCP
  and website bridge fixtures. Successful L website research reaches authenticated
  backend REST, but that does not prove direct REST/OAuth MCP equality in production.
- Warnings are honest but repetitive. “Buying power” means max-loss budget here,
  not account buying power. “Current” means strict-age archived observation, not
  executable live option quotes. Availability summaries should distinguish
  constructor availability, classifier reachability, capital and evidence eligibility.

## Operations and live boundary

Read-only Render inspection confirmed both user-facing services manually deployed
to the audited `aade8038...` commit; auto-deploy off, one free instance each,
Virginia. API: `pip install -r requirements-api.txt`, `python -m alphaos_api`,
`/health`. Website: `cd web && npm ci && npm run build`, `cd web && npm start`;
configured Render HTTP health path empty. Retained API staging is Oregon,
`release/release1-consolidation`, live `15dc5683...`, not the current release.
The old staging Blueprint branch/86400s ceiling still differs from audited service
metadata; neither was changed. Older deployment docs are dated, not current state.

L public `/health` 200 and `/openapi.json` 200 establish process/contract reachability,
not archive freshness or research success. L website requests intermittently
returned HTTP 502 `backend_service_unavailable`, including in the matrix after
successful health. The exact upstream status/root cause, resource pressure and
cold-start contribution were **not confirmed**; no logs/secrets were inspected.
A Render `live` deployment is not an end-to-end research availability guarantee.
See [Render deployment](https://render.com/docs/deploys) and
[health-check semantics](https://render.com/docs/health-checks).

Collector workflow has dispatch only, external scheduler dependency, five-minute
slots, serialized concurrency, finite retries and a 720s process limit inside a
15-minute job. Pending dispatch replacement and long symbol/expiration collection
can miss slots; no backfill pretends to observe the past. Scheduler current
configuration, token expiry, daily coverage and alert delivery are NV. Collector
proof should include per-symbol slot coverage and stale-age/partial-archive alerts,
not dispatch HTTP success. Process health is intentionally not evidence health.

Dependency risks remain from 1.5C: no isolated API/UI/collector installs verified;
test environment Supabase 2.31.0 differs from collector pin 2.32.0; broad ranges and
transitive direct imports need isolation checks before changes. Python tests used
3.12.14; devcontainer still 3.11. Website validated on local Node 24.20.0, not CI's
Node 22. React 18 deprecation/module-type warnings and reviewed audit exceptions
remain. No dependencies were upgraded and no runtime settings were inspected for
secret values. Observability covers protocol sanitization and research-stage
counts, not proven collection/data-quality SLOs, quote-age alerts or execution data.

## Top 10 prioritized gaps

Effort: S = a few focused changes; M = cross-layer work plus evidence tests;
L = new validated data/evaluation capability. Estimates are relative, not schedules.

| Priority | Gap / evidence | Impact | Effort |
|---:|---|---|---|
| 1 | Intermittent L research 502s and no confirmed upstream cause | Working research cannot be relied on; health alone misses it | M |
| 2 | Intraday archive candidates have no entry-aligned historical EV/early-exit sample | Prevents defensible probability/EV-qualified candidate claims | L |
| 3 | Nonempty routes can resolve to zero constructors (L QQQ); “no constructible structure” conflates unreached construction | Valid quote research can stop before economics; users misread reason | M |
| 4 | Premium/volatility/range/pin classifications unavailable | Broad router/catalog does not translate into broad automatic discovery | L |
| 5 | Quote timestamps/liquidity/spread/fill and consistent friction qualification incomplete | Especially material for $150–$1,000 and 0DTE/ratio structures | M–L |
| 6 | Archive limited to 0–7 DTE / strike band; monthly/LEAPS and mixed-expiry valuation absent | Cannot claim broad expiration or calendar/diagonal coverage | L |
| 7 | Live MCP connection expired and declaration missing historical-mode control | Live MCP/website parity not established | S–M |
| 8 | Website lacks explicit structure/compare UI and compact candidate controls | Backend research capabilities inaccessible or cumbersome | M |
| 9 | Collection coverage/SLO/partial snapshot observability and external scheduler status unverified | Freshness gaps may silently reduce available evidence | M |
| 10 | Isolated dependencies, Node/Python alignment and stale staging drift unverified | Green combined-env tests do not prove independent deployability | M |

Do not treat a lack of calibrated POP as permission to publish uncalibrated POP.
Do not add ranking before candidate/evidence eligibility is clear.

## Proposed Release 2.0 milestones and acceptance criteria

**First development milestone: M1 — Reliable, evidence-qualified research delivery.**
Keep current strategy/expiry scope. Diagnose intermittent website-to-backend
failures with sanitized correlation/status/timing evidence; distinguish process,
archive and research health. Characterize route-to-supported-family gaps using
observed/frozen evidence; report “not attempted / unsupported route evidence”
separately from invalid geometry. Resolve connection/schema parity through the
normal authorized OAuth flow, without weakening auth or inventing state.

Acceptance: SPY/QQQ current/historical controlled fixture parity; repeatable live
probes at all four budgets with failures reported; successful reconnect exposes
historical mode or records a connector limitation; every zero has the correct
reached-stage reason; no synthetic production candidates, relaxed quote/freshness
gate or implied live execution. Define a bounded operational observation window
and failure budget before claiming reliability. Live observations are not a
forecast backtest.

**M2 — Explicit evidence and transaction-cost contract.** Define separate
expiration-payoff, historical-frequency and execution/holding eligibility. Include
actual consumed-leg timestamp coverage, spread/quantity/OI limitations and total
fees/slippage assumptions. Acceptance: all supported families retain deterministic
results; absent evidence remains unavailable; capital edge tests include costs,
ratio quantities and actual width; no broker-buying-power assertion.

**M3 — Validated entry/horizon research dataset.** Choose a documented entry and
holding policy, acquire/verify the required option/underlying outcomes and prove
maturity/alignment. Acceptance: no close-to-close substitution for intraday entry,
0DTE/early-exit marks handled explicitly, sample/overlap/temporal holdout diagnostics,
reproducible data lineage and no calibrated-POP claim without calibration evidence.
A completed-session-only policy is acceptable if clearly scoped and supported;
new research semantics need separate authorization.

**M4 — Website research coverage and presentation.** Accessible candidate summaries
and expandable detail, explicit supported-structure/compare forms and cost/horizon
controls only for existing backend contracts. Acceptance: REST/MCP/website fixture
parity, mobile/keyboard browser tests, persistent non-executable/exclusion warnings,
no frontend pricing or ranking.

**M5 — Incremental strategy/expiration expansion after evidence gates.** Select one
family/horizon at a time, beginning with already-supported explicit same-expiry
structures. Acceptance: real listed expiration/chain coverage, quality and risk
fixtures, live supported-state probes and relevant evidence/valuation. Calendars,
diagonals, straddles/strangles, monthly and LEAPS each require their own B–G proof;
router/catalog names do not satisfy it. Ranking is a later separate decision.

**Parallel operational prerequisite:** complete Release 1.5D isolated dependency
and deployment-consistency checks without mixing that migration into research
feature work. No implementation of any milestone is authorized by this audit.
