# Release 2.0 Milestone 1: historical timeout investigation

Refs Issue #49. Based on main `168fd853` (merged PR #51), October 20, 2026.
**Diagnostic-only change: the production bottleneck is not established.** No
timeout increase, speculative cache, concurrency restriction or research change.

## Production evidence (measured, not fixtures)

Read-only Render application-log inspection used the previously authorized
workspace and the existing backend/website services. No configuration, secret,
infrastructure or deployment was read or changed to obtain these records.

At `2026-10-20T04:42:00Z`, the website logged both historical requests at
`stage=fetch`, status 502, `elapsed_ms=12001`:

- QQQ: `56b8e0536a9f46a6bf73bbc7ec8ffead`.
- SPY: `b9f31d924b5d4fdc923b3a99f3a40d1e`.

Backend log inspection for `04:40–04:50Z` returned five current-mode stale
failures, including 2,899 ms and 2,801 ms at `04:41:47Z`, but no correlated
records for those historical IDs. A correlation-ID search from `04:42Z` through
the inspection time likewise returned only the two website records. Existing
code logs backend failures only, not arrivals or successful completions. Thus
absence of a backend record **does not establish non-arrival or cancellation**.
`stage=fetch` means no response headers had been received by the bridge; it
cannot distinguish connect/TLS, server queueing or backend work before headers.

Four new live read-only requests were executed through the public website's
existing `POST /api/research/market` with explicit historical mode and no client
credentials. Durations below are client wall latency, including internet/TLS,
website and backend processing; HTTP bodies were not retained in the repo.

| Condition | Symbol | HTTP status | Measured ms | Website request ID |
|---|---|---|---:|---|
| Independent, first | SPY | 200 | 7,611 | `baef2bf44fe245ddb1467c76eb6f8a15` |
| Independent, second | QQQ | 200 | 5,696 | `99cb3a723e1c46b1a94bd71c6669e39d` |
| Concurrent pair | SPY | 200 | 10,994 | `14ee2868bf0a4efe8f2dab7234bf9284` |
| Concurrent pair | QQQ | 200 | 9,353 | `beab789d2b0d4105893abe39b8b07419` |

The concurrent pair completed in 11,002 ms wall time. This is one small,
order-dependent sample, not a load test, latency percentile or performance
improvement. The slower concurrent pair suggests possible shared-resource
effects but **does not prove contention** or isolate CPU, dependency latency,
cold starts or SDK initialization. These probes confirmed HTTP success only;
they did not validate every returned candidate or independently verify archive
contents. No live OAuth MCP verification is claimed.

There are **no before/after production timings** for this patch because it has
not been deployed. The successful probes used the unchanged production code.

## Call path and timeout inventory

`DashboardResearch` -> `loadDashboardResearch` -> existing website bridge
`POST /api/research/market` -> authenticated FastAPI
`POST /v1/research/market` -> `ArchiveResearchService.run` ->
`read_latest_option_snapshot` -> Supabase metadata query and Storage download ->
SHA-256 check -> gzip decode/JSON -> archive identity/quality validation ->
Public completed daily history -> `run_latest_market` normalization/calendar/
classifier -> existing candidate/payoff/capital/historical-economics pipeline ->
sanitization/JSON response. Current stale checks exit before download and research.

| Boundary | Configured behavior |
|---|---|
| Dashboard -> website | 14,000 ms AbortSignal per request, unchanged. A stale current error initiates a separate explicit historical request. |
| Next bridge -> backend | 12,000 ms AbortSignal across fetch and body read, unchanged; no retries. Safe timeout response remains 502/`backend_timeout`. |
| FastAPI endpoint | Synchronous worker-thread endpoint; no application-wide execution deadline. One Uvicorn process/worker does not mean only one sync endpoint thread. |
| Supabase client | `create_client` without timeout overrides. Inspected local Supabase 2.31.0 defaults: PostgREST 120 s, Storage 20 s. Production manifest allows `>=2.6,<3`; its exact installed version/defaults were not reverified. These SDK values are not an end-to-end request budget. |
| Public SDK | Pinned 0.1.17; underlying `ApiClient` defaults to a 30 s request timeout and three retries. Auth initialization/account retrieval and daily-history requests can each perform network work. urllib3 retries/backoff can extend total time beyond one timeout. |
| Local archive verification, parsing, calculations | No explicit deadline; synchronous CPU work. |
| MCP -> REST | In-process HTTPX ASGI transport, default HTTPX I/O timeout configuration; it does not impose an end-to-end deadline on sync research computation. Same backend pipeline. |
| Render proxy/network | Not reconfigured or independently characterized by this investigation. |

Dependency timeout budgets can exceed the website budget. That is a confirmed
configuration relationship, **not proof** that a particular dependency caused
the observed incident. The Supabase SDK and Public transport timers include
network work that these application-level spans cannot split into DNS, connect,
TLS and server processing. No transport hooks, credential-bearing network debug
logs or speculative timeout adjustments are introduced.

## Diagnostics added

- `modules/research_timing.py`: request-local ContextVar with sanitized opaque
  correlation ID, fixed stage names, start/end records, elapsed/duration ms,
  safe outcome/status, validated SPY/QQQ and mode, and process-local counts of
  requests/executions in progress. No bodies, URLs, keys, hashes, paths, objective
  text, quotes or exception text are emitted. Stages are inactive outside a
  traced research request. The dedicated WARNING logger works with the existing
  warning-level entrypoint; these events are timing records, not error claims.
- An outer ASGI observer logs arrival before auth/worker dispatch, response
  headers, completion, observed disconnect and propagated cancellation. It
  delegates every receive/send message unchanged except replacing an invalid
  correlation header with the same sanitized ID used by the existing boundary.
  It never consumes an extra receive or adds a competing disconnect poller.
