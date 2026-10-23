# Issue 60 — real Next HTTP probe validation

**Historical v2 report.** The current native `response.json()` v3 evaluation is [native JSON validation](ISSUE60_BRIDGE_NATIVE_JSON_VALIDATION.md). V3 also received NO-GO; the original evidence is retained below.

**Decision: NO-GO for requesting production diagnostic enablement under the current no-meaningful-regression criterion.** Functional, cancellation, privacy and timing-order checks pass. Observer overhead remains variable and is not established as negligible near the production deadline. Leave the probe disabled; do not treat control-fixture deadline passes as research acceptance. Issue #60 / Milestone 1 remain open.

Existing branch: `diagnostics/issue60-bridge-timing`; research baseline `76a6a16`. Current tested probe revision: `4fb30878e438d33d6525e76dde5b960049ca46fa`. No new branch, research optimization, provider request/data capture, PR, merge, production configuration or deployment.

## Actual HTTP setup

Three independent Ubuntu CI runners, off/on order counterbalanced (off first in trials 0/2, on first in trial 1). Each trial launches the real **Next 16.4.1 production server**, local Node HTTPS backend and separate HTTP client on an **internal Docker network**. The backend and Next each have **0.15 CPU**, **512 MiB RAM**, and no extra swap. Node **24.21.0**; generated local CA trust is supplied explicitly, with certificate verification enabled. No external provider is reachable from the isolated test network. Build/package downloads occur before the tests, outside their measured request path.

Bodies are deterministic opaque JSON controls with empty candidate arrays, not invented market observations. Largest decoded upstream text is **13,000,320 code units**. The gzip controls advertise only **12,883–12,886 compressed bytes**: this compression ratio is not representative of production market-data graphs. Do not infer production performance from these fixtures.

Per trial: 72 completed HTTP requests, plus two deliberately aborted client connections. Across three trials: **216 completed requests**, of which **156 are expected successes and 60 expected error responses**, plus six client aborts. Each flag state includes 36 warm concurrent and 18 warm sequential successful full-body samples. Client timings run from HTTP request initiation through complete compressed response-body receipt; decompression/hash checking follows separately. Exact parity compares the complete **decoded UTF-8 JSON response bytes**, not dynamic correlation headers or transport/compression framing.

## Functional results

| Controlled case | Off/on result |
|---|---|
| Complete streamed 13 MB response | HTTP 200; exact decoded response hash/length parity |
| Delayed chunks | HTTP 200; exact body parity; observable body/JSON boundaries |
| Gzip upstream | HTTP 200; identical decoded body; decompression remains inside body consumption |
| BOM and multibyte UTF-8 split into single-byte writes | HTTP 200; native decoding/JSON semantics preserved |
| Malformed JSON | Same HTTP 502 / `response_schema_mismatch`, exact error-body parity |
| Truncated EOF and abrupt connection interruption | Same HTTP 502 / `response_schema_mismatch`; no partial successful output |
| Headers stalled 13 seconds | Same HTTP 502 / `backend_timeout`, original 12,000ms signal observed |
| Body stalled 13 seconds | Same HTTP 502 / `backend_timeout`, original 12,000ms signal observed |
| Client socket closed at ~500ms | Backend peer closed after ~494.6–495.1ms from its request start in both modes; bridge records 499; disconnected client received no response, not a successful 499 delivery |

All response/error/status parity and correlation checks pass. Every completed response ID links to the local backend; successful bridge records confirm backend correlation. Disabled mode emits no probe records. Enabled records pass an explicit metadata-key allowlist, timing boundaries are monotonic, and credential/body/header canaries never appear in Next logs. Only counts, hashes, timings, enums and IDs are retained in CI artifacts; generated TLS keys/certificates are excluded.

## Necessary diagnostic-only changes

1. Initial harness failures occurred before research endpoint testing: host readiness could not reach the internal-network origin, then a one-shot client raced CPU-limited origin startup. Moved the client inside the isolated network and added readiness polling. No TLS or outbound-network protection was weakened.
2. A timeout check incorrectly required an independently sampled monotonic counter to reach exactly 12,000ms whenever the native signal fired. One native abort was observed at **11,999.509ms** on that counter. Validate actual signal/error behavior separately from the wall-clock observation; no deadline/timer was changed. The existing `deadline_budget_exceeded` field remains a monotonic observation, not a claim about signal state or an extra enforcement step.
3. Original probe v1 (`arrayBuffer` + explicit TextDecoder) showed concerning full-HTTP overhead. V2 uses Fetch's native `response.text()` then times `JSON.parse`; it no longer claims an independent UTF-8 duration or measured wire-byte count. It records `body_decoded_ms`, `body_read_including_decompression_utf8_ms`, **UTF-16 code-unit count**, and a separately labeled numeric **declared Content-Length**, rejecting arbitrary header text. Unit coverage proves code units are not confused with bytes. Normal disabled behavior still uses original `response.json()`.

V2 is a change to diagnostics only, not JSON reuse/stringify optimization. Complete envelope validation and output construction remain unchanged. The smaller explicit body-materialization path is not claimed as a proven causal speedup: old/new workflow runs use different hosts, and original v1 repeat trials also varied in sign.

## Paired completion measurements: v2

