# Issue 60: disabled metadata-only website bridge probe

Baseline: `76a6a1696d007aeb6aab31fa33c6dad847608688`. Isolated branch: `diagnostics/issue60-bridge-timing`. Application/test revision measured: `47723be70429db1696fd818d791ac3ec79acabf9`.

**Recommendation: NO-GO for enabling in production yet.** Correctness tests pass, but the enabled probe changed concurrent median latency by up to ~101ms (20.2%) in one constrained control trial. No full Next-over-HTTP constrained measurement was run. Review/accept the observer overhead and its limits before requesting deployment approval; do not interpret these controls as SPY/QQQ research acceptance. No runtime optimization, provider request/data capture, timeout increase, PR, merge, deployment, or production configuration change occurred. Issue #60 and Milestone 1 remain open.

## Existing path and design

The 12,000ms AbortSignal is created in the bridge fetch-options evaluation, after request parsing/config checks and request-body JSON construction. It is combined with the browser request signal. Fetch resolves at upstream headers. Native Fetch decodes/decompresses the response; baseline `response.json()` then consumes the body and parses JSON. The bridge validates the envelope, wraps the full research with `Response.json`, and returns to Next. Timeout/body errors preserve the current fixed error classification. A timer cannot preempt synchronous parse/wrapper work, so the baseline can return HTTP 200 after the nominal deadline; this diagnostic does not fix or hide that behavior.

The backend computes, sanitizes/encodes the full response before emitting, then compression/server/proxy delivery occurs. Existing correlated backend final-ASGI-send timing is not end-to-end website receipt. No backend code changed: use its existing request IDs/stage records for correlation.

Probe activation: server environment **`ALPHAOS_BRIDGE_TIMING_PROBE=1`**, otherwise off, including when absent. No request parameter or header can enable it. No credential/endpoint/contract additions. Nothing is configured in Render by this branch.

Disabled: existing native `response.json()` is retained for both success/error bodies; no monitor or new probe log is created. A static helper/module import and environment check remain, so zero cold overhead is not claimed.

Enabled: use `response.arrayBuffer()` to mark full decoded body receipt, decode with UTF-8/BOM handling, then `JSON.parse`, matching Fetch JSON's data semantics. Record schema-validation completion and route completion. Preserve existing validation, output wrapper, timeout creation, combined signal, errors and failure-before-response behavior. Do not reuse raw JSON in the output or skip stringify/validation. This is a diagnostic split, not the rejected validated-JSON optimization.

The request-local monitor uses Node `monitorEventLoopDelay` at 20ms resolution, removed/disabled at completion. It is not per-request CPU time: other overlapping work affects it. A request that only yields microtasks can finish before histogram samples run; report `event_loop_samples=0` and null delay instead of claiming zero event-loop delay. Histograms may miss the final blocking parse interval before completion.

## Output and limits

One extra `research_bridge_probe` JSON record when enabled, alongside unchanged `research_bridge` records:

| Field | Meaning |
|---|---|
| request_id | Existing server-generated correlation ID, also forwarded to backend and response |
| fetch_started_ms / headers_received_ms | Offsets from probe start, not absolute wall timestamps |
| body_received_ms / decoded_body_bytes | Complete decoded upstream body; null/missing if incomplete |
| body_read_including_decompression_ms | Body consumption including native Fetch decompression and scheduling |
| utf8_decode_ms / json_parse_ms | Separate enabled-path decode and parse wall time |
| parsed_ms / validated_ms / elapsed_ms | Completion boundaries; last is route return preparation, not final HTTP/client receipt |
| deadline_elapsed_ms / deadline_budget_exceeded | Monotonic observation against original 12,000ms budget; never enforces a new cutoff |
| timeout_signal_aborted / timeout_observed_ms / client_aborted | Original signal state and observed timeout callback offset |
| event_loop_samples / event_loop_delay_max_ms | Node histogram sample count and sampled maximum, null with no samples |
| status / event / version | Fixed diagnostic envelope and response status |

No URLs, headers, errors/messages, objective, raw inputs, chains, history, response bodies, request payloads or credentials are passed to the diagnostic logger. Byte counts describe **decompressed** bytes; no fabricated wire-byte or independent decompression timing is emitted. TLS/proxy transfer, decompression and scheduling cannot be separated by this hook. Wrapper construction, Next gzip, outgoing transfer, browser parsing and rendering are not independently measured. Existing client complete-body measurements remain necessary.

## Validation

