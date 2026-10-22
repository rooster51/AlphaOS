# Issue 60: constrained full-research lifecycle investigation

Date: 2026-10-22 UTC. Issue #60 and Milestone 1 remain open. No production PR,
merge, deployment, timeout, configuration, subscription, or safety-policy change
is proposed by this investigation.

## Finding and decision

The constrained reproduction identifies CPU contention over large research
object graphs as the dominant measured mechanism. Payoff construction and
sanitization consume substantially more CPU than JSON encoding. Cyclic garbage
collection adds significant CPU work, including scans of live graphs. The website
then decompresses, decodes, parses, and re-encodes the full response under its own
CPU quota. Its measured "body reading" is consequently not pure network latency.

A real source-level retention defect was found: `sanitized()`'s recursive `clean`
closure retains itself, its normalization caches, and source arrays until cyclic
GC. Breaking that closure after its return value is computed releases the graph
earlier without changing response values. This experimental correction reduces
retained memory and GC work, but **does not reliably improve complete website
responses**. Cold requests regress and warm concurrent deadline passes only move
from 6/12 to 7/12. It does not qualify for a production PR.

This establishes a reproducible CPU mechanism, not an exact decomposition of the
original production failures. Actual provider authentication/network latency,
Render's shared-host scheduling, edge transfer, and Next framework overhead are
not reproduced. No claim of production acceptance follows from these fixtures.

## Production evidence versus experimental evidence

Previously captured production observations remain unchanged:

| Case | Complete response | Result |
| --- | ---: | --- |
| SPY monthly unrestricted Auto Width | 13.885 s | Website timeout |
| QQQ monthly unrestricted Auto Width | 14.033 s | HTTP 200, over deadline |

SPY request `46aa57ce02bc48a2a65f1dbd989b56a6` recorded 3.997 s payoff
processing. QQQ request `54cd0c0ae79d4f0180a12860fd1e743b` recorded
4.507 s serialization and 2.349 s website body reading. These are production
measurements; the tables below are diagnostic fixture measurements.

Read-only Render metrics around that failure window report both services at
0.15 CPU and approximately 512 MiB memory. Backend memory samples were roughly
207-231 MB and website samples 142-177 MB; 30-second CPU samples cannot resolve
individual request contention. See `performance/issue60-render-resource-metrics.json`.
Render's website build log explicitly reports Node 24.21.0.

## Reproduction and instrumentation

