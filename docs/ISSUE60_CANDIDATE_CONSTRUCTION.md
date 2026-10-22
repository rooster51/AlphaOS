# Issue 60: candidate construction experiment

Baseline: main `ff0a42efe74f964733cd2f0ea79e7456a1e862c8`.
This report concerns diagnostic fixtures, not production acceptance. No deployment,
production configuration, timeout, authentication, or provider change was made.
Issue #60 and Milestone 1 remain open.

## Construction and traversal audit

The production-scale synthetic monthly unrestricted Auto Width workload yields
1,024 candidates per SPY/QQQ request. The frozen archive has 2,820 contracts over
ten expirations; the history fixture has 1,260 daily rows. These are test inputs,
not verified real market observations or trade recommendations. The real archive
reader still verifies the fixture checksum and requested expiration.

Counts below come from `tests/performance/count_construction.py`, using cProfile
and an identity-aware graph walk. Instrumentation is excluded from latency runs.
Both symbols produced identical counts. Recursive deepcopy counts include calls
on scalar values, not 152,693 distinct candidate objects.

| Work per request | Baseline | Copy-elision experiment |
| --- | ---: | ---: |
| Discovered/researched candidate positions | 1,024 | 1,024 |
| Exact payoff analyses (`analyze`) | 1,024 | 1,024 |
| Trade normalization/validation calls | 2,048 | 2,048 |
| Payoff materialization calls | 2,048 | 2,048 |
| Payoff scenario evaluations | 18,404 | 18,404 |
| Recursive `deepcopy` calls | 152,693 | 26,741 |
| Deep-copied dictionaries | 4,697 | 1,625 |
| Deep-copied lists | 6,273 | 1,153 |
| Sanitizer dictionary visits | 47,210 | 47,210 |
| Unique input dictionaries visited | 47,170 | 47,170 |
| List encounters before existing memoization | 25,681 | 25,681 |
| Unique input lists visited | 20,537 | 16,601 |

Each two-leg candidate is constructed once, then baseline structure research
deep-copies its root, two leg dictionaries, and nested observation arrays. The
trade is normalized once by structure research and again by the public payoff
engine: two normalizations per candidate, but only one exact payoff calculation.
One normalized position/evidence projection and one comparison projection are
created per candidate. The initial structure evidence leg projection is replaced
by the position projection; final discovery removes redundant aliases already
represented in trade/position. Those temporary evidence objects remain a possible
future allocation target; they were not changed in this experiment.

Payoff materialization is first called with `none` for exact-economics validation,
then with landmarks after capital eligibility. It does not recompute exact
economics. There is no ranking to move earlier: discovery retains deterministic
enumeration order and explicitly makes no recommendation. Capital gating already
precedes expensive chart construction. Moving it ahead of exact payoff evaluation
would violate the capital requirement; reducing search breadth is not a solution.

Existing shared-list memoization prevents thousands of repeated array traversals.
Only 40 repeated dictionary visits remain after that memoization, predominantly
small market-context objects. A dictionary cache would not address the dominant
47,170 distinct dictionaries. The raw graph contains 147,474 float and 132,386
string encounters, plus other scalar values. REST's raw v2 path already avoids
the default JSON-ready helper passes; there is no redundant whole-response
`_serializable` pass to remove on this path.

## Experimental correction and safety boundary

The experiment adds a private ownership-aware constructor path only for candidates
created by automatic discovery in the current request. It skips their recursive
deep copy and starts with a root mapping copy. Trade/leg normalization, family
validation, exact payoff analysis, capital checks, comparison, quote observations,
and all later sanitization/redaction remain unchanged. Nested quote metadata is
read-only during this private pipeline. Public/caller-supplied research retains
defensive deep copies. There is no global cache, provider cache, cross-request
reuse, acceptance of caller-cached economics, or user-accessible ownership flag.
The previous sanitizer-closure cleanup is absent.

This eliminates 125,952 recursive deepcopy calls, 3,072 dictionary clones, and
5,120 list clones per request. It does not eliminate necessary economic output
representations: top-level economics, payoff analysis, capital identity,
historical economics, and comparison are existing response contracts.

