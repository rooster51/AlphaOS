# Release 2.0 Milestone 1: dashboard evidence delivery

Issue #49 follow-up, based on main `4087218` (PR #50). No Milestone 2 work.

## Confirmed source-level cause

The dashboard called `getMarketSnapshotServer`, which requests legacy
`GET /v1/market/{symbol}` and a matching `/v1/structure/{symbol}` snapshot.
It did not use archive-backed `POST /v1/research/market`. The legacy fetcher
reduces unsuccessful HTTP responses to an availability exception; additional
missing-ID and failed-evidence checks throw plain `Error`. The dashboard caught
only `ResearchUnavailableError`, so those validation errors could escape and
replace its main content. The page could not handle archive-specific errors or
display explicit historical archive context through this path.

The user reported production health success, historical research success,
`503 archive_stale` for current requests, and October 19 SPY/QQQ archives.
These production facts were **not independently reverified** in this change.
No assertion is made that the legacy dashboard itself returned `archive_stale`;
the source trace demonstrates its separate contract and uncaught-error boundary.

## Smallest safe approach and resulting behavior

No new backend behavior is required: existing `research_mode=historical`
retains checksum, identity, quality and provenance checks while permitting old
observation dates. The existing classifier returns authoritative NYSE session
bounds, including early closes, in its time-state evidence. The UI does not
infer a calendar from weekdays or invent a closing snapshot.

- The dashboard shell renders independently of per-symbol browser requests to
  the existing `/api/research/market` bridge. Credentials remain server-side.
- Each card first explicitly requests `research_mode=current`. Only a sanitized
  `archive_stale` error initiates one separate historical request. Authentication,
  connectivity, unsupported research, missing/corrupt archives and invalid
  successes never trigger historical fallback.
- Successful responses must match symbol, mode, schema and read-only markers;
  archive provider, symbol, session date and observation timestamps must agree.
  Quality must be complete/partial consistently, checksum metadata must be
  present, and the observed spot must be finite and positive. This is additional
  presentation validation, **not** browser-side cryptographic verification;
  the authoritative archive reader still verifies actual bytes.
- Current evidence must satisfy the returned freshness limit, at most 600
  seconds. The browser also checks observation age and invalidates an open
  card when the earlier of its observation-age or returned age budget expires.
  Expiry hides the price and asks the user to refresh; it does not poll or retry.
- Historical display requires explicit historical modes, a null current-age
  ceiling and backend-supplied session bounds. The observation must be inside
  that session and the session close must precede both backend request time
  and browser time. Missing/inconsistent evidence fails closed.
- Historical cards prominently say **HISTORICAL — COMPLETED SESSION ARCHIVE**,
  explain that an intraday observation from an ended session is not a closing
  price, and display source, timestamp, New York session date, archive age at
  request and archived expiration. The stale-current warning remains visible.
- Cards display only an observed underlying price and provenance. Neither mode
  enables live-only signals, POP, EV, candidate trades or recommendations.
  Existing Market Research/Strategy Explorer historical behavior is unchanged.
- Errors use fixed safe messages. The bridge's validated opaque correlation IDs
  remain visible for failed current/historical requests. Raw backend bodies,
  exception strings and credentials never enter UI messages.

## Validation

Windows, existing Python 3.12.14 and Node 24.20.0 environment; no dependency changes.

| Command | Result |
|---|---|
| `python -m pytest tests/test_after_hours_research.py tests/test_archive_read_path.py tests/test_research2_api.py tests/test_research_delivery.py tests/test_website_mcp_parity.py -q --tb=short --basetemp=../dashboard-reliability-python-temp` with repository/tests on PYTHONPATH | **118 passed in 37.20s** |
| `cd web; npm test` | **86 passed**, including 17 new dashboard tests |
| `cd web; npm run typecheck` | **Passed** |
| `cd web; npm run build` | **Passed** |
| `cd web; npm run test:e2e -- --workers=2` | **22 passed in 8.0s**, including 6 new dashboard tests |

**CODE VERIFIED:** request paths, safe error handling, unchanged server auth,
archive integrity/freshness rules and existing research semantics.
**FIXTURE VERIFIED:** SPY/QQQ current success, stale/historical delivery,
completed-session eligibility, provenance rejection, expired-open-card behavior,
backend outage/authentication/unsupported states, independent symbol cards,
real bridge authentication/correlation and existing REST/MCP parity. Browser
tests mock the existing HTTP contract using clearly synthetic deterministic
archive fixtures and controlled clocks; they are not live quote verification.
The full Python suite was not rerun for this frontend-only change; the listed
archive, after-hours and parity suites were run without skipping or weakening tests.
Existing React 18 deprecation, Node module-type and browser color warnings remain.

## Limits and deployment follow-up

No production request, live OAuth MCP session, deployment or Render inspection
was performed. The October 19 production snapshots' exact content and whether
their returned metadata satisfies this UI's checks remain **NOT VERIFIED**.
Post-deployment verification requires a separately authorized deployment and
actual current/historical requests; this PR does not claim production acceptance.

Historical mode verifies **the latest archive only**. If the latest archive's
session has not ended, is missing or invalid, the dashboard remains usable but
shows no historical price. It does not scan older rows or silently select a
different archive. If selection of a previous completed session becomes required,
the smallest backend migration would be an explicit completed-session selection
contract with authoritative calendar bounds and the same per-record verification,
shared by REST/MCP and the website. That behavior is not introduced here.
No collector scheduling gap is repaired by this display fix. A healthy `/health`
alone does not establish current archive availability.
