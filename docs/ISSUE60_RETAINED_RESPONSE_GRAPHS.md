# Issue 60: retained response graphs and buffered encoding experiment

Baseline: main `ff0a42efe74f964733cd2f0ea79e7456a1e862c8`. Date: 2026-10-22.
Issue #60 and Milestone 1 remain open. This is a constrained fixture investigation,
not production acceptance. No deployment, infrastructure, provider, authentication,
freshness, timeout, strategy, enumeration, or capital-policy change was made.

## Hypothesis and measured retention

Baseline `sanitized()` builds a complete second response graph. Its recursive
`clean` closure references itself and owns the list-normalization cache, which
keeps source arrays and transformed arrays reachable from that cycle after JSON
encoding. Neither the source graph nor the transformed graph necessarily goes
away when the HTTP body/input variables are released. Cyclic GC must discover
the unreachable cycle later, potentially during another request's construction
or sanitization. The earlier closure-only fix was rejected; it is not treated as
a proven latency improvement here.

An intrusive local profile freezes GC only during serialization/release, uses a
weak-referenceable source candidate list, counts GC-tracked objects, and records
tracemalloc snapshots at each boundary. It then forces GC and restores the
original GC state. This happens only in the diagnostic process; serving uses
normal GC throughout. Traced/forced-GC times are not latency benchmarks.

SPY results (QQQ has the same tracked-object counts and within 4 KB of these
traced retained-memory values):

| Boundary | Baseline tracked objects / traced retained bytes | Experiment tracked objects / traced retained bytes |
| --- | ---: | ---: |
| Before research | 183,129 / about 0.03 MB | 183,129 / about 0.03 MB |
| Research graph built | 219,619 / 19.15 MB | 219,619 / 19.15 MB |
| Body encoded | 274,038 / 53.99 MB | 219,631 / 35.86 MB |
| Input released | 274,013 / 54.06 MB | 184,720 / 17.61 MB |
| Body released, before forced GC | 274,025 / 37.44 MB | 184,732 / 1.00 MB |
| After forced GC | 184,693 / 0.78 MB | 184,693 / 0.78 MB |

The baseline source weak reference remains alive after input release; the
experiment's is dead immediately. Baseline forced GC collects 89,293 objects;
candidate forced GC collects zero. Baseline's retained allocations include
10.4 MiB of sanitizer dictionaries, 4.1 MiB of sanitizer lists, roughly 2.9 MiB
of sanitizer dictionary storage, and payoff/position graphs. GC-tracked counts
include unreachable-but-uncollected objects; they are not a count of externally
reachable application objects, nor a complete count of every Python allocation.

Traced peak memory is a tradeoff: 56.38 MB baseline versus 60.27 MB experiment
for SPY, because buffering candidate bytes adds temporary byte allocations. Lower
retained object memory does not imply lower peak RSS or faster body completion.

## Traversal and contract preservation

Instrumented `clean` call counts per symbol are identical before/after:
47,210 dictionaries, 25,681 lists, 132,386 strings, 147,474 floats, 12,379 integers,
14,369 booleans, and 47,136 nulls. There are 47,170 unique dictionaries and 20,537
unique lists; the existing memoization avoids rewalking shared list contents.
Only 40 dictionary visits are repeats. Therefore this experiment does not depend
on silently skipping response data or claiming a large duplicate traversal win.

There are still 1,024 researched candidates in the monthly unrestricted workload,
with one exact payoff analysis each. No research constructors, payoff functions,
strategy families, quote observations, search budgets, expiration matching,
eligibility checks, or candidate order were changed. The rejected candidate-copy
elision is absent.

The experimental encoder replaces only the temporary representation of full v2
market-session candidate and exclusion arrays. It sanitizes one entry at a time
with the existing implementation, encodes it into bytes, and releases the small
temporary graph. Key policy and redacted primitive strings are reused only within
the response; list memoization remains local to an entry. The smaller header
retains original field order, every field, and both full candidate arrays as
internally encoded JSON fragments. Input graphs are not mutated. No caller bytes
are accepted as fragments. All bytes are buffered; nothing is emitted until all
sanitization/encoding succeeds, preserving error/fail-closed handling.

Root v2 nonfinite-number semantics apply to every chunk. Standard JSON fallback
remains available for integers outside the native encoder range. Legacy endpoints
and responses without a market research session use the existing full-graph path.
Tests exercise Unicode, secrets in strings, sensitive-key removal, nonfinite
numbers, dates/numpy scalars, arbitrary-size integers, tuples, colliding normalized
keys, unsupported-object failure, empty/legacy shapes, and source-list lifetime.