Local baseline/candidate SPY and QQQ serialized bytes match exactly (12,735,756
bytes per symbol under the local fixture environment). Linux lifecycle tests
compare every field across direct REST and website response bodies using canonical
full-response digests, with only JavaScript's integral-number spelling normalized.
No fields, economics, safety flags, quotes, provenance, diagnostics, or exclusions
are ignored. Payload size is not reduced by this experiment.

## Website field audit

`web/src/components/market/MarketResearchPanel.tsx` consumes both accepted and
capital-excluded candidates via `web/src/lib/market-candidates.ts`. Its expandable
evidence panel includes the full candidate `research` object, eagerly pretty-printed
even when collapsed (line 784 in the baseline). Diagnostics, routes, exclusions,
warnings, and provenance are also shown. The session-level `comparison` and
`historical_comparison` roots are not directly consumed by that panel, but they
remain full REST/MCP data. An earlier captured production monthly session was
91.4% candidates and 8.4% comparison by compact JSON size. Removing comparison
cannot be assumed to solve the main cost, and removing candidate details would
change the full website research view. No response fields were removed.

## Measurement protocol

The actual website POST handler runs in a small Node HTTP adapter, with the
unchanged 12-second deadline. Both it and the backend receive separate Linux
cgroups of 0.15 CPU and 512 MiB memory/no additional swap, applied before imports.
Python is 3.12.14 and Node 24.21.0. The uncapped CPU control retains the memory
limit. Each job compares baseline and candidate in the same Python image on the
same host; baseline source is exported directly from `ff0a42e`, not emulated by
patching a sanitizer. Variant order alternates between symbol-start cases.

Each fresh process pair starts with SPY, QQQ, or concurrent SPY+QQQ, then runs two
sequential rounds, two concurrent rounds, and one direct REST pair. "Cold" means
first research after health readiness, not Render idle wake or interpreter boot.
Separate tracemalloc passes measure allocations and are not latency benchmarks.
Complete-body time ends after all bytes arrive; external diagnostic-client parsing
is measured separately. The bridge's own reading, decoding, parsing, and response
construction are included. HTTP 200 over 12 seconds is a deadline failure.

Archive/provider HTTP calls use 20 ms fixture stubs and provider authentication is
synthetic. Real checksum verification, history processing, SDK dependency import,
research calculations, payoff output, sanitization, encoding, and compression run.
This is not the Next production framework, Render edge/WAN, live provider behavior,
or browser-render benchmark. Same quota does not mean identical physical CPU.
Hosts and package versions are recorded; unpinned dependency installs can differ
from the deployed release. Compare variants within matched jobs, not absolute
times against prior investigations.

Stage wall/thread CPU and GC callbacks are recorded separately. GC time is already
inside parent stage time. Node process CPU may include a concurrent peer or V8
workers. Do not add nested medians or overlapping process CPU as exclusive totals.

## Benchmark results and disposition

**Rejected. No draft PR.** The second independent repeat did not reproduce the
concurrent website improvement. Application files have been restored to main.
The rejected patch and its passing experimental parity tests are retained as
inert diagnostic artifacts, not active product changes.

