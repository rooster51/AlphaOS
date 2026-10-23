# Issue 60 — native JSON bridge probe validation

**NO-GO for requesting temporary production diagnostic deployment.** Functionality and metadata privacy pass, but acceptably low overhead is not demonstrated across repeat trials. Leave the probe disabled and stop this instrumentation experiment. No additional variant is proposed.

Research baseline: `76a6a16`. Existing branch: `diagnostics/issue60-bridge-timing`. Tested application revision: `e567fb55ddbdafa3272bec974e2d93c53d400293`.

## Scope and observability

The single narrower probe (v3) calls native `response.json()` exactly once. It adds no response cloning, separate text/byte consumption, manual parsing, duplicate serialization or additional body buffering. The disabled path still calls native `response.json()` directly. Request schema validation, authentication, error classification, cancellation, the existing 12,000ms signal, full envelope validation and output construction are unchanged from the deployed research behavior.

V2 used `response.text()` plus manual `JSON.parse` and a per-request 20ms event-loop histogram. V3 removes both changes. The histogram's independent observer cost was not established, so event-loop monitoring is omitted rather than claimed free. This is diagnostic narrowing, not a research optimization or a revived JSON-wrapper reuse experiment.

V3 records monotonic request/fetch/header/combined-body-end/validation offsets; combined native body/decompression/UTF-8/JSON wall time; successful JSON completion; status; generated correlation ID; deadline elapsed/budget observation; actual timeout signal observation; and client cancellation. A numeric, bounded Content-Length is recorded only when present: it is declared upstream encoded size, not measured transfer/decoded bytes. No body is consumed to count bytes. A failed body/parse attempt records its elapsed interval with `body_json_completed=false`.

The combined interval includes scheduling, quota contention and GC. It cannot isolate transfer, decompression, decoding or parse CPU. Route completion precedes Next output compression/network delivery and browser rendering. Comparing the route log against external complete-body timings can locate a delivery gap, but cannot attribute it to a specific subsystem. Existing late-200 behavior is preserved; telemetry adds no post-parse deadline enforcement.

## Controlled real HTTP validation

Actual Next 16.4.1 production server and local TLS upstream, Node 24.21.0, Ubuntu runners. Backend and Next each limited to 0.15 CPU / 512 MiB with no extra swap. Internal Docker network prevents provider access. TLS verification remains enabled. No production service, provider request or historical capture was used.

Controls are deterministic opaque JSON with empty candidate arrays, not market data. Largest decoded upstream is 13,000,320 code units; its approximately 12.9 KB gzip representation is unusually compressible and not production-representative. Request timing ends at complete compressed HTTP body receipt; decompression/hash verification follows separately. Exact parity concerns complete decoded JSON bytes, status, error messages and cache policy, excluding dynamic IDs and compression framing.

Each independent trial has 72 completed HTTP requests plus two client aborts. Trials counterbalance enabled/disabled server order, with off first in trials 0/2 and on first in trial 1. Separate flag states run in separate fresh Next containers on the same runner; samples are not randomized request-by-request. Requests within a server pair are correlated.

Complete streams, delayed chunks, gzip, split multibyte/BOM input, malformed JSON, truncated EOF, interrupted connections, stalled headers, stalled bodies and downstream client aborts are checked. Success is 200; malformed/truncated/interrupted responses remain 502/schema mismatch; intentional deadline cases remain 502/backend timeout. Disconnected clients receive no response; backend cancellation and bridge 499 records are verified separately. Timeout-error bodies never count as successful research/deadline passes.

## Security and rollback

Instrumentation remains disabled unless server environment `ALPHAOS_BRIDGE_TIMING_PROBE` is exactly `1`; ordinary request parameters cannot enable it. Explicit log-key allowlists and credential/body/header canaries check metadata-only output. No credentials, authorization headers, quotes, bars, response bodies or arbitrary exception messages are logged. Generated TLS keys are excluded from CI artifacts. Controlled result artifacts retain hashes and numeric metadata only.

Rollback: leave/remove the flag (off by default). Removing source instrumentation would require a separately approved code deployment; no deployment or configuration action occurred here. No provider-data cleanup is needed. Issue #60 and Milestone 1 remain open.

## Paired complete-body results