Milliseconds, complete HTTP body. Twelve concurrent samples per mode/trial; six sequential samples per mode/trial.

| Trial | Concurrent off median | On median | On minus off | Sequential off / on median |
|---|---:|---:|---:|---:|
| 0 | 2279.46 | 2271.57 | -7.89 (-0.35%) | 1122.31 / 1325.79 |
| 1 | 2421.05 | 2550.70 | +129.65 (+5.36%) | 1273.66 / 1321.50 |
| 2 | 2552.32 | 2617.71 | +65.39 (+2.56%) | 1486.04 / 1321.18 |

| Pooled warm sample | Off median / p95 / worst | On median / p95 / worst |
|---|---:|---:|
| Concurrent, n=36 each | 2469.85 / 3167.67 / 3269.24 | 2553.51 / 2946.84 / 2973.37 |
| Sequential, n=18 each | 1227.26 / 1860.97 / 1860.97 | 1325.51 / 1798.81 / 1798.81 |

Warm successful control deadline passes: **36/36 concurrent and 18/18 sequential per flag**. Intentional timeout/error bodies are excluded. All 78 expected successful responses per flag (including first/delayed/gzip/unicode controls) completed within 12 seconds. These are control successes, not production research acceptance.

Original v1 full-HTTP first-set on-minus-off concurrent medians were **+110.36 / +438.75 / +485.78ms**. A separate v1 repeat was **+0.73 / +304.67 / -198.59ms**. V2 does not eliminate uncertainty. Only three independent v2 runner/server pairs exist; requests inside one pair are correlated, so a pooled median is not a tight causal confidence bound. Hardware/GC/CFS phase differences and capture/readback overhead cannot be assigned separate causal shares from these tests.

Next cold launch-to-health: off **4.651 / 5.149 / 5.227s**, on **4.577 / 4.967 / 5.167s**. Includes container/client startup and readiness polling, not Render activation. First full request bodies ranged **3.098–4.492s off**, **2.808–4.395s on**; these are separate from launch-to-health. Do not label them production cold-start timings. Peak Next cgroup memory: **251.4–278.9 MB**, no OOM events. The CPU cap/throttling and memory files are retained; physical HTTP-runner CPU model was not recorded, limiting cross-run comparison.

## Timing usefulness and limits

In enabled warm concurrent controls, median body receipt/decompression/native UTF-8 time was **1398.05ms** and separately timed JSON parse **97.65ms**. Delayed small-body controls showed **901.25ms** body consumption and **0.50ms** parse. These are wall-clock measurements under quota, not parse CPU costs. Gzip decoding cannot be measured independently through native Fetch without introducing another decompressor; no such path was added.

Node event-loop delay is measurable on the real I/O path: delayed-body controls had median sampled max **21.40ms**, while large concurrent controls had **395.58ms**. Median sample counts were **43.5** and **6**, respectively. Other overlapping work, quota throttling, GC and synchronous wrapping affect the process-wide histogram. It cannot attribute delay solely to JSON parsing, measure its own cost independently, or guarantee coverage of the final blocking interval. Zero samples remains null, not zero latency.

Client headers/full-body completion and route completion are distinct. Probe completion precedes Next output compression and network delivery. The probe does not separately measure TLS, decompression, UTF-8 decoding, output gzip, browser parsing or rendering. No timeout guard was added after synchronous parsing: existing late-200 behavior remains possible. Do not describe the diagnostic as fixing deadline enforcement.

## Validation, reproducibility and decision

Current run: https://github.com/rooster51/AlphaOS/actions/runs/40008496780. **All jobs passed** on `4fb3087`: all three HTTP trials, **1,184 Python tests + 64 subtests**, **107 website tests**, **29 browser tests**, typecheck, production build, production dependency audit and the three route-only overhead controls. No application changes followed this tested revision; subsequent edits document the evidence only.

Prior v1 repeat: https://github.com/rooster51/AlphaOS/actions/runs/40007961584 (all three HTTP trials passed after correcting the timing assertion). Initial failures are retained rather than silently omitted. Artifact ZIP digests were checked against GitHub metadata before analysis. Numeric final summary: `performance/bridge-http-v2-summary.json`.

Reproduce on Linux: run the existing manual `Issue60 isolated bridge probe validation` workflow on this branch, or `TRIAL=0 python tests/performance/bridge_http_lifecycle.py` with Docker, requests and cryptography installed. The workflow `http_only` input reruns focused HTTP checks after harness-only changes; full mode also runs existing regressions/audits and route controls. No production keys or market data are required.

**NO-GO under the requested acceptance standard:** semantics/security are validated, but no-meaningful-latency-regression is not established. Two v2 trials have higher concurrent medians, one by ~130ms; sequential differences also change sign. Tail timings improve in this control but cannot prove near-deadline noninterference on production graphs. Do not request approval on a claim of negligible overhead.

**One next step:** review a still narrower diagnostic scope that leaves native `response.json()` consumption intact and accepts a combined body/decode/parse interval, retaining only correlation/deadline/event-loop observations. That sacrifices decomposition; it is a design decision for this same branch, not an implemented new optimization. No production approval is requested now. Rollback remains flag absent/off; remove the helper/calls only in a separately approved code deployment. No data cleanup is required because this probe never persists provider payloads.
