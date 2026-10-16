# Release 1 after-hours archive research

## Production diagnosis (October 15, 2026)

Authenticated POSTs to `https://alphaos.onrender.com/v1/research/market` for
SPY and QQQ with `available_capital: 150` returned HTTP 503 and
`error.code: archive_stale`. Paired website requests to
`https://alphaos-web-staging.onrender.com/api/research/market` returned HTTP 502
and `code: archive_stale`. Authentication succeeded far enough to reach archive
validation; missing data, corruption and response-schema rejection were not the
error reported by these requests.

The configured default current archive ceiling is 600 seconds. The external
scheduler dispatches `.github/workflows/intraday-archive.yml`; the documented
heartbeat is every five minutes on weekdays, 13:00–21:59 UTC. The collector's
authoritative NYSE calendar gate collects only during the regular session and
rejects collections that finish after close. Heartbeats outside that session do
not produce new snapshots. An archive therefore ages out normally after close.
The external scheduler's live configuration was not inspected or changed.

The first website probes reproduced `backend_http_error`; a subsequent direct
probe timed out before successful paired requests returned `archive_stale`.
Render logs show the backend starting during this interval. The exact upstream
status/body behind the initial generic message is not established by available
logs. A temporary gateway/startup failure is plausible, not confirmed. The
bridge now maps non-JSON HTTP 5xx responses to a safe service-unavailable message,
and maps known API configuration, internal, endpoint and rate-limit errors
specifically, without returning upstream text or credentials.

## Shared contract

REST `POST /v1/research/market` and OAuth MCP `run_market` accept:

```json
{"symbol":"SPY","research_mode":"historical","available_capital":500,"expiration":"2026-10-15"}
```

The expiration above is an example request, not a statement of archive
availability. Explicit unavailable expirations are rejected; they are never
replaced. SPY and QQQ are the only supported symbols.

- `research_mode: current` is the default. The existing finite freshness ceiling,
  latest-snapshot selection and request-date expiration gate remain enforced.
  An error never triggers an automatic retry using older data or historical mode.
- `research_mode: historical` must be explicitly requested. It selects the same
  latest available persisted snapshot, allowing its age to exceed the current
  ceiling and its expiration to precede today's request date. It does not search
  backward for a better, complete or matching-expiration snapshot.
- Both modes verify the same SHA-256, payload, identity, path, quality and temporal
  availability rules before using the existing `run_market` engine. Missing,
  corrupt or inconsistent archives still fail closed. No broker fallback, archive
  mutation, synthetic quote, ranking or new strategy is introduced.
- Both return `research.research_mode`, original `as_of`, separate
  `requested_as_of`, archive source, expiration and archive age at request time.
  Historical freshness reports `max_age_seconds: null`, meaning no current-age
  ceiling was applied, not that the observation is fresh or executable.
- Historical research still evaluates history, DTE, structures and economics
  relative to the original observation. Loading newer daily bars does not move
  the research cutoff forward. Existing missing-evidence limitations remain.
- `available_capital`, when provided, must be a finite positive JSON number in
  both interfaces. It is an expiration max-loss ceiling, not broker buying power.

The website mode selector requires an explicit Run Research submission. Result
labels follow the returned request, not an unsent control change. Historical
results prominently state that candidates are not current trading opportunities
or executable quotes. Current mode remains strict even on weekends and holidays.

## Validation and release

Focused regressions cover regular hours, after close, weekend and NYSE holiday
requests; active-session freshness expiry; expired historical structures;
checksum, identity, finish-time, quality, missing and corrupt archives; REST/OAuth
MCP parity for both symbols; $150/$500 capital; invalid capital and expiration;
website forwarding, provenance validation, mode mismatch rejection and safe
errors; browser mode selection, capital rerun and historical labeling.

The existing fixed website fixtures now include the default current mode in the
backend request/result metadata. Their economics are unchanged. The existing
cross-platform checksum and volatility-roundoff checks remain intact.

This PR does not deploy either service, change Render configuration, change
secrets, or modify collection scheduling. Deployment of backend and website and
an authenticated after-hours smoke test of both website and MCP remain required
before calling production reliability complete. Deploy the backend contract
before the website mode control; an older backend rejects the new mode field.
