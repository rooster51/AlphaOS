# Issue #60: reliability follow-up to PR #61

Base: merged PR #61, `8a374fbd`. Milestone 1 production acceptance remains **open**.
This change is not deployed. Fixture results below are not production acceptance.

Post-merge traces still narrowly exceeded complete website response deadlines.
See [the dashboard contract follow-up](ISSUE60_DASHBOARD_CONTRACT.md) for the newer
evidence, additive observation-only contract and serialization measurements.

## Confirmed production evidence

Read-only Render logs from 2026-10-21 were retrieved in full for all four supplied
IDs, with no additional pages. The timing records are in
[`performance/issue60-followup-production-traces.json`](performance/issue60-followup-production-traces.json).

| Symbol/mode | Correlated request ID | Website | Backend |
|---|---|---|---|
| SPY current | `dadc4090784d4246a7d6022ba79de26f` | 2,301 ms, `archive_stale` | 1,764 ms, 503 |
| QQQ current | `7a034429fc8a4b028c76150522a0abe4` | 2,201 ms, `archive_stale` | 1,374 ms, 503 |
| SPY historical | `33882cdf844f4f7abcc4de23c435a801` | 12,008 ms, timeout | 16,987 ms, disconnected |
| QQQ historical | `faab29f15b8e41bd9f7a851a7ebf1a3f` | 12,004 ms, timeout | 19,494 ms, disconnected |

Historical stage durations (ms):

| Stage | SPY | QQQ |
|---|---:|---:|
| Archive read, including verification | 685 | 685 |
| Daily history load | 4,200 | 4,807 |
| Archive normalization | 1,707 | 902 |
| Session calendar | 1,499 | 1,504 |
| History features | 1,498 | 1,291 |
| Width enumeration | 101 | 196 |
| Candidate/payoff research | 903 | 2,188 |
| Candidate comparison | 3 | 904 |
| Historical economics | 995 | 3,503 |
| Response serialization | 2,094 | 3,115 |

Stages nest and requests overlap: do not sum these rows. Cold import, calendar
coverage labeling, compression, scheduling and transport also contribute to the
request total. History's measured provider HTTP requests were only 399/720 ms;
the rest of history loading cannot be attributed entirely to network latency.
New import/schema/coverage spans make that residual observable in future logs.

The backend observed disconnects at 12,785/12,586 ms but still finished economics
and serialized success responses. The outer ASGI observer logged disconnects
without setting the route's cancellation event; inner polling could miss an event
consumed by middleware. This is reproduced and fixed through the full middleware
stack, without mocking `Request.is_disconnected`.

Local profiling confirms redundant NYSE holiday initialization across date ranges,
unused classifier indicators and repeated OHLC validation, duplicate candidate
deep copies, repeated historical payoff research, and unnecessary chart/quote
aliases in discovery output. Width enumeration itself is comparatively small.
CPU contention on production is plausible, not proven by these timings. Read-only
Render metrics report a 0.15 CPU limit; minute samples do not establish per-request
saturation. Local workstation timings do not reproduce that resource allocation.

## Collection and freshness audit

The external scheduler invokes `.github/workflows/intraday-archive.yml`; native
GitHub cron is intentionally disabled. No scheduler or infrastructure was changed.
GitHub Actions run history and read-only `option_snapshots` queries showed:

| Session | SPY complete snapshots | QQQ complete snapshots |
|---|---:|---:|
| October 19 | 78 | 78 |
| October 20 | 76 | 76 |
| October 21 | 78 | 78 |

All 78 five-minute slots were present on October 21. Last observations were
19:56:01.450845Z (SPY, 2,814 contracts) and 19:56:06.441752Z (QQQ, 2,994 contracts),
uploaded at 19:56:04.676313Z / 19:56:09.270664Z. Both were complete, labeled with
the correct October 21 session and 19:55Z slot. Historical reads verified their
checksums and payload identities successfully.

