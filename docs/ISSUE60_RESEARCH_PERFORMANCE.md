# Issue #60: bound research work and response cost

Incident: [GitHub Issue #60](https://github.com/rooster51/AlphaOS/issues/60).

Baseline: main `dd1196b`, including PR #59. No deployment or production success
claim accompanies this change. **Milestone 1 production cold-start acceptance
remains open.** The website deadline is still 12,000 ms.

Post-merge production validation of PR #61 still exceeded that deadline. See
[the reliability follow-up](ISSUE60_RELIABILITY_FOLLOWUP.md) for the newer
correlated traces, after-close freshness audit and further measured changes.

## Production evidence, correlated rather than summed

Read-only Render app/website logs were retrieved for 2026-10-21 18:18:50–18:22:30
UTC, with a follow-up through 19:05. Four backend executions overlapped.

| Request ID | Symbol | Website | Archive read | History load | History features | Candidate pipeline |
| --- | --- | --- | --- | --- | --- | --- |
| `169ffa23f4f24e7fa25f1aff9eb35927` | SPY | 502 at 12,001 ms | 7,196 ms | 9,604 ms | 6,398 ms | Started at elapsed 23,799 ms; no completion found |
| `8f0cdb01eef14b3fa4dc219fc6f9b05a` | QQQ | 502 at 12,001 ms | 7,702 ms | 6,696 ms | 4,803 ms | Started at elapsed 20,194 ms; no completion found |
| `9ade20211d8a4e15a5fc9747f0ac51e8` | SPY | 502 at 12,001 ms | 2,231 ms | 3,986 ms | 1,102 ms | 56,404 ms, including 25,112 ms historical economics |
| `06169905aa1d425fbc225699aca9a2e0` | QQQ | 502 at 12,003 ms | 2,505 ms | 4,398 ms | 1,493 ms | 55,704 ms, including 23,709 ms historical economics |

The named pair's archive downloads took 4,606/4,527 ms. Public provider-request
spans were 6,100 ms SPY and 792 ms QQQ; total history loading was much longer for
QQQ. These wall spans include scheduling/contention and are not pure remote
server latency. Even SPY's checksum took 193 ms under load. A backend start
message appears at 18:20:36, without complete traces for the named pair; the logs
alone do **not** establish the reason for that restart. There were no correlated
successful response-completion records in the retrieved incident window.

Stages overlap across requests; parent stages contain child stages. Do not add
these columns or attribute archive/provider delays entirely to width enumeration.

## Reproduction and measured cause

The committed fixture has 810 synthetic option observations: five expirations,
81 observed strikes per side/expiration, and 1,260 daily OHLC rows per symbol.
It exercises the real archive metadata/identity/freshness/checksum/decompression
reader, classifier, constructors, exact payoff engine, historical annotations,
REST serialization and negotiated compression. Four requests are SPY, QQQ, SPY,
QQQ with $150 capital. Archive/history waits are fixed **20 ms fixture waits**,
not measurements or simulations of actual provider latency. No live market data
or production credentials are used.

The original pipeline exceeded 12 seconds locally even with this fast fixture
I/O. Auto Width amplified pre-existing per-candidate work and response copying:

* Every discovered structure, including capital exclusions, materialized dense
  chart samples in addition to exact analytical economics.
* Historical annotation validated accepted structures again, rebuilt chart
  grids it discarded, then called the same analytical engine again. Intraday
  entries still lacked aligned historical evidence, so this was not expensive
  analog selection or a per-candidate provider/database fetch.
* Session JSON conversion, envelope conversion, legacy JSON conversion and
  credential redaction repeatedly traversed/copied the large graph before JSON
  encoding. More simultaneous requests magnified GIL/CPU and allocation pressure.
* Website departure did not stop a sync worker's later candidate processing.

A separate profiled late-session baseline produced 4,915 packages, accepted
1,164, and an approximately 184.8 MB JSON envelope for **one** request. With
cProfile overhead it took 38.3 seconds: width enumeration itself took only
84 ms; `research_position` ran 6,079 times, chart scenarios 794,571 times, and
the analytical engine 7,243 times. Session/envelope JSON traversals alone had
cumulative times of 12.0/11.0 seconds. These nested profile times must not be
summed or presented as unprofiled latency. Four copies of that late baseline
were not attempted because of the memory cost.

## Changes and preserved controls

1. Discovery payoff grids contain exact spot, strikes, breakevens and adjacent
   midpoints, explicitly marked `grid_sampling=exact_landmarks_and_midpoints`.
   Existing extreme scenarios remain. The exact piecewise-linear kink/tail
   calculation still determines every maximum loss/profit and breakeven **before
   capital screening**. Explicit structure/legacy research retains its full
   adaptive grid. No quotes or economic summary fields are removed.
2. Historical validation still validates the actual trade, quantities, fees,
   multipliers, expiration and supported family through the shared researcher.
   Its intermediate chart is not materialized, and the just-computed exact
   payoff result is reused instead of invoking the analytical engine again.
   Caller-cached economics are never trusted. Missing aligned history/EV/POP,
   robustness and execution evidence remain unavailable and fail closed.
3. REST discovery defers redundant intermediate JSON copies to one final
   normalization/redaction pass. Direct Python callers retain JSON-ready output
   by default. Legacy numpy/pandas/date conversion and credential filtering
   remain covered, including numeric/string enums and nonfinite values.
4. POST market responses negotiate low-cost gzip and `Vary: Accept-Encoding`.
   Uncompressed clients receive the same JSON. MCP/SSE and other paths bypass
   this middleware. Client decoding/schema validation still happens within the
   existing website deadline; no early-success response or timeout extension
   hides incomplete work.
5. Constructor search now shares **1,024 geometry/quote attempts per request**
   fairly across routed families (integer shares, deterministic remainder), with
   the existing 1,024 per-family ceiling, 80-contract side cap and 100-point wing
   bound. This prevents late-session overlapping routes multiplying the budget.
   BWB search begins at observed OTM bodies nearest spot and visits multiple
   inner/outer widths. No capital-based pruning or post-constructor shortlist is
   introduced. All generated packages reach exact economics. New bounds and each
   family's allocation are returned in construction diagnostics.
6. After FastAPI consumes/validates the body, the handler observes disconnects
   and sets a request-local cancellation event. Cooperative checkpoints stop
   later work at I/O/stage and enumeration/payoff boundaries. Observed departure
   returns a quiet empty 499, avoiding a misleading internal 500; task
   cancellation remains cancellation. A blocking SDK call cannot be killed: it
   retains its existing timeout, and subsequent work stops when it returns.
   Cancellation does not cancel another symbol's request or shared client.

No providers, subscriptions, infrastructure, secrets, deployed configuration,
quote gates, archive checksums/freshness, expiration matching or strategy routes
change. Archive selection and verification still happen on every request before
history loading; there is no new market-data/result cache or fallback.

The shared budget is an **explicit coverage tradeoff**: multi-family late
searches can return fewer structures than PR #59. `search_truncated`, applied
bounds, `max_attempts_per_family`, `max_total_attempts` and the actual allocated
`max_attempts` expose it. Existing website partial-search warnings remain active.
An empty partial search is `bounded_search_incomplete`, never proof that all
possible structures exceed capital. Manual widths remain exact; unavailable
strikes or expirations are never substituted. Single-family search retains its
original domain and candidate count.

## Before/after fixture measurements

Same Windows/Python environment and helper files; baseline code was extracted
from `dd1196b`. First and second rounds mean cold/warm **fixture process/calendar
state**, not a Render cold boot or cold provider connection. Per-request wall
time includes the real ASGI response and client JSON decoding. Batch CPU/RSS
also include fixture clients, decoding and economic-fingerprint comparison;
these are not exclusive backend CPU or production memory measurements.

| Four-request case | Before per-request seconds | After per-request seconds | Generated / capital eligible, per request |
| --- | --- | --- | --- |
| Auto, first round | 20.411–23.696 | 5.248–7.162 | 1,024 / 105, unchanged |
| Auto, warm round | 17.039–20.110 | 5.448–7.157 | 1,024 / 105, unchanged |
| Manual five, first round | 1.574–1.675 | 0.847–0.967 | 70 / 0, unchanged |
| Auto monthly | Not separately measured | 2.988–3.934 | 1,024 / 105 |
| Auto long-dated | Not separately measured | 4.915–6.129 | 1,024 / 105 |
| Auto late-session overlap | No four-request baseline | 5.026–7.295 | 892 / 119, explicitly partial shared-budget search |

For Auto first/warm rounds, batch process CPU dropped from 24.359/20.547 seconds
to 8.547/7.953 seconds. Measured process peak working set dropped from 639 MiB
to 304.5/363.7 MiB. Per-request negotiated wire bytes dropped from 22,688,333 to
about 768,023; decoded JSON is about 12.0 MB and still contains full quotes and
economics for accepted/excluded structures. Manual wire size dropped from about
1.10 MB to 48 KB. Single-family economic fingerprints match main exactly after
excluding chart presentation and added budget metadata. Full-grid versus compact
math/quote equality is also tested across all affected strategy families.

Monthly/long-dated measurements preceded the shared-budget refinement; those
cases route one constructor family and retain the same domain. Raw numeric
measurements, runtime metadata and caveats are in
[issue60-fixture-benchmarks.json](performance/issue60-fixture-benchmarks.json).
Reproduce with `python -m tests.benchmark_research_pipeline --rounds 2`, adding
`--width 5`, `--expiration 2030-01-18`, `--expiration 2031-01-17` or `--late`.
Run the same two helper files in the baseline tree for a baseline comparison;
do not accidentally import the newer production modules there.

## Validation and production acceptance

Regression tests exercise four simultaneous SPY/QQQ requests, cold/warm fixture
rounds, $150 Auto/Manual, monthly and long expirations, exact math/quotes across
nine structure shapes, shared-budget diagnostics, fractional-budget rejection,
stale/missing/corrupt archives, redaction/conversion parity, task cancellation
and observed disconnect without cancelling a peer. Performance fixtures enforce
10.5-second local request completion to leave headroom below the unchanged
12-second bridge. Existing REST/OAuth MCP and website/browser fixtures are
regenerated through the actual REST boundary. Final local validation on
2026-10-21: **1,119 Python tests plus 64 subtests passed** in 417.68 seconds,
with four existing Supabase SDK deprecation warnings; **90 website tests**,
**27 Chromium browser tests**, TypeScript typecheck and production build passed.

After approval and deployment, capture fresh correlated IDs for cold first,
warm, simultaneous SPY/QQQ, and four-request retry/overlap tests in current mode,
including late-session and monthly/long dates actually present in the archive.
Require complete backend execution, new width/payoff/comparison subspans,
serialization, website body/schema validation and final request records, with
both website results below 12 seconds and useful headroom. Confirm exact expiry,
$150 capital, partial-search warnings and all evidence limitations. Separately
abort a request and verify a cancelled worker stops after its blocking call,
while its peer succeeds. Never use historical mode to pass current-mode timing.

Real provider/network waits, first imports/calendar startup, CPU throttling and
blocking SDK calls remain production limitations. This PR removes measured
compute/response amplification and orphaned later work; it cannot establish a
production SLA from fixture I/O or explain a restart without further evidence.
No merge or deployment has been performed.