Baseline: `ff0a42efe74f964733cd2f0ea79e7456a1e862c8` (PR #63).
Experimental profiling source: `2007503bbead117303b27dde11f4dc20c1e44056`.
[Completed Linux profiling run](https://github.com/rooster51/AlphaOS/actions/runs/39718452069).

Three independent Linux jobs start with SPY, QQQ, or a simultaneous pair. Each
compares baseline and candidate in the same Python image on the same runner,
alternating variant order between jobs. Every variant has a fresh backend and
website process. Each process receives its own cgroup limit of 0.15 CPU,
512 MiB memory, and no additional swap. An uncapped CPU control retains the
512 MiB memory limit. Python is 3.12.14; Node is exactly 24.21.0. The quotas apply
before interpreter imports. Docker inspection, cgroup counters, package versions,
request IDs, and individual response measurements are retained in the artifacts.

Fixtures use verified/checksummed archives with 2,820 contracts over ten
expirations and 1,260 history rows, with a frozen historical clock. Requests use
monthly expiration `2030-01-18`, unrestricted capital, and default Auto Width.
Archive metadata/storage and history network calls are stubs; SDK dependency
imports and actual archive verification, constructors, payoff calculations,
normalization, sanitization, redaction, JSON encoding, and gzip remain exercised.
Authentication is synthetic; live provider initialization/authentication time is
not measured. These are diagnostic inputs, not market evidence or recommendations.

After the initial cold request(s), each process runs two sequential SPY/QQQ
rounds, two simultaneous SPY/QQQ rounds, and a direct REST pair. "Cold" means
first research after health readiness; interpreter boot and Render idle wake are
excluded. Separate tracemalloc passes measure allocations and are excluded from
latency comparisons. Earlier Node 22 runs are exploratory and are not used in
the principal tables here.

The bridge invokes the actual website POST handler through a small HTTP adapter,
with the existing 12-second abort signal. This is not a Next production server
or browser rendering benchmark. Backend TLS uses a trusted local test certificate;
Render terminates TLS differently. Direct diagnostic clients allow long reads
to observe completion; the website timeout is never changed. Client completion
ends after the complete response body has arrived; external diagnostic-client
JSON parsing is separately measured and excluded.

Instrumentation distinguishes wall time and thread CPU for Python stages,
gzip body compression, ASGI send duration, cgroup CPU throttling/memory events,
per-generation GC callbacks, Node body read/decode versus JSON parsing, response
construction, bridge completion, and process memory. Node process CPU can include
the peer request and V8 worker threads. Nested stages and GC overlap; do not add
their medians or overlapping process CPU intervals as exclusive totals.

## Before/after complete-body timings

Seconds; median [minimum, maximum], population standard deviation. Warm samples
span three fresh-process experiments, not twelve independent machines. HTTP 502
timeout responses are excluded from successful-body timing distributions but
included in pass counts and the machine-readable measurements. HTTP 200 alone is
not a deadline pass.

| Workload | Baseline | Experimental closure cleanup | Under 12 s, before / after |
| --- | --- | --- | --- |
| Uncapped, warm sequential (12 each) | 0.962 [0.635, 1.039], SD 0.155 | 0.905 [0.602, 0.961], SD 0.129 | 12/12 / 12/12 |
| Uncapped, warm concurrent (12 each) | 1.591 [1.030, 2.146], SD 0.369 | 1.603 [0.978, 2.165], SD 0.400 | 12/12 / 12/12 |
| Limited, warm sequential (12 each) | 6.759 [4.665, 7.953], SD 1.040 | 6.607 [4.374, 7.724], SD 1.237 | 12/12 / 12/12 |
| Limited, warm concurrent (12 each) | 10.495 [8.175, 13.383], SD 1.701; 8 HTTP 200 | 10.732 [6.524, 13.129], SD 2.040; 9 HTTP 200 | **6/12 / 7/12** |
| Limited, cold first requests (4 each) | 11.518 [10.213, 12.200], SD 0.724 | 12.356 [11.519, 12.528], SD 0.395 | **3/4 / 1/4** |
| Limited, direct REST concurrent (6 each) | 9.492 [7.845, 11.792], SD 1.458 | 9.757 [6.138, 10.524], SD 1.778 | 6/6 / 6/6 |

Among eight matched warm concurrent pairs where both variants returned HTTP 200,
five improved, three worsened. Median paired change was -1.76%, ranging from
-20.19% to +18.42%. Two prior deadline failures passed, but one prior pass failed.
Every matched cold request worsened (median +7.81%). The different direct REST
median and median paired improvement (-10.94%) illustrate substantial variability;
neither is a reliable website improvement. Do not substitute successful-only
medians for the failed responses.

Baseline warm concurrent per-process outcomes (SPY-first / QQQ-first / pair-first)
were respectively 1/4, 1/4, and 4/4 deadline passes. Candidate outcomes were 1/4,
2/4, and 4/4. GC scheduling and process history materially affect results.

## Lifecycle breakdown

Baseline constrained medians across research requests (including cold/direct
requests); wall milliseconds and Python thread CPU milliseconds:

| Stage | Wall ms | CPU ms | Interpretation |
| --- | ---: | ---: | --- |
| Archive read/verify/decode | 84.0 | 11.92 | Stubbed storage; real production retrieval not represented |
| History load | 193.5 | 15.17 | Stubbed HTTP; cold SDK import shown separately below |
| History features | 301.5 | 26.47 | Actual fixture calculations |
| Width enumeration | 88.5 | 4.48 | Small relative to payoff and graph transformation |
| Candidate payoff | 2,055.5 | 186.92 | Includes construction of many full research objects |
| Candidate comparison | 99.5 | 12.12 | Actual fixture comparison |
| Historical economics | 195.0 | 18.52 | Actual fixture economics |
| Complete research execution | 3,818.0 | 343.93 | Parent stage; not additive with its children |
| Sanitization/redaction | 2,296.6 | 245.09 | Recursive graph transformation and allocations |
| JSON encoding | 103.7 | 16.31 | Native encoder, not dominant |
| Gzip compression | 266.2 | 34.60 | Per-request aggregate including flush calls |

Warm sequential versus concurrent baseline wall medians rise from 2,307.5 to
4,640.5 ms for execution, 1,400.5 to 2,603.5 ms for payoff, and 2,004.6 to
2,958.6 ms for sanitization. Corresponding CPU medians do not double. Together
with the uncapped control and throttling counters, this demonstrates requests
competing for the same backend CPU budget. Example baseline limited process:
719 of 783 CPU periods throttled, 69.199 seconds cumulative throttled time.
This counter covers the process lifetime, not one request.

Cold history SDK import in the single-symbol starts takes 795-801 ms wall,
109-112 ms thread CPU, versus effectively zero in warm requests. In the cold pair,
both callers wait about 496 ms; only one spends meaningful import CPU because
the other waits on import synchronization. Cold imports contribute but cannot
explain recurring warm failures. Production's earlier 2.1-2.2-second import
measurement is not replaced by this fixture measurement.

Website Node process medians, constrained baseline:

| Phase | Wall ms | Process CPU ms |
| --- | ---: | ---: |
| Backend body read, gzip decode, UTF-8 decode | 762.6 | 121.15 |
| Backend JSON parse | 601.6 | 90.77 |
| Combined body reading/parsing | 1,420.2 | 220.95 |
| Website response construction | 410.6 | 64.58 |

These process CPU intervals can include a concurrent peer. Even so, pure
network transfer is not an adequate explanation for the body-read duration.
ASGI send-await median for warm concurrent baseline was 1.44 ms on the local
network, with gzip bodies 811,127-811,157 bytes. This measures application sends,
not Render edge/WAN delivery. Body read/decode includes transfer and cannot isolate
those costs on production without additional production tracing.

## Allocations and garbage collection

Across constrained baseline processes, 45 generation-2 collections consumed
5,941.9 ms thread CPU / 41,919.9 ms wall and collected 2,651,124 objects. Candidate:
44 collections, 4,130.1 ms CPU / 29,027.0 ms wall, 1,461 objects collected. These
are cumulative totals across different process lifetimes, not per-request deltas.
GC CPU is already included in enclosing stage CPU. Many collections remain even
after unreachable response retention is fixed because live graphs still need
scanning; globally disabling GC or changing thresholds is not a justified fix.

Constrained cgroup peak memory fell from 295,677,952 to 248,229,888 bytes; process
peak-RSS reports were 383,725,568 versus 337,305,600 bytes. Cgroup and process
accounting use different scopes; neither indicates an OOM. All measured cgroup
OOM counters and container OOMKilled flags were zero/false.

Separate uncapped tracemalloc passes showed baseline peaks 118.63-118.90 MB,
candidate peaks 95.33-96.09 MB. Baseline end snapshots retained about 99.54-99.55 MB;
candidate snapshots about 9.30-25.95 MB depending on overlap. Baseline allocations
include 20.8 MiB of sanitizer dictionaries, 8.1 MiB of sanitizer lists, and
substantial payoff/position objects. Snapshots and tracing change timing and
must not be used as latency benchmarks. Immediate cleanup also moves some
deallocation work into the response path, so lower retained memory does not
automatically imply faster first responses.

## Response size and website field audit

Every successful response in a case is compared across modes and variants using
a canonical digest of **all fields**. Integral JSON float/integer spelling is
normalized solely because JavaScript round-tripping spells `1.0` as `1`; no
fields are dropped. Saved baseline/candidate SPY and QQQ response objects match
in each of the three jobs. Full economics, provenance, diagnostics, and safety
outputs therefore match for this workload. Payload size is unchanged: successful
website bodies are approximately 12.54 MB decoded; backend gzip is about 0.811 MB.
No payoff, width, quote, freshness, authentication, or archive-validation logic
was modified by the experiment.

An earlier captured production QQQ monthly session contains 13,408,641 compact
JSON bytes: candidates 12,256,036 (91.4%), comparison 1,127,891 (8.4%), and small
market/history/diagnostic roots. `MarketResearchPanel.tsx` uses both accepted and
capital-excluded candidates through `market-candidates.ts`. Candidate raw-details
views call `JSON.stringify(research, null, 2)` eagerly, including collapsed details.
The panel does not directly consume the session-level comparison and
historical_comparison roots, but deleting them would require an explicit website
contract and preserve access elsewhere. They account for too little payload to
assume a complete solution. Most candidate fields remain accessible through raw
details, so they cannot simply be declared unused. Browser render CPU is a
separate unmeasured cost and does not explain server bridge timeout by itself.

## Validation, artifacts, and next action

All checks on the experimental source passed: **1,173 Python tests + 64 subtests**
(four existing SDK deprecation warnings), **100 website tests**, **29 browser
tests**, typecheck, and production build. Two new lifetime tests prove source-array
release with GC disabled for both response shapes while checking redaction and
source immutability. These are diagnostic-branch changes, not a production PR.
Full-suite success is not production acceptance for live archive/freshness cases.

Source harnesses are `tests/performance/lifecycle_backend.py`,
`lifecycle_bridge.mjs`, and `run_lifecycle.py`. The diagnostic workflow is retained
for manual runs only after this report to avoid automatic repeated profiling.
The run above has three artifacts (`SPY`, `QQQ`, `pair`), with seven-day retention.
Local ZIP copies are retained in the workspace parent as
`issue60-node24-SPY.zip`, `issue60-node24-QQQ.zip`, and `issue60-node24-pair.zip`.
The durable `performance/issue60-resource-profile-summary.json` contains every
measurement/request ID, distributions, CPU/GC/memory aggregates, configuration,
artifact IDs and ZIP SHA-256 values. Provider credentials/private keys are absent.

Recommended next action: a narrowly bounded **non-production experiment** that
reduces repeated candidate graph construction/traversal while preserving the full
REST/MCP JSON contract. Require repeated paired complete-body wins on both cold
and concurrent cases before proposing it. The measured targets are payoff object
construction and recursive normalization/sanitization, not native JSON encoding.
Do not ship this closure cleanup solely on its memory benefit, remove full
research fields, weaken sanitization, disable GC globally, or increase timeouts.
Exact attribution of the remaining production transfer/provider portions remains
open. Issue #60 and Milestone 1 cannot close.