Full validation run [40010959213](https://github.com/rooster51/AlphaOS/actions/runs/40010959213) and identical-code HTTP repeat [40011594792](https://github.com/rooster51/AlphaOS/actions/runs/40011594792), both on `e567fb5`. All six HTTP jobs passed: **432 completed HTTP responses (312 expected successes, 120 expected errors), plus 12 client aborts**. Every decoded-body/status/error/cache parity, timing-order, correlation and log-privacy check passed. Client aborts preserve upstream cancellation and bridge 499 classification. Both flag states preserve native timeout classification for stalled headers and bodies, without counting timeout errors as successes.

Milliseconds; each trial has 12 concurrent samples per flag. Percentiles use nearest rank `ceil(0.95*n)`; per-trial p95 equals worst at this sample size.

| Run / trial | Off median | On median | Difference | Off p95/worst | On p95/worst |
|---|---:|---:|---:|---:|---:|
| Full / 0 | 2177.05 | 2174.46 | -2.59 | 2570.22 | 2669.93 |
| Full / 1 | 1575.37 | 1385.52 | -189.85 | 1881.55 | 1880.10 |
| Full / 2 | 1585.06 | 1428.87 | -156.19 | 1881.61 | 1970.73 |
| Repeat / 0 | 1871.37 | 1866.22 | -5.15 | 2064.60 | 2275.09 |
| Repeat / 1 | 2455.68 | 2667.07 | +211.39 (+8.61%) | 2781.12 | 2971.75 |
| Repeat / 2 | 1965.28 | 1578.32 | -386.96 | 2182.55 | 2278.38 |

| Pooled sample per flag | Off median / p95 / worst | On median / p95 / worst | Off / on successful under 12s |
|---|---:|---:|---:|
| Warm concurrent, n=72 | 1881.58 / 2772.52 / 2781.12 | 1866.22 / 2672.28 / 2971.75 | 72/72 / 72/72 |
| Warm sequential, n=36 | 1076.08 / 1572.85 / 1773.24 | 984.58 / 1600.10 / 1676.91 | 36/36 / 36/36 |
| First request, n=12 | 2900.18 / 4201.90 / 4201.90 | 3094.45 / 4613.20 / 4613.20 | 12/12 / 12/12 |

All 156 expected successes per flag finished under 12 seconds. These are controlled diagnostics, **not production research acceptance**. The fixtures are far from the real production deadline, so equal pass counts do not establish near-deadline noninterference.

First-request medians changed sign across pairs. Repeat trial 1 was 4197.68ms off versus 4599.22ms on (+401.54ms, +9.57%). Launch-to-health ranges were 3.231–5.151s off and 3.082–5.266s on, separately measured and including container/client startup/readiness; they do not measure Render activation. Peak Next memory ranged 261.8–314.4 MB, with no OOM events.

V2's concurrent median differences were -7.89 / +129.65 / +65.39ms; its pooled off/on median was 2469.85/2553.51ms. V3 has a smaller pooled median difference (-15.36ms), but **demonstrably lower overhead is not established**: the unchanged repeat produced a +211.39ms pair, cold samples worsened in three pairs, and tail differences remain. The full-run gzip pair in trial 2 also rose from 1547.97 to 1993.56ms (+445.59ms). No unfavorable scenario is excluded from the numeric report.

These observed differences cannot be attributed entirely to instrumentation. Different workflow runs use different runners; even paired separate containers differ in JIT/GC/cache state and CPU-quota phase. The old/new disabled baselines also differ substantially. Only six independent server pairs exist, and pooled request observations are correlated; no tight causal confidence interval or negligible-overhead bound is claimed. Route-only baseline/off/on medians also vary, across AMD EPYC 7763, 9V45 and 9V74 runners. Those controls preserve response hashes but do not substitute for real HTTP evidence. HTTP runner hardware was not independently recorded.

## Diagnostic value, checks and decision

Enabled combined native body/JSON wall-time medians were **1098.47ms** for large warm concurrent streams, **903.91ms** for delayed chunks and **1768.03ms** for gzip controls. Correlation and deadline/abort observations remain useful; splitting parsing or adding another decompressor is unnecessary for that coarse view. Removing event-loop sampling loses attribution to event-loop delay, which the previous per-request histogram could not uniquely assign to GC, parsing or quota contention anyway.

Full CI passed on the tested revision: **Python 3.12.14: 1,184 tests + 64 subtests; 108 website tests; 29 browser tests; typecheck; production build; `npm audit --omit=dev --audit-level=moderate`: zero vulnerabilities**. All three route-only controls passed. Focused tests prove exactly one native JSON call, no clone/text/ArrayBuffer access, unchanged exception identity, incomplete-body telemetry, disabled behavior, UTF-8/BOM semantics, schema/error parity and deadline noninterference. No dependency or backend/research-engine changes were made. Subsequent edits are documentation/numeric results only.

Numeric evidence: `performance/bridge-http-v3-summary.json`. Downloaded artifact ZIP SHA-256 values were checked against GitHub artifact metadata before analysis; digests are retained in `performance/bridge-http-v3-artifacts.json`. Reproduce with the existing manual workflow on this branch; full mode runs all regressions/audits, `http_only=true` repeats unchanged HTTP validation.

**Recommendation: NO-GO.** Native consumption and useful metadata visibility pass; the no-meaningful-overhead criterion remains unproven, particularly cold and concurrent tails. Leave disabled, do not request production diagnostic deployment on the basis of these results, and stop here. No new instrumentation variant, PR, production setting change, merge or deployment is recommended. Issue #60 / Milestone 1 remain open; this controlled test cannot close production acceptance.
