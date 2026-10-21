# Issue #60: response completion and dashboard observation contract

Base: latest main `b9697ebe` (merged PR #62). **Not deployed. Milestone 1 acceptance
remains open.** The website bridge deadline remains 12,000 ms.

## Confirmed cause versus remaining uncertainty

The complete correlated backend and website traces are recorded in
[production evidence](performance/issue60-dashboard-production.json).

| Historical request | Execution | Cold dependency import (nested) | Serialization | Backend headers | Website completion |
|---|---:|---:|---:|---:|---|
| QQQ `6f341a5de5564c6ba4deea04679ea085` | 8,568 ms | 2,109 ms | 2,394 ms | 11,564 ms | 12,202 ms, timeout while reading body |
| SPY `fa9ae134f6ae4acdb7453b9a6963b1f9` | 8,678 ms | 2,217 ms | 2,694 ms | 11,667 ms | 12,008 ms, timeout while reading body |

Do not add nested stages. Actual provider history HTTP calls took 377/714 ms;
SDK initialization/account validation and history coverage checks were separate.
Backend headers before 12 seconds were insufficient: transfer/decompression,
JSON body parsing, validation and bridge re-encoding still had to finish.

The dashboard consumes only underlying spot, original observation/session time,
expiration, provider, archive verification and freshness metadata. It was requesting
the full classifier/candidate/historical-economics workflow and downloading large
responses it did not display. That unnecessary work includes the cold SDK import.
The dedicated research page and MCP actually consume full research and keep it.

## Explicit, additive contract

`POST /v1/research/observation` accepts only:

```json
{"symbol":"SPY","research_mode":"historical","expiration":"2031-01-17"}
```

`research_mode` defaults to `current`; expiration is optional and follows the
existing archive selection default. An explicit unavailable date returns
`archive_expiration_unavailable`, never a substituted date. Capital, width,
objective and unknown parameters are rejected rather than silently ignored.
The route uses existing owner authentication, no-store/correlation, compression,
request-local cancellation and timing middleware. Its OpenAPI response model is
`ObservationResponse`, with `schema_version=alphaos-observation-v1` and explicit:

```json
{"read_only":true,"verified_for_trading":false,"research_performed":false,
 "evidence_scope":"archive_observation_only"}
```

The response includes symbol/mode, selected expiration, spot, original `as_of`,
`requested_as_of`, authoritative NYSE session bounds, archive provider/session,
storage identity/path/SHA256, freshness, quality diagnostics/warnings and caveats.
It contains no candidates, classifications, capital eligibility, payoff economics,
probability, EV or recommendations. Missing candidate arrays are intentional;
they do **not** mean zero candidates were found. The underlying observation is
not claimed to be a closing price, executable quote or a fresh provider quote.

The same trusted archive reader verifies checksum, metadata/payload identity,
collection/observation times and current freshness before projection. The existing
adapter validates expiration/contract context and retains quality rejection counts.
Session bounds and current-expiration rules remain enforced. The projection does
not load history, initialize/authenticate a provider client, or run calculations
that the dashboard cannot use. No evidence or observations are cached/replaced.
Cold subprocess tests establish that this path does not import `public_api_sdk`.

**Full research remains the default:** `/v1/research/market`, all existing explicit
endpoints and MCP tool names/parameters retain their contracts. Auto Width, manual
width, $150/no-limit capital checks, all supported families, monthly/long expirations,
verified quote provenance and evidence-quality controls are unchanged. Full research
still authenticates with the existing Public SDK and applies the same historical
schema/coverage/OHLC validation. We did not rewrite authentication, drop historical
checks, or claim that full-research SDK cold startup has disappeared.

The website bridge explicitly selects observation mode via
`{"symbol":"SPY","research_mode":"current","view":"observation"}` and strips
`view` before forwarding to the observation endpoint. Omission retains the full
research path. Width/capital/objective cannot be combined with observation view.
The shared website validator checks version/scope flags, symbol/mode/date identity,
session, provider, hash and freshness consistency. Observation data cannot pass as
full research. The dashboard retains its stale-current warning and separate,
historically labeled fallback; its legacy full-response parser remains compatible.
The research page still requests full research.

Deploy the backend before the new frontend after approval: an older backend lacks
the additive endpoint and returns a visible unavailable state to the new dashboard.
It does not silently fall back to an expensive full request. Older frontend/REST/MCP
clients continue using the unchanged full endpoint.

## Serialization work

Both REST responses and MCP's text representation use pinned **orjson 3.13.0** for
encoding **after** the existing normalization/redaction walk. No secret/key filtering,
nonfinite handling or legacy scalar conversion is bypassed. Arbitrary-size legacy
integers fall back to the original strict stdlib JSON semantics. Economic JSON
values match before/after; whitespace/float spelling and content lengths can differ.
MCP's additional defense-in-depth sanitization is retained. Compression remains
gzip level 1 with the same negotiation, now also covering the observation route.
This is a free application dependency, not infrastructure or a provider change.

The largest saving is avoiding an unused multi-megabyte research response and its
construction/normalization/encoding/compression on the dashboard. Full research
normalization is still necessary and large no-limit responses remain expensive.

## Local measurements — synthetic, not production acceptance

Both revisions used the same 2,820-contract-per-symbol, ten-expiration, 141-strike-
per-side synthetic archive fixtures and 1,260 synthetic daily bars. Real SHA256,
archive decoding/validation, REST/middleware, gzip and complete client JSON reads
were exercised; archive/history boundary delays were 20 ms and five dummy values
exercised redaction. **Provider network, real SDK cold imports, host quotas and real
market quotes are not represented by these fixtures.** Round zero uses a fresh
process/calendar cache and round one is warm. Process CPU includes benchmark client
decoding/equivalence hashing. These figures must not be compared to earlier PRs'
different runs as if hardware/scheduling conditions were identical.

Four concurrent SPY/QQQ/SPY/QQQ requests; seconds, min–max across each round:

| Case | Before full, cold / warm | After full, cold / warm | Observation, cold / warm |
|---|---|---|---|
| Historical $150 Auto | 2.18–2.86 / 1.93–2.62 | 1.55–2.16 / 1.59–2.36 | 0.245–0.246 / 0.075–0.102 |
| Historical $150 manual $5 | 0.48–0.51 / 0.33–0.38 | 0.47–0.50 / 0.35–0.37 | 0.254–0.255 / 0.071–0.073 |
| Historical no-limit, late | 3.24–4.19 / 3.41–4.69 | 2.55–3.73 / 2.65–3.71 | 0.258–0.260 / 0.050–0.107 |
| Historical monthly Auto | 2.07–2.84 / 1.81–2.25 | 1.35–1.93 / 1.52–2.16 | 0.250–0.252 / 0.076–0.077 |
| Historical long-dated Auto | 1.64–2.28 / 1.83–2.50 | 1.56–2.33 / 1.91–5.24 | 0.248–0.249 / 0.069–0.093 |
| Current $150 Auto | 4.36–5.23 / 2.15–3.01 | 1.43–1.99 / 1.40–1.76 | 0.249–0.251 / 0.075–0.076 |
| Independent SPY current | 0.616 / 0.543 | 0.705 / 0.533 | 0.231 / 0.036 |
| Independent QQQ current | 0.662 / 0.459 | 0.521 / 0.354 | 0.209 / 0.036 |

Observation columns are a **different scope**, not accelerated full research. The
manual/capital labels identify the full comparator; observation requests do not
accept or evaluate those knobs. All full before/after economic/quote/identity/count/
classification/safety digests match across 14 cases (both modes, individual and
concurrent). Individual calculation timings vary even though math is unchanged;
the long-dated warm outlier and independent SPY result preclude a claim that every
individual full request became faster.

Median serialization spans: historical $150 Auto **473 → 191 ms**, no-limit
**1,003 → 714 ms**; observation serialization rounded below 1 ms. Full response
size is essentially unchanged: $150 about **5.50 MB decoded / 312 KB compressed**;
no-limit about **13.03 MB / 825 KB**. Observation is **2.16 KB / 0.97 KB**, independent
of capital/candidate count. No-limit batch CPU was 5,250/5,312 → 4,703/4,625 ms;
the observation batches were 219/78 ms (cold/warm).

A separate seven-run bridge-only experiment passed decoded synthetic backend JSON
through the **actual Next POST handler**, its validation and JSON construction,
then read the entire returned body. Median completion was **108.35 → 0.65 ms**,
12.90 MB full versus 2.22 KB observation. This excludes backend execution, real
network/TLS and browser rendering; do not sum it with overlapping REST spans or
present it as real website latency. Browser tests cover both compact symbol cards,
current/historical labels and continued full research controls.

Raw timings/stages, payloads, CPU/RSS, equivalence digests and bridge scope are in
[fixture measurements](performance/issue60-dashboard-benchmarks.json). Reproduce
REST measurements using `python tests/benchmark_research_pipeline.py
--production-scale --mode historical`, adding `--capital none --late`, `--width 5`,
`--expiration 2030-01-18`, `--expiration 2031-01-17`, or
`--concurrency 1 --symbol SPY` / `QQQ`; add `--endpoint observation` for its explicit
scope. Omit `--mode historical` for current mode.

## Validation

The complete Python suite passed: **1,171 tests and 64 subtests**, in 301.44 seconds,
with four existing Supabase SDK deprecation warnings. Website validation passed:
**100 unit tests, 29 Chromium browser tests, TypeScript typecheck and production
Next build**. `git diff --check` passed. All 14 full-research benchmark cases retained
identical economic and safety digests before and after. These are local fixture
and regression results, not post-deployment production acceptance evidence.

## Production acceptance checklist (open)

- After an approved deployment, verify reviewed commits in both services; backend
  first. Confirm fresh complete SPY/QQQ archives during regular NYSE hours.
- Correlate dashboard requests with `/v1/research/observation`: no history import,
  provider auth, classifier or candidate work; flags explicitly deny research.
- Verify both cards in current mode and after-close historical fallback, preserving
  observation time, stale-current warning, source/quality and unavailable states.
- Independently and concurrently exercise the full research page, REST and MCP:
  $150 Auto, no capital limit, manual $5, monthly and long expirations. Retain exact
  economics, exclusions, visible search bounds and unavailable POP/EV.
- Measure repeated cold/warm **complete website response bodies**, not headers,
  with meaningful margin below 12 seconds on the actual Render allocation.
  Full SDK/provider startup and large full responses remain production risks.
- Exercise corrupt/missing/stale archives, unavailable expiration, quote-quality
  failures and client aborts; require fail-closed results and isolated cancellation.
- Do not close Milestone 1 until these production checks pass. No timeout, secrets,
  infrastructure, subscription or deployment configuration changes are included.
