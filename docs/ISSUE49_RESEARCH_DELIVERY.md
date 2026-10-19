# Issue #49 — Milestone 1 research delivery

Base: `fcfbc07e721b0fd8b7f05081b109d2de4caf0ba7` (main after readiness audit).
Scope: reliable, evidence-qualified SPY/QQQ delivery only. No strategy, pricing,
classification, collector, database, dependency, secret or deployment changes.

## Findings and root-cause limits

The audit recorded website HTTP 502 `backend_service_unavailable`. Tracing
`web/src/app/api/research/market/route.ts` proves that this code requires a
received upstream HTTP 5xx response without a more specific recognized error.
Fetch timeouts and TypeError/network failures map to `backend_timeout` and
`backend_unreachable`, respectively. Recognized archive/auth/internal backend
errors have their own mappings. The existing safe response collapsed the original
upstream HTTP status and provided no cross-service request correlation.

Consequently the audit does **not** establish whether those production responses
came from a gateway, application, cold start, storage issue or resource pressure.
No production logs with correlation existed in the audit captures. This PR does
not claim to eliminate the intermittent upstream 5xx. It makes the next failure
investigable without exposing credentials or hiding real failures.

A separate reproducible defect was confirmed: the fetch-only timeout catch did
not cover a DOM `TimeoutError` while consuming a success or error response body.
That could escape the bridge's classified error handling. The outer boundary now
maps that failure to the existing `backend_timeout`, including Fetch body-read
`AbortError` when the original timeout signal confirms expiry. It retains the **12,000ms**
AbortSignal and does not add retries, stale fallback, provider substitution or
historical-mode fallback. Deterministic tests inject both body-timeout cases.
This is not asserted to be the root cause of `backend_service_unavailable`.

## Minimal correlation and safe diagnostics

The bridge generates a 32-lowercase-hex opaque `X-AlphaOS-Request-ID`, forwards it
to the backend and includes it in normal handled bridge responses. Research
backend responses echo a valid ID or generate a replacement if input is invalid.
IDs are diagnostics, never authorization. Existing bearer authentication remains.

Only failures are logged:

- Website `research_bridge`: generated ID, fixed stage (`request_validation`,
  `fetch`, `response_body`, `schema_validation`), final HTTP status, elapsed ms;
  when headers arrived, upstream status, application/json content-type boolean,
  whether the backend echoed the ID, and a **fixed allowlist** of upstream codes
  or `unrecognized_or_missing`. Unexpected errors get a fixed outcome diagnostic
  and continue to propagate as before; exception text is not added to these logs.
- Backend `alphaos_api.research` / `research_request`: ID, HTTP status, elapsed ms
  and fixed error code or category, scoped to POST `/v1/research/market`.

No headers, URLs, bodies, objective, symbol/contract data, credentials, provider
responses or exception messages/stack traces are included in the added records.
The browser error JSON remains the existing sanitized status/code contract. Full
successful research envelopes are unchanged. Invalid/early middleware rejections
outside the research handler may not carry a backend correlation marker; absence
of an echo is **not proof** that no backend code ran (headers can also be stripped).

After a separately authorized review/deployment, capture the browser response ID,
then match website and backend failure records. A non-JSON upstream 503 without
an echo differs from a correlated application error; it still requires logs or
platform evidence to locate the source. Do not inspect raw tokens or dump bodies.
A backend timeout may outlive a disconnected client; this change does not claim
to cancel sync Python provider work or change its resource lifecycle.
No deployment or new live verification of these changes occurred in this PR.

## Routing correction (diagnostics only)

A controlled completed-history fixture reproduces mixed EMA ordering (direction
unknown) with a prior-range breakout. Existing routes are `long_option`,
`directional_debit_spread`, `directional_bwb`; all require known direction to
resolve a supported family. This is not invalid option geometry or insufficient
capital. Existing policy intentionally does not broaden a nonempty unresolved
route list into the no-routes quote-research fallback.

`opportunity_session` now reports `no_supported_constructor_route` as the
zero-candidate/blocking reason for that automatic-discovery case. Routing-stage
reason counts enumerate the unresolved route count in route units. Construction,
economics and capital remain `not_attempted`. Direction stays unknown; no
constructor, quote, capital rule or fallback changed. Existing valid SPY results,
unknown/no-route debit hypotheses and genuine bad-quote/capital exclusions retain
their original behavior. The existing website renderer displays the new reason
and stage status without adding frontend classification or pricing.

A REST-generated controlled fixture is checked exactly through REST/OAuth MCP,
the website bridge and browser renderer. Fixture history/quotes are software test
data, not production evidence. No real observations were fabricated as fixtures.

## Source schema parity and OAuth boundary

Current source MCP `run_market` argument properties and required fields already
match `MarketRequest` exactly, including `research_mode` enum
`current|historical` and default `current`. A deterministic runtime schema test
now protects this equality; there was no source-level mode drift to repair.
The website now also rejects unknown/null backend mode labels for current requests,
instead of accepting any value except historical; legacy omitted-current labels
remain compatible. Existing default-current, explicit-historical, invalid-mode, evidence-envelope
and SPY/QQQ parity tests remain intact, along with all 17 MCP tools/19 REST operations.

The audit's connected app declaration omitted `research_mode` and required
reauthentication. Refresh/reconnect is user-controlled. Source changes cannot
refresh a cached remote connector declaration or authorize a session. Live OAuth
MCP remains **NOT VERIFIED**; no secrets, scopes, consent or auth bypass changed.

## Validation and remaining blockers

Final validation on the existing Windows/Python 3.12.14 and Node 24.20.0 environment:

| Check | Result |
|---|---|
| `python -m pytest -q --tb=short --basetemp=../issue49-full-temp` with repository/tests on PYTHONPATH | **901 passed, 64 subtests passed in 436.93s** |
| `python -m pytest tests/test_research_delivery.py -q --tb=short --basetemp=../issue49-focused-complete-temp` | **9 passed in 5.40s** |
| `npm test` | **69 passed, 0 failed, 0 skipped** |
| `npm run typecheck` | Passed |
| `npm run build` | Passed |
| `npm run test:e2e -- --workers=2` | **16 passed in 8.4s** |
| `git diff --cached --check` | Passed |

Existing tests are retained; none were weakened or skipped. Node module-type,
React 18 and browser color-variable warnings remain. No isolated dependency
installation or production validation is claimed. New coverage includes unknown-direction breakout across both
symbols and modes; exact website fixture parity; missing/invalid correlation;
archive/auth/unexpected backend failures; 500/502/503/504 upstream statuses,
non-JSON and unknown-code sanitization; no automatic retry/recovery masking; and
response-body timeout classification. Browser coverage asserts routing reasons
and unreached capital stage alongside all previous navigation/research cases.

Remaining release blockers: diagnose the actual intermittent upstream 5xx with
new correlated evidence after a separately authorized deployment; user OAuth
reauthentication and live schema/parity verification; a bounded repeatability/SLO
observation window. This PR is reviewable Milestone 1 source work, not a claim
that production reliability or live MCP acceptance is complete.