At 21:01Z (5:01 p.m. New York), these observations were about 3,899/3,894 seconds
old. The NYSE regular session had ended at 20:00Z. Rejecting them under the existing
600-second current limit was correct, not an archive access failure or a timestamp
bug. The [21:01 collection run](https://github.com/rooster51/AlphaOS/actions/runs/39675313787)
correctly logged that the regular session was closed. Later dispatches were also
successful no-ops. No evidence points to an October 21 provider/collection outage.

October 20 had missing 14:05Z and 17:05Z slots. The
[17:05 dispatch](https://github.com/rooster51/AlphaOS/actions/runs/39463006462)
actually collected at 17:10:51Z/17:10:53Z and correctly used the later slot;
GitHub runner/dispatch delay can therefore create gaps. The first gap's exact
cause is unverified. These gaps do not explain the October 21 after-close failures.
Monitor scheduled run start delay, failures and per-symbol slot coverage; repair
an external scheduler/runner problem only if a fresh audit establishes one.

Current requests still fail closed after freshness expires. To validate current
research, test during an open NYSE session after a successful collection. Outside
that interval use separately labeled historical research; making current data
available after hours would require new observed evidence, not a freshness bypass.
Website stale/missing/unverifiable codes remain distinct. The dashboard's existing
separate historical request retains the stale-current warning, observation time
and historical labels; it never promotes that response to current evidence.

## Changes and tradeoffs

- Reuse the package's NYSE calendar object and holiday cache under the existing
  lock, preserving date-range copies, holidays and early closes. Cache no quotes.
- Calculate only the classifier's consumed EMA/range/volatility columns with the
  identical full-history formulas, seed and strict OHLC audit. The full research
  feature calculator remains available and unchanged in its calculations.
- Remove one redundant candidate copy. Validate and calculate every candidate's
  exact payoff before capital filtering. Materialize chart landmarks/extremes only
  for accepted candidates; exclusions keep exact risk, profit and breakevens.
- Reuse immediately validated discovery payoff results for evidence-unavailable
  intraday annotations, with unchanged fees and multiplier. External/explicit
  research still validates original legs and cashflow, ignoring supplied metrics.
- Discovery output keeps original observations in `research.trade.legs` and
  normalized signed/action/quantity observations in `research.position.legs`.
  Omit redundant `research.legs`, `research.payoff.trade` and
  `research.evidence.option_legs` aliases. `presentation` identifies discovery or
  capital-exclusion summaries. Explicit structure endpoints retain full output.
  Accepted chart landmarks remain; exclusions expose empty charts with
  `grid_sampling=not_materialized`. Clients using removed aliases must use the
  canonical fields above. REST, website fixtures and OAuth MCP agree.
- Reuse redacted strings/shared normalized arrays only within one response; retain
  credential redaction, nonfinite-value handling and scalar conversions.
- Share one request-local cancellation event across middleware, route and worker.
  Add checkpoints in normalization, OHLC, calendar waits, economics and response
  traversal. An observed disconnect stops subsequent work and yields no successful
  research response. Browser cancellation also reaches the website's upstream
  fetch, combined with the unchanged 12,000 ms timeout.

Blocking SDK calls and individual C/Pandas/JSON/gzip operations cannot be forcibly
interrupted safely. Cancellation is cooperative at the next checkpoint. No other
request's event is set. No provider, infrastructure, secret or deployment changes
were made. Auto/manual width semantics, supported strategies, search budgets,
partial coverage diagnostics, exact expiration matching, SHA256 checks, freshness,
capital economics and fail-closed evidence eligibility remain intact.

## Validation and benchmarks

The committed benchmark data records each request/stage, wall time, process CPU,
peak RSS, counts, decoded bytes, actual compressed ASGI bytes and equivalence
digests. These are synthetic fixtures matching production row-count scale, not
replayed production quotes or measured provider latency: 2,820 contracts per
symbol, 141 observed strikes per side across ten expirations, 1,260 daily bars,
real archive SHA256/decompression/identity checks, real REST/middleware/compression,
20 ms simulated archive/history delays and five dummy secret-redaction values.
No synthetic prices enter production or support market conclusions.

Both revisions use the same benchmark helpers. Four concurrent SPY/QQQ/SPY/QQQ
requests are run twice in each new process: cold calendar caches, then warm.
Independent SPY/QQQ runs use concurrency one. Process CPU includes test-client
decoding and equivalence hashing, not just server execution. Warm/cold network and
Public SDK startup behavior are **not** represented by these fixtures.

Reproduce against `8a374fbd` and this branch with
`python tests/benchmark_research_pipeline.py --production-scale --mode historical`;
also use `--width 5`, `--expiration 2030-01-04`, `--expiration 2030-01-18`,
`--expiration 2031-01-17`, `--capital none --late`, and
`--concurrency 1 --symbol SPY` / `QQQ`. Omit `--mode historical` for current mode.
The economic digest omits only charts, explicitly removed quote aliases and
presentation/budget metadata; retained economics, quotes, identities, counts,
classifications and safety diagnostics must match exactly.

Results against `8a374fbd` (seconds, min–max across requests in each round):

| Case | Before cold / warm | After cold / warm |
|---|---|---|
| Historical $150 Auto | 4.11–5.35 / 3.82–4.82 | 2.01–2.79 / 2.16–2.65 |
| Historical $150 manual $5 | 0.92–0.96 / 0.66–0.71 | 0.52–0.55 / 0.30–0.41 |
| Current $150 Auto | 3.95–4.87 / 3.95–4.86 | 1.98–2.76 / 2.42–2.96 |
| Current $150 manual $5 | 1.44–1.49 / 0.65–0.78 | 0.53–0.56 / 0.38–0.40 |
| Historical weekly Auto | 4.11–5.01 / 4.02–4.90 | 1.93–2.54 / 1.94–2.77 |
| Historical monthly Auto | 4.34–5.34 / 3.71–4.79 | 1.83–2.53 / 1.92–2.50 |
| Historical long-dated Auto | 3.98–4.98 / 3.72–4.86 | 1.86–2.70 / 2.43–2.89 |
| Late dashboard, no capital limit | 5.95–7.34 / 5.84–7.22 | 3.88–5.63 / 3.93–5.24 |
| Independent SPY $150 Auto | 1.43 / 1.09 | 0.67 / 0.53 |
| Independent QQQ $150 Auto | 1.26 / 1.09 | 0.66 / 0.54 |

Per-stage median wall time across eight concurrent-case requests (ms):

| Stage | $150 Auto before → after | No capital limit before → after |
|---|---:|---:|
| Verified archive read | 49 → 51 | 50 → 50 |
| Synthetic history load | 59 → 60 | 69 → 64 |
| Archive normalization | 122 → 68 | 122 → 68 |
| Session calendar | 56 → 12 | 58 → 12 |
| History features | 699 → 194 | 620 → 343 |
| Width enumeration | 6 → 14 | 10 → 28 |
| Candidate/payoff research | 452 → 206 | 582 → 406 |
| Candidate comparison | 2 → 1 | 16 → 28 |
| Historical economics | 80 → 3 | 1,004 → 114 |
| Total research calculations | 1,762 → 850 | 2,763 → 1,398 |
| Response serialization | 1,424 → 734 | 1,934 → 1,498 |

These overlapping wall spans include thread scheduling; small enumeration/
comparison differences are not evidence of improvements or changes in search.
The enumeration algorithm and attempt limits are unchanged. Savings come from
calendar/feature reuse, reduced copying/chart work, historical validation reuse
and smaller responses. No market-data cache or new provider was introduced.

The $150 Auto case retained 1,024 researched structures / 105 accepted; manual $5
retained 70 / zero, as all valid researched manual structures in this synthetic
chain exceed $150. The late no-limit case retained 892 / 892. Search bounds and
partial diagnostics match before/after. Every retained economic/quote/identity/
classification/count/safety digest matched across all ten benchmark cases.

$150 Auto batch CPU fell from 5,875/5,547 to 3,219/3,328 ms (cold/warm); the no-limit
case fell from 8,594/8,484 to 6,391/6,375 ms. $150 decoded output fell from 11.99 MB
to 5.50 MB; SPY compressed bytes from 770,410 to 311,612. The no-limit response
remains substantial: 17.84 → 13.03 MB decoded, 1,048,247 → 825,465 compressed bytes.
Peak process RSS was 310/335 → 290/290 MiB ($150) and 367/368 → 357/359 MiB (no limit).
Compression remains level 1; smaller output reduces its work without changing
negotiation. A separate seven-run in-memory gzip level-1 measurement of the $150
REST JSON measured a median 39.97 → 15.82 ms (no network or concurrency): compression
alone is much smaller than the observed multi-second research/serialization work.
Raw measurements are in
[`performance/issue60-followup-fixture-benchmarks.json`](performance/issue60-followup-fixture-benchmarks.json).

Regression coverage includes four concurrent cold/warm SPY/QQQ requests in both
modes, Auto/manual, $150, weekly/monthly/long expirations, the no-limit dashboard,
shared-calendar accuracy/copy isolation, exact classifier equivalence, all affected
family economics and ignored forged metrics, real ASGI disconnects with an active
peer, blocking-I/O cancellation, stale/missing/corrupt archives, stale/missing quotes,
partial-search bounds and real REST/OAuth MCP/website fixtures. The deadline tests
require under 10.5 seconds locally; they do not certify Render performance.

Final checks: **1,153 Python tests and 64 subtests passed** (301.57 seconds),
**91 website tests passed**, **27 Chromium browser tests passed**; TypeScript
typecheck, production website build and `git diff --check` passed. Four existing
Supabase SDK deprecation warnings remain. The Python run used a fresh writable
workspace-local `--basetemp` because the machine's default pytest temporary
directory was inaccessible; no test assertions or suite checks were skipped.

## Production acceptance checklist (still open)

- After an approved deployment, confirm the exact reviewed commit in both services.
- During an open NYSE session verify fresh complete SPY/QQQ uploads, observed/slot/
  finish times and hashes. Check provider failures and scheduler start delays.
- Exercise independent, simultaneous and four-request cold/warm runs through the
  actual website, REST and OAuth MCP, including $150 Auto/manual $5 and the
  dashboard with no capital limit; near/weekly/monthly/long expirations must match.
- Require repeated end-to-end website completion below 12 seconds with headroom,
  including provider startup, response transfer and body validation. Correlate
  bridge IDs with all backend stages and resource metrics; fixture timing alone
  cannot pass this gate.
- Verify stale current responses after close, separately labeled historical
  research, and safe missing/corrupt/stale-quote/unavailable-expiration failures.
- Abort during archive I/O, candidate work, historical annotation and serialization.
  Require prompt cooperative cancellation/no success payload, eventual completion
  of already-blocked provider calls, balanced active counts and unaffected peers.
- Preserve unavailable historical intraday evidence/POP/EV, capital exclusions,
  quote provenance and visible partial-search bounds. No fabricated candidates,
  prices or eligibility upgrades. Keep Milestone 1 open until all checks pass.