- Service and archive spans cover client creation, metadata query/validation,
  download, checksum, decompression, JSON decode and payload validation.
- Public-history spans distinguish context lookup (including cold SDK/auth
  initialization and accounts request), token refresh and provider request.
  Existing cache, authentication and fallback/error behavior are untouched.
- Calculation spans distinguish normalization, calendar, history features,
  classification, candidate/economics orchestration and historical economics.
  `response_serialization` measures sanitization/JSON construction separately.
- The bridge now logs safe completion timings on successes as well as failures,
  with validated symbol/mode, unchanged 12,000 ms budget, header wait, body read
  and schema-validation durations. HTTP status alone never promotes evidence.

Stage durations are nested; **do not add overlapping spans**. Arrival-to-
execution includes body/auth/validation/thread dispatch, not a pure queue metric.
Request completion means the app completed the ASGI response path, not proof the
remote client received all bytes. Inflight counters are per process, not fleet
metrics. A disconnect is claimed only if ASGI actually supplies `http.disconnect`;
an upstream proxy may not forward it promptly, and some paths may never read it.

## Cancellation and concurrency: fixture evidence

Deterministic fixture tests execute SPY and QQQ independently and concurrently
through actual REST handlers and verified fake storage. A barrier proves two
history-load executions overlap; correlation contexts remain isolated and the
full responses equal their independent results. This rejects an application-wide
serialization assumption locally, not dependency/production contention.

An actual ASGI cancellation test blocks a sync archive reader, cancels the client
task, and releases the reader independently. The reader and research execution
can finish under the same ID while cancellation unwinds; the cancellation still
propagates. Starlette/AnyIO can shield a worker during unwinding. Python thread
work is not preempted by cancelling its awaiting task. Another ASGI test supplies
an observed disconnect and verifies transparent message delivery and diagnostics.
These controlled tests **cannot determine whether the original production IDs
arrived or were cancelled**. No synthetic "client disconnected" event is inferred
merely from a 12-second duration or missing completion.

Injected archive-download timeouts still return sanitized 503 archive-unavailable
and do not proceed to checksum/history/research. Concurrent website timeout tests
keep two IDs isolated and assert the actual 12,000 ms signal factory argument;
they simulate cancellation rather than waiting 12 seconds. Browser coverage shows
both historical timeouts retain stale warnings, correlation, navigation and refresh
controls, without any displayed price, candidate or live label.

## Validation and limitations

Validation uses the existing Windows Python 3.12.14 and Node 24.20.0 environment.
Test timings are fixture/environment measurements, not market latency or an SLA.

| Command/check | Result |
|---|---|
| `python -m pytest -q --tb=short --basetemp=../historical-timing-full-final-temp` (repository/tests on PYTHONPATH) | **916 passed, 64 subtests passed in 414.26s** |
| `python -m pytest tests/test_research_timing.py tests/test_public_history.py tests/test_public_observations.py tests/test_public_research.py -q --tb=short --basetemp=../historical-timing-final-focused-temp` (repository/tests on PYTHONPATH) | **49 passed, 35 subtests passed in 17.01s** |
| Timing tests with `logging.disable(logging.CRITICAL)` before `pytest.main`, `--basetemp=../historical-timing-logger-isolation-temp` | **9 passed in 7.96s** |
| `cd web; npm test` | **87 passed** |
| `cd web; npm run typecheck` | **Passed** |
| `cd web; npm run build` | **Passed** |
| `cd web; npm run test:e2e -- --workers=2` (unchanged rerun) | **23 passed in 10.6s** |

Existing React 18 deprecation, Node module-type and browser color warnings remain.

An initial browser run had 19 passes and four navigation/connection failures.
Both its elapsed time and the concurrent targeted Python run's elapsed time jumped
to approximately 11 hours during a local execution interruption. The unchanged
browser rerun passed all 23 tests in 10.6 s; no assertions or timeout limits were
relaxed. The interrupted Python run passed 127 tests but its 40,306.57 s elapsed
figure is not a usable benchmark. Two early diagnostic test iterations also
caught/fixed an instrumentation naming collision and corrected a cancellation
test that incorrectly expected Python worker preemption. A mistyped provider test
filename produced no tests; the corrected command is used for final validation.
The first full Python run had 910 passes and six new timing-log assertion
failures: earlier UI tests changed process-wide logging state, so those tests
captured no timing records. The new module now explicitly enables/captures its
own logger, following the existing OAuth diagnostics test pattern; it retains
all log/privacy/cancellation assertions. The final full rerun passed all 916
tests and 64 subtests; a separate run with logging deliberately disabled before
pytest also passed all nine timing tests.

No research result schema, archive selection, checksum/provenance gate, historical
eligibility, 600-second freshness rule, provider, endpoint, authentication, secret,
Render setting or infrastructure changed. The dashboard's behavior is unchanged;
the additional browser regression protects genuine historical failures.

## Next investigation after separately authorized deployment

1. Observe a fresh pair of explicit historical calls independently, then one
   concurrent pair. Match website and backend IDs; do not treat absent records
   from an undeployed diagnostic patch as evidence.
2. If arrival exists, compare execution start, last started stage and matching end
   durations. Separate slow metadata/download/history calls from calculations and
   serialization. If no arrival exists, investigate the connection/proxy boundary.
3. Inspect observed disconnect/cancellation and later worker completion under each
   ID. Absence of disconnect does not prove the client remained connected.
4. Only then propose the smallest measured fix at the demonstrated bottleneck.
   Keep integrity and deadlines intact unless evidence supports a specific budget
   change. No such behavioral fix is claimed in this PR.