Full SPY/QQQ fixture bodies match baseline bytes exactly (12,735,756 bytes each in
the local environment). An additional 16-case matrix uses separate baseline and
candidate source trees: both symbols, monthly and long-dated expiration, Auto Width
and manual $5 width, $150 and unrestricted capital. All complete serialized bodies
match, including diagnostics, exclusions, provenance, and economics.

## Constrained lifecycle protocol

Python 3.12.14 and Node 24.21.0 run in separate Linux Docker cgroups with 0.15 CPU,
512 MiB memory, and no additional swap, applied before imports. The uncapped CPU
control retains the memory cap. Baseline is exported from `ff0a42e`; both variants
use the same Python image and physical runner within each job. Package versions,
CPU identity, Docker inspection, cgroup CPU throttling, memory events, RSS, and
request IDs are retained. Same quota does not establish identical Render hardware
or package versions, especially with unpinned dependencies.

Each fresh process pair begins with SPY, QQQ, or simultaneous SPY+QQQ, followed by
two sequential rounds, two concurrent rounds, and a direct REST pair. "Cold"
means first research after health readiness, excluding interpreter boot and Render
idle wake. The fixture has 2,820 contracts over ten expirations and 1,260 daily
history rows, with frozen monthly expiration `2030-01-18` and unrestricted Auto
Width. Fixture quotes are synthetic diagnostic inputs, not real market evidence.
Real archive checksum/payload verification runs; archive/provider HTTP calls are
20 ms stubs and provider authentication is synthetic. SDK dependency import,
calendar/history work, research, sanitization, encoding, and gzip remain exercised.

The actual website POST handler runs through a small HTTP adapter, with the
unchanged 12-second abort signal. This is not Next's framework, browser rendering,
Render TLS termination, edge transfer, WAN, or live provider behavior. End-to-end
completion ends after the entire website response body arrives at the diagnostic
client. That client's later JSON parse is measured separately and excluded;
the website bridge's own read/decode, parse, and response construction are included.
HTTP 200 over 12 seconds counts as a failure.

Python stage wall/thread CPU, GC generation/CPU/wall pauses, JSON encoding, gzip,
ASGI sends, website body read/decode, website JSON parse, and response construction
are instrumented. Operation measurements aggregate in request-local state to avoid
logging once per candidate chunk. Separate traced allocation passes also count
tracked objects and record hotspots; their timings are excluded from benchmarks.
GC is inside parent stage time. Per-chunk operation timers omit some caller-side
deallocation/join work; total serialization and complete-body timing include it.
Node process CPU can include a concurrent peer/V8 workers. Nested medians and
overlapping CPU intervals must not be added as exclusive costs.

## Results and disposition

The buffered representation demonstrated repeated aggregate improvements and is
proposed as a **draft, incremental GC-retention fix**. It does not establish the
12-second production SLO or resolve all cold/concurrent failures. No merge or
deployment is authorized. Issue #60 must not auto-close from this PR.

Three independent matched runs:

1. [Run 39830728954](https://github.com/rooster51/AlphaOS/actions/runs/39830728954),
   initial source `b3a650a06b7a8ff29e268da5378518b02fa08c82`.
2. [Run 39831776239](https://github.com/rooster51/AlphaOS/actions/runs/39831776239),
   identical application source; commit `0359522a3958579065c216f8f9194baea71237df`
   adds traversal instrumentation only.
3. [Run 39832878454](https://github.com/rooster51/AlphaOS/actions/runs/39832878454),
   final application source `c8830b7`: policy initialization is centralized in the
   original sanitizer instead of repeating the secret-key list in the buffer
   helper. Every final source field and economic output still matches baseline.

Seconds: successful complete-body median / maximum, with population SD. Timeout
HTTP 502 bodies are not successful research responses and are excluded from these
latency distributions, but **included in all denominators**. Different successful
sample counts mean the median is not a paired estimator; individual request
records, paired comparisons, and deadline counts are retained alongside it.

| Run / constrained case | Baseline median / worst (SD) | Buffered median / worst (SD) | Under 12 s: baseline / buffered |
| --- | --- | --- | --- |
| 1 warm sequential | 7.092 / 11.101 (1.234), 12 HTTP 200 | 6.521 / 9.093 (0.865), 12 HTTP 200 | 12/12 / 12/12 |
| 1 warm concurrent | 12.665 / 13.421 (0.469), 6 HTTP 200 | 11.940 / 13.128 (0.820), 9 HTTP 200 | 0/12 / 6/12 |
| 1 cold | 11.806 / 12.301 (0.495), 2 HTTP 200 | 11.122 / 12.008 (0.886), 2 HTTP 200 | 1/4 / 1/4 |
| 1 direct REST concurrent | 10.570 / 11.558 (0.596), 6 HTTP 200 | 9.243 / 10.023 (0.451), 6 HTTP 200 | 6/6 / 6/6 |
| 2 warm sequential | 7.009 / 8.863 (1.088), 12 HTTP 200 | 6.442 / 7.375 (1.004), 12 HTTP 200 | 12/12 / 12/12 |
| 2 warm concurrent | 11.514 / 13.164 (1.318), 7 HTTP 200 | 10.742 / 13.211 (2.226), 9 HTTP 200 | 4/12 / 5/12 |
| 2 cold | 13.010 / 13.308 (0.375), 3 HTTP 200 | 12.155 / 12.545 (0.437), 4 HTTP 200 | 0/4 / 2/4 |
| 2 direct REST concurrent | 10.567 / 12.661 (2.031), 6 HTTP 200 | 8.679 / 10.348 (1.326), 6 HTTP 200 | 4/6 / 6/6 |
| 3 warm sequential | 6.688 / 7.565 (0.763), 12 HTTP 200 | 5.772 / 6.249 (0.724), 12 HTTP 200 | 12/12 / 12/12 |
| 3 warm concurrent | 11.446 / 13.160 (1.553), 10 HTTP 200 | 10.054 / 12.550 (1.743), 12 HTTP 200 | 6/12 / 10/12 |
| 3 cold | 11.498 / 12.205 (0.492), 3 HTTP 200 | 11.208 / 12.802 (1.058), 4 HTTP 200 | 2/4 / 3/4 |
| 3 direct REST concurrent | 10.141 / 10.647 (0.305), 6 HTTP 200 | 8.560 / 9.481 (1.526), 6 HTTP 200 | 6/6 / 6/6 |

All 36 matched warm sequential responses improve; paired medians improve 14.07%,
15.35%, and 15.33%. Warm concurrent run-level medians and deadline rates improve
in all three runs, but individual latencies are not monotonic. In run 1 only two
of five pairs where both variants return HTTP 200 are faster (paired median
4.81% slower); the other successful bodies come from requests that failed in the
baseline. In runs 2 and 3, six of six and eight of ten such matched responses
improve, paired medians -17.97% and -11.03%. No baseline deadline pass becomes a
deadline failure in the three constrained warm concurrent/cold comparisons.

Pair-level reliability is a stricter and still-failed criterion. Warm batches
where **both** symbols finish under 12 seconds: run 1 0/6 -> 0/6; run 2 2/6 ->
2/6; final run 2/6 -> 4/6. Cold paired batches do not have both bodies under
12 seconds in any of the three comparisons. Improvement is not acceptance.

Cold singles improve in each run. Final SPY 11.498 -> 10.807 s and QQQ 11.006 ->
9.926 s. Final cold pair: baseline QQQ times out and SPY takes 12.205 s; buffered
QQQ completes at 11.610 s and SPY at **12.802 s**. That SPY tail is 4.89% slower
than its already-over-budget baseline. The cold median/deadline-rate gain must
not conceal this regression; cold tail reliability remains a production risk.

Uncapped controls all meet 12 seconds. Warm concurrent medians are 1.871 ->
1.616 s, 1.675 -> 1.579 s, and 1.667 -> 1.435 s. The corresponding constrained
results demonstrate CPU-quota sensitivity rather than pure provider latency.

## GC and stage-level attribution

Per-process cumulative generation-2 collection totals across each constrained
run (not per-request savings):

| Run | Collection count, before / after | CPU seconds, before / after | Wall-pause seconds, before / after |
| --- | ---: | ---: | ---: |
| 1 | 44 / 28 | 6.864 / 2.820 | 49.039 / 20.318 |
| 2 | 41 / 25 | 7.665 / 2.743 | 54.320 / 20.634 |
| 3 | 45 / 26 | 7.507 / 2.706 | 53.255 / 19.607 |

Final generation-2 pause median / p95 / max wall: baseline 1,110 / 2,038 / 2,287 ms,
buffered 744 / 967 / 1,003 ms. CPU pause median / max falls from 164 / 326 ms to
101 / 132 ms. These wall pauses include quota throttling and scheduling; they
are not all CPU work. GC remains necessary and is not disabled or retuned.

Whole serialization stage median thread CPU (all 34 backend research requests
per constrained variant): 335 -> 242 ms, 338 -> 241 ms, and 302 -> 204 ms.
Matching GC callbacks to the true parent serialization interval separates the
work: final median GC CPU 130.36 -> 1.30 ms; median serialization CPU excluding
GC 188.61 -> 202.42 ms. Non-GC work slightly increases because of small-chunk
sanitization/encoding and byte assembly, but avoided retained-graph GC more than
offsets it in these runs. Medians are computed per request before summarizing;
different medians are not additive. Per-chunk operation aggregates are not used
to infer GC time windows.

Final warm concurrent stage medians (wall ms / thread CPU ms):

| Stage | Baseline | Buffered |
| --- | ---: | ---: |
| Research execution | 4,986.5 / 360.13 | 4,293.0 / 318.24 |
| Whole serialization | 3,748.5 / 267.91 | 2,700.0 / 205.11 |
| Sanitization/redaction operations | 3,598.8 / 252.24 | 1,330.7 / 170.99 |
| JSON encoding operations | 105.6 / 16.58 | 107.8 / 21.04 |
| Gzip compression | 535.2 / 36.14 | 438.1 / 36.48 |

Research code is unchanged. Lower execution CPU/wall can reflect less GC over
prior responses during the next request, not a faster payoff algorithm. The gap
between summed small operations and whole serialization includes byte assembly
and caller-side deallocation. Native JSON encoding is still comparatively cheap.
Complete-body times, not any single timer, remain the decision metric.

The website still reads/decompresses/decodes and parses the complete body, then
constructs its full wrapper. In run 1 warm concurrent median read/decode was
1,044.6 -> 973.2 ms and JSON parse 751.5 -> 791.2 ms; response construction
approximately 405 ms in both. Backend headers in that run arrived around
9-11 seconds baseline and 8-10 seconds buffered. Those remaining bridge costs
consume much of the deadline headroom. This experiment does not optimize them.

## Memory and payloads

| Peak bytes | Run 1 baseline / buffered | Run 2 baseline / buffered | Final baseline / buffered |
| --- | ---: | ---: | ---: |
| Backend process RSS | 369,438,720 / 361,746,432 | 376,459,264 / 365,305,856 | 371,642,368 / 358,719,488 |
| Backend cgroup memory | 295,440,384 / 291,090,432 | 294,219,776 / 291,098,624 | 302,751,744 / 288,137,216 |
| Website-adapter process RSS | 250,523,648 / 256,356,352 | 234,344,448 / 255,369,216 | 254,550,016 / 256,503,808 |

Backend and cgroup accounting scopes differ. Backend peaks improve modestly;
website peak memory does not improve. Measured OOM counters/container flags remain
zero/false. No memory cap or GC threshold was changed.

In run 1's separate normal-GC tracemalloc passes, baseline response-end tracked
objects were about 395,000 and traced retained memory 98.9-100.6 MB. Buffered
response-end counts were about 214,700-215,600 and retained memory 9.4-27.8 MB,
depending on overlap with the peer response. Traced peaks were 118.2-118.9 MB
versus 103.4-104.7 MB. These concurrent, GC-enabled profiles differ from the
single-request GC-disabled diagnostic above; neither profile's timings belong
in the latency table. Raw snapshots/hotspots and all final-run values are retained.

Every successful full response matches the baseline canonical digest in all
three jobs in each run, across direct REST and website transport. JavaScript's
integral float/integer spelling is normalized, with no fields omitted. Website
decoded bodies remain approximately 12.54 MB and backend gzip bodies about
0.811 MB. No payload-size reduction is claimed. Original REST/MCP research
capabilities and every field remain intact; neither observation-only responses
nor a compact response contract is substituted.

## Validation, limitations, and production checklist

Final source: **1,184 Python tests + 64 subtests passed**, four existing SDK
warnings; **100 website tests**, **29 browser tests**, typecheck, and production
build passed. The initial local build stopped on a dependency advisory;
retrying succeeded, but CI subsequently blocked the vulnerable Next.js pin.
The scoped security correction below replaces that pin. No settings or
deployment files were changed. Thirteen new tests cover contract/safety/lifetime
edge cases; all 16 full-body parity cases also pass on the final implementation.

The draft is justified by repeated aggregate cold/concurrent median and deadline
outcome gains, substantial repeatable GC CPU reduction, and complete economic /
response parity. It is not a claim of statistically proven tail-SLO reliability:
sample sizes are small, several requests still miss 12 seconds, some individual
latencies regress, and the first two runs precede final policy centralization.
Only run 3 measures the exact final application source; runs 1/2 repeat the same
buffered representation. Independent deployment validation remains required.

Production acceptance, still open and **not executed for this undeployed change**:

- Verify the reviewed commit across backend, website, and MCP deployment/catalogs.
- Repeat real cold/warm monthly unrestricted SPY/QQQ separately and concurrently,
  measuring complete response bodies and website bridge time under 12 seconds.
- Recheck $150 Auto Width, manual widths, long-dated expirations, and all supported
  families, exact economics, capital exclusions, and no candidate-breadth reduction.
- Verify stale/missing/malformed archives, checksums, invalid/exact-mismatched
  expiration, authentication, and redaction remain fail-closed in production.
- Capture request IDs and backend/serialization/transfer/bridge breakdown; do not
  substitute these fixture timings for production evidence.

Next architectural investigation, if production remains over budget: reduce
duplicate full-body JavaScript materialization at the website bridge while
preserving its complete response wrapper, all research data, complete JSON/contract
validation, redaction, and error handling. No raw unvalidated pass-through or field
trimming is proposed. The full website's expandable candidate evidence panels use
the research object, so those fields cannot silently be removed. This is a future
bounded experiment, not another feature or change implemented in this PR.

## Reproducibility

The [complete machine-readable profile](https://github.com/rooster51/AlphaOS/blob/d3f8c04/docs/performance/issue60-buffered-response-summary.json) records every request ID,
success/failure and complete-body timing, medians/tails, stages, GC, allocation
profiles, memory, configurations, workflow IDs, artifact IDs, and ZIP SHA-256s.
Detailed intrusive retention/traversal data are preserved on the diagnostic branch
`diagnostics/issue60-buffered-graphs`. Harnesses are in `tests/performance/` there;
they are not part of the application PR. The profiling workflow becomes manual
only and pins final experimental source so documentation pushes do not retrigger
profiling. Workflow artifacts have seven-day retention; local ZIP copies remain
in the workspace parent (`issue60-buffered-*.zip`, `issue60-buffered-repeat-*.zip`,
and `issue60-buffered-final-*.zip`). No production credentials/private TLS keys
are included. **Issue #60 and Milestone 1 remain open.**

## PR #64 dependency audit correction (2026-10-22)

[Run 39838466447](https://github.com/rooster51/AlphaOS/actions/runs/39838466447),
web job 120032874295, failed at the unchanged
`npm audit --omit=dev --audit-level=moderate` command. Next.js 16.4.0 was
affected by [image optimization RCE](https://github.com/advisories/GHSA-2464-fhr4-w9xw),
[Server Actions denial of service](https://github.com/advisories/GHSA-p3m5-59mp-jv5r),
and [typed-array cache RCE](https://github.com/advisories/GHSA-673q-mjm6-r5xr).
All three advisories list **16.4.1** as the first patched 16.x version.
Although npm suggested 16.4.2, the smallest compatible correction is the exact
16.4.1 pin in both `web/package.json` and `web/package-lock.json`.

Only Next.js, its matching `@next/env` and platform SWC packages change in the
lockfile; its sharp dependency minimum becomes 0.35.5 (the existing lock already
resolves a sufficient version). React remains 18.3.1; supported peers and the
Node >=20.9.0 engine requirement remain compatible with CI Node 22. No routes,
application code, audit exceptions, deployment configuration, or Python code
change in this correction. React 18's existing Next.js 16 deprecation warning
is not a compatibility failure and is outside this patch's scope.

Validation on the corrected dependency tree:

- Clean `npm ci`; production audit: **zero vulnerabilities**.
- Full audit: only the existing Issue #41 development-tool advisories (two
  moderate, five high, zero critical); unchanged CI exception validation passes.
- **100 website tests**, **29 Chromium browser tests**, typecheck, and production
  build pass with Next.js 16.4.1.
- Buffered encoder contract/redaction/failure/lifetime tests: **13 passed**.
- Complete Python 3.12.14 suite: **1,184 passed + 64 subtests**, four existing
  SDK deprecation warnings, 511.64 seconds on the local Windows environment.
- All **16 complete-response SHA-256 hashes, byte sizes, and candidate/exclusion
  counts** match both main and pre-security-patch PR #64. These fixtures span
  SPY/QQQ, monthly/long-dated expirations, $150/unrestricted capital, and
  Auto/manual $5 widths. Byte identity includes exact economic outputs.

The performance measurements earlier in this report precede this dependency
patch. These checks establish compatibility and fixture parity, not production
latency acceptance. No merge or deployment was performed; **Issue #60 and
Milestone 1 remain open pending complete-response production validation**.
