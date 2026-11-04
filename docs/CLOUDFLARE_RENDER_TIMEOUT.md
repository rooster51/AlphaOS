# PR #67: Cloudflare-to-Render timeout investigation

Investigated October 27, 2026. All infrastructure access was read-only. Live
research probes used the existing website proxy and its server-side bindings;
no credentials or market observations were printed or committed.

## Confirmed cause

The two supplied requests expired during **Render Free instance startup**,
before the Python application received them. They did not time out in archive
queries, the Public history provider, or research calculations.

| Evidence | Observation |
| --- | --- |
| Cloudflare QQQ `cc21641449b045bcaf112001c3b462e3` | At 11:53:23 EDT, 502 after 12,001 ms; `stage=fetch`; configuration ready; no upstream status/headers. |
| Cloudflare SPY `75a0416e8847486baaf3b55f650a66fb` | At 11:53:23 EDT, 502 after 12,007 ms; same fetch-stage evidence. |
| Render correlated logs | Neither ID appears. The deployed middleware logs market-request entry before authentication, so there is no evidence either reached the application or authenticated. |
| Render instance | New instance `9q57v` logged `Running 'python -m alphaos_api'` at 11:53:32 EDT (`2026-10-27T15:53:32Z`), after both proxy deadlines had expired. |
| Render compute | `serviceDetails.plan=free`; one instance; 0.15 CPU, 512 MiB limit. `buildPlan=starter` is the build plan, not the compute plan. |
| Deployment | Existing manual deploy `dep-dbdc8dtg1s2s73b05a6g`, commit `76a6a169` (PR #64), live. Auto-deploy is off. No new backend deployment was triggered. |
| Health after startup | `/health` returned 200, authentication configured, in approximately 354 ms. |
| Resource usage after startup | Approximately 153 MB of 512 MB; no OOM/failure event was found in the queried window. |

[Render documents](https://render.com/docs/free#spinning-down-on-idle) that Free
web services spin down after 15 minutes without inbound traffic and can take
about a minute to restart. That delay exceeds this website's fixed 12-second
research deadline. A live deployment status does not mean a Free instance is
currently awake. There is no justified archive/query optimization for requests
that never entered the application.

## Full path and warm verification

Browser → Cloudflare native runtime bindings → authenticated server-side POST
to Render `/v1/research/market` with `X-AlphaOS-Request-ID` → archive service →
verified Supabase metadata/object/checksum → completed Public daily history →
research calculations → buffered response serialization → Cloudflare envelope
validation → browser. Research never falls back to a live options chain or
synthetic market evidence.

After Render started, the existing deployed Preview completed all four live
probes with HTTP 200, `source=alphaos_research_api`, and
`verified_for_trading=false`. The proxy validates the real response envelope
before accepting it. These are point-in-time successes, not a guarantee of
executable prices or continuous availability.

| Probe | Client round trip | Correlation ID |
| --- | --- | --- |
| QQQ sequential | 10,090 ms | `cd8f0124f240488eb377f363fd4a9bbb` |
| SPY sequential | 6,283 ms | `6d0588245d2d43fc95145479acbc857b` |
| QQQ concurrent pair | 8,489 ms | `3be375fef2964c23be0dce4b70155b0b` |
| SPY concurrent pair | 8,212 ms | `f1c9a1edcaf64aa4b116bbddd9ee6f54` |

Cloudflare confirmed upstream 200 and matching backend correlation headers on
the sequential pair. Its own processing times were 8,476 ms / 4,425 ms, both
inside 12 seconds. Client round trips include network time outside that budget.
Render also logged both requests completing successfully:

| Render stage | QQQ first request after startup | SPY subsequent request |
| --- | ---: | ---: |
| Verified archive read | 760 ms | 570 ms |
| Metadata query (part of archive read) | 338 ms | 306 ms |
| Object download (part of archive read) | 297 ms | 256 ms |
| Completed history loading | 3,057 ms | 579 ms |
| History dependency import (part of history loading) | 2,051 ms | 0 ms |
| External history request (part of history loading) | 374 ms | 380 ms |
| Research calculations | 3,295 ms | 1,901 ms |
| Response serialization | 1,006 ms | 893 ms |
| Application request completion | 8,319 ms | 4,063 ms |

The dependency import is a measurable cold-process cost, but neither the
external provider nor the archive query was blocked. The original failures
occurred before any of these stages. No speculative backend optimization,
cache, data-selection change, or MCP change is included.

## Smallest justified fix and remaining operation

For reliable first-request research within 12 seconds, move the existing
**AlphaOS** backend service (`srv-daqillmgekts73ak0mj0`) to a **non-Free,
non-sleeping compute instance**, after approval for that production
infrastructure change. In Render, open this service's Settings / Instance Type
and change its service compute plan; upgrading the workspace or build plan is
not the same operation. Keep one instance, one Python worker, the same source
commit, start command, health path, credentials, archive policy, and MCP origin.
Recheck health plus concurrent QQQ/SPY from the Preview afterwards.

That compute change was **not applied**: it affects the production service and
may restart it, outside this task's no-production-deployment constraint.
The existing Render website is retained. There is no new keepalive automation,
hidden retry, health preflight, extended deadline, or synthetic fallback.
While the service remains Free, another idle period can reproduce the failure.
For a manual Preview session, allow the service to finish starting and then
explicitly retry; this does not establish always-on availability.

The code change is deliberately limited to truthful diagnostics and recovery
guidance. Proxy timeout logs now include a fixed `outcome`, `timeout_phase`, and
failed header-wait duration where available. Header wait is not itself proof of
a cold start; operators must correlate with Render. The market view explains
the 12-second server deadline; both views offer an explicit retry after startup.
The dashboard's existing 14-second client watchdog also remains unchanged.

Regression tests cover concurrent QQQ/SPY header waits in current and historical
mode, exactly 12,000 ms, separate correlation IDs, no hidden retries, safe logs,
body-timeout classification, and recovery only on a new request. Browser tests
verify the retry guidance and absence of substitute evidence. Existing real-data
validation, cancellation, archive error handling and MCP parity remain intact.