- Local website: **106 tests passed**, including six probe-specific tests; typecheck and production build passed; **29 browser tests passed**; production dependency audit (`npm audit --omit=dev --audit-level=moderate`) found zero vulnerabilities. Dependencies unchanged. Local Node 24.19.0.
- Focused coverage: disabled native-only body consumption/no probe logs; on/off byte/status/cache parity; schema rejection and upstream errors; BOM, invalid UTF-8, duplicate keys/negative zero, malformed JSON; partial bodies; client/timeout abort classification; observation of exceeded deadline while preserving late success; unexpected errors and log canary non-exposure. Tests retain the exact 12,000ms timeout argument.
- Local Python: 1,178 passed + 64 subtests; six setup errors from inaccessible default Windows pytest temp directory. Rerun of those six with an isolated `--basetemp` passed (6/6). No Python implementation changed. Linux full-suite result is authoritative and linked below.
- Isolated GitHub Actions run: https://github.com/rooster51/AlphaOS/actions/runs/40003253857. **All jobs passed**: Linux Python **1,184 tests + 64 subtests** in 294.32s; website **106 tests**, browser **29 tests**, typecheck/build/production audit, and all three constrained overhead trials. The full run concluded success on application/test commit `47723be`.

The test responses contain controlled opaque padding and empty candidate arrays, **no market observations**. These tests do not establish economics parity on real captured data; exact pass-through/full-envelope byte parity plus unchanged research source prevent a claim that the probe independently revalidated production economics.

## Measured observer overhead

Three Ubuntu runners; separate containers for pristine baseline, candidate flag off, candidate flag on; counterbalanced order. Node **24.21.0**, CPU quota **15000/100000 = 0.15 core**, memory/swap cap **536870912 bytes**, network disabled. Route functions invoked directly with a controlled 13,000,301-byte upstream JSON body, streamed in 64KiB chunks. Complete returned wrapper bodies were consumed and SHA-256 checked against the same expected bytes. This includes route response construction/readback, but **not actual Next HTTP/network/compression lifecycle**. No research or provider was invoked.

Each mode/trial: one first pair, three sequential pairs and six warm concurrent pairs. All 36 warm concurrent bodies per mode passed byte/status integrity and completed within 12s; that is an opaque-control result only. Artifact ZIP hashes were matched to GitHub artifact digests before analysis. Raw artifacts contain only controlled metadata; no provider data.

| Trial | Pristine concurrent median | Flag-off median | Flag-on median | On minus off |
|---|---:|---:|---:|---:|
| 0 | 795.14ms | 898.31ms | 896.42ms | -1.89ms |
| 1 | 502.30ms | 500.25ms | 601.07ms | +100.82ms |
| 2 | 696.77ms | 692.64ms | 704.40ms | +11.76ms |

| Mode | Pooled concurrent median | p95 | Worst |
|---|---:|---:|---:|
| Pristine | 696.77ms | 996.29ms | 1004.18ms |
| Flag off | 692.64ms | 1098.32ms | 1105.09ms |
| Flag on | 701.95ms | 1002.53ms | 1010.51ms |

Do not use pooled medians to erase paired variability. Sequential flag-on medians were 402.88/299.61/390.03ms versus off 409.07/299.53/305.01ms. Enabled median CPU per concurrent pair was 144.24/98.20/117.63ms versus off 147.86/88.20/110.41ms; overlapping per-request CPU measurements were not summed. Cgroup peak memory across modes/trials was **314.5–349.2 MB**, with no OOM events. Quota throttling was present in nearly every CFS period, expected for these CPU-capped controls; it does not establish Render's instantaneous behavior.

Cold module import wall times: pristine 600.86/397.75/394.57ms; off 691.86/495.66/490.96ms; on 695.13/497.52/592.86ms. First-pair completion ranged roughly 0.606–1.302s across modes/runners. These are process/import/request costs, **not Render activation or cold Next startup**. Disabled import overhead is not proven negligible. Full machine-readable per-trial summary: `performance/bridge-probe-overhead-summary.json`.

## Deployment review / rollback

Do not deploy from this branch now. Before an approval decision, review whether the measured ~100ms occasional overhead and body-consumption substitution are acceptable for a metadata-only diagnostic, and validate with controlled actual Next HTTP streaming/abort behavior if proceeding. Keep provider-data retention/capture excluded. No optimization benefit is asserted.

If separately approved later: deploy website-only code with flag absent/off, verify normal parity, then explicitly approve a short enabled window on already-authorized traffic. Backend/Next versions, quotas, timeout, authentication and research contracts stay fixed. A server-only flag exposes no data to users but causes instrumentation overhead on all bridge requests while enabled; there is no operator-only per-request sampling mechanism in this minimum prototype.

Rollback: set flag off/remove it only with separate production-config authorization; no data/bucket cleanup is necessary because the probe retains no payloads. Revert the route import/calls and remove helper on a separately approved deployment. Keep existing normal timing/correlation logs. No such actions were performed here.