[Run 1](https://github.com/rooster51/AlphaOS/actions/runs/39825541469), source
`599deae495e703d1b284c0f536116dfd98d19150`;
[run 2](https://github.com/rooster51/AlphaOS/actions/runs/39826537491), source
`62aba97735f7e227d36a0ca77ab79a19b15ae3f6`. The second commit adds parity tests
only; the experimental application code is identical. Both workflows passed
their full-response digest checks. Each run includes 12 sequential, 12 concurrent,
four cold first responses (two single-symbol starts plus a pair), and six direct
REST responses per constrained variant.

Seconds: median / worst successful complete body, population SD; deadline pass
counts include every response. HTTP 502 responses are excluded from successful
timing distributions, not from the denominator. This distinction matters because
an HTTP 200 can also exceed 12 seconds.

| Run / constrained workload | Baseline median / worst (SD) | Experiment median / worst (SD) | Under 12 s: before / after |
| --- | --- | --- | --- |
| 1 warm sequential | 6.611 / 11.191 (1.556) | 6.059 / 9.099 (0.968) | 12/12 / 12/12 |
| 1 warm concurrent | 10.958 / 13.455 (1.576), 10 HTTP 200 | 10.280 / 12.846 (1.562), 11 HTTP 200 | 7/12 / 9/12 |
| 1 cold | 8.916 / 10.927 (2.011), 2 HTTP 200 | 9.155 / 10.809 (1.653), 2 HTTP 200 | 2/4 / 2/4 |
| 1 direct REST concurrent | 10.488 / 11.120 (1.574) | 9.390 / 10.040 (0.613) | 6/6 / 6/6 |
| 2 warm sequential | 7.228 / 9.395 (0.791) | 6.168 / 8.197 (0.766) | 12/12 / 12/12 |
| 2 warm concurrent | 11.700 / 13.159 (1.021), 10 HTTP 200 | 11.809 / 13.379 (1.163), 12 HTTP 200 | 6/12 / 7/12 |
| 2 cold | 11.162 / 11.508 (0.346), 2 HTTP 200 | 10.434 / 10.444 (0.011), 2 HTTP 200 | 2/4 / 2/4 |
| 2 direct REST concurrent | 9.825 / 10.634 (0.469) | 8.860 / 10.039 (0.610) | 6/6 / 6/6 |

Run 1 paired concurrent comparisons where both returned HTTP 200: seven of nine
faster, median -9.94%, range -16.51% to +32.57%. Run 2: only two of ten faster,
median **+4.47% slower**, range -24.86% to +18.04%. Run 2 converts four deadline
failures to passes but also converts three passes to failures. Aggregating the
deadline counts (13/24 to 16/24) would conceal the failure to repeat the timing
improvement. Sequential paired medians improve 10.40% and 12.56%; these do not
establish concurrent website reliability.

Cold single SPY was 6.905 -> 7.502 s in run 1 and 10.817 -> 10.423 s in run 2.
Cold single QQQ was 10.927 -> 10.809 s and 11.508 -> 10.444 s. Both cold paired
responses timed out in both variants in both runs. Cold effects are not solved.
The uncapped CPU controls all met 12 seconds: concurrent medians 1.564 -> 1.493 s
and 1.749 -> 1.597 s. Faster controls do not overcome constrained contention.

### CPU, sanitization, and GC attribution

Median constrained thread CPU milliseconds (all backend research requests), with
GC attributed by matching callback intervals and request IDs. The exclusive
median is computed per request before taking the median. Different medians are
not additive.

| Run / stage | Baseline inclusive / excluding GC | Experiment inclusive / excluding GC |
| --- | ---: | ---: |
| 1 candidate/payoff | 179.08 / 166.65 | 127.88 / 118.42 |
| 2 candidate/payoff | 176.14 / 163.78 | 126.58 / 116.69 |
| 1 sanitization/redaction | 292.85 / 190.15 | 283.98 / 185.62 |
| 2 sanitization/redaction | 300.75 / 184.01 | 307.92 / 183.44 |

Thus the intended CPU saving is real and repeated (roughly 28% candidate/payoff
CPU), while sanitization's own traversal CPU barely changes. GC inside
sanitization is substantial and variable: callback CPU medians were 126.65 ->
108.04 ms and 110.31 -> 124.17 ms. Native JSON encoding remains roughly 16 ms
thread CPU in the first run, far below sanitization and construction.

Across constrained processes, generation-2 GC totals were 45 -> 40 collections,
7.552 -> 6.497 s CPU in run 1; 44 -> 42 collections, 6.505 -> 5.755 s CPU in run 2.
These are cumulative process-lifetime totals, not per-request savings or exclusive
pipeline phases. Even after eliminating clones, large live/unreachable response
graphs and CPU scheduling continue to dominate end-to-end variation. The rejected
closure experiment is not silently included here, and GC settings are unchanged.

### Memory, payloads, and parity

| Metric | Run 1 before / after | Run 2 before / after |
| --- | ---: | ---: |
| Peak process RSS bytes, maximum across jobs | 374,456,320 / 368,259,072 | 363,773,952 / 360,615,936 |
| Peak backend cgroup memory bytes | 290,447,360 / 297,459,712 | 292,593,664 / 289,513,472 |
| Peak website-adapter process RSS bytes | 238,338,048 / 260,726,784 | 248,627,200 / 286,515,200 |

The website-adapter read/decode CPU medians were 99.02 -> 110.08 ms and
104.33 -> 117.88 ms; JSON parse 87.13 -> 87.62 ms and 111.24 -> 107.70 ms;
response construction 52.70 -> 55.36 ms and 56.11 -> 58.07 ms. These process CPU
intervals may include peer requests/V8 workers. The website still performs
substantial full-body work; backend clone removal does not remove that work.

Memory accounting scopes differ. There is no consistent large peak-memory win;
all measured OOM events remain zero. Separate tracemalloc profiles and allocation
sites are retained in the JSON summaries and raw artifacts. Their timings are
excluded from the latency tables because tracing perturbs both CPU and GC.

The full monthly Linux responses match before/after in each job and across direct
REST/website transport, with unchanged approximately 12.54 MB decoded website
body and 0.811 MB backend gzip. An additional 16-case matrix compares exact
serialized bytes against a separate `ff0a42e` checkout: both symbols, monthly and
long-dated expiration, $150 and unrestricted capital, Auto Width and manual $5.
Every case matches, including exclusions and diagnostics. The 68 constructor
parity/validation cases cover all supported structure families, two expirations,
and all payoff presentation modes, and verify caller-copy isolation and rejection
of invalid quantities. These tests passed before the experiment was discarded.

## Validation and final disposition

Experimental source: **1,239 Python tests + 64 subtests passed**, with four existing
SDK deprecation warnings; **100 website tests**, **29 browser tests**, typecheck,
and production build passed. A first local Python attempt encountered an existing
Windows temp-directory permission error; the complete successful rerun used a
fresh workspace temp directory without changing application or test assertions.
After restoring the application files, the complete Python suite passed again:
**1,171 tests + 64 subtests**, four existing warnings, in 357.03 seconds. Backend,
module, and website source diffs against main are empty.

All three application files are restored to `ff0a42e`. The experiment's tests are
preserved in `tests/performance/owned_parity_experiment.py.txt`, and the source
patch in `performance/issue60-rejected-owned-copy.patch.gz`. They are not deployed
or proposed for merge. The manual-only profiling workflow explicitly checks out
the immutable experimental commit to reproduce the recorded comparison; it does
not build/deploy production or change settings.

Durable data: `performance/issue60-construction-{baseline,experiment}.json`,
`issue60-owned-run{1,2}-summary.json`, and `issue60-owned-parity-matrix.json`.
The summaries include individual request IDs and complete-response times, failure
rows, CPU/GC/memory distributions, package/CPU identities, workflow IDs, and raw
ZIP SHA-256 values. Original workflow artifacts have seven-day retention; local
ZIPs are retained in the workspace parent as `issue60-owned-*.zip` and
`issue60-owned-repeat-*.zip`. They contain no production credentials or private
TLS keys. The raw host CPU models differ between some jobs, while before/after
within a job use the same host/image; this is another reason not to infer
production latency from pooled fixture medians.

Next evidence-based experiment: measure a **buffered, incremental full-response
sanitization/encoding path** that avoids accumulating a second large sanitized
object graph before JSON encoding. Keep every existing JSON field and redaction
rule, and emit no HTTP body until validation and encoding complete so failures
remain closed. First measure allocation/GC reduction and repeat the same paired
cold/concurrent complete-body tests; do not assume it will improve performance.
Dictionary memoization has little remaining duplicate work to eliminate, exact
payoff is already computed once, and earlier filtering cannot safely remove
required economics. This is a recommendation for a bounded experiment, not a
production optimization proposal. **Issue #60 and Milestone 1 remain open.**
