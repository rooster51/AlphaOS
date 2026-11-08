# Render keep-warm heartbeat

The AlphaOS research API runs on Render as a **Free** web service
(`srv-daqillmgekts73ak0mj0`, 0.1 CPU / 512 MB). Render spins a Free web service
down after 15 minutes without inbound traffic and boots it again on the next
request. Measured on 2026-11-04: the first request after idle waited **42.65 s**
while DNS took 12 ms, TCP 16 ms and TLS 38 ms — the wait is the boot, not the
network. Warm `GET /health` answers in 0.18–0.34 s.

That boot is what surfaced as `market_evidence_timeout` on `/charts`: the page
allows one 8.5 s budget for the verified market + structure pair, so a sleeping
backend cannot answer. The evidence budget is unchanged; this heartbeat removes
the boot from the common path.

## Decision

Keep the service warm with the **existing external scheduler** (cron-job.org,
already used for the intraday collector heartbeat) calling the **public**
`GET /health` every 10 minutes during the hours AlphaOS is used. No code path,
credential, data, timeout or freshness rule changes.

| Option | Cost | Effect on the failure |
| --- | --- | --- |
| Keep-warm heartbeat (this document) | $0 | Removes the boot while the window is active. A ~40 s boot still happens once per window start and outside the window. |
| Non-sleeping Render instance (`0.5c-512mb`, legacy name "Starter") | $7/month per instance, prorated to the second | Removes cold starts entirely and raises CPU from 0.1 to 0.5. Required before always-on, unattended or multi-user use. |
| Server-side evidence cache | $0 (code change) | Does **not** fix a cold start: the first request still pays the boot. Only collapses the panel and chat duplicate pairs into one. Optional follow-up, not a substitute. |

The prior audit in `docs/CLOUDFLARE_RENDER_TIMEOUT.md` reached the same
conclusion for always-on use: the smallest justified fix is a non-Free instance.
This heartbeat is the zero-cost mitigation for the pilot's working window, and it
does not claim always-on availability.

## Scheduler job (manual; not performed by this change)

cron-job.org job, created **disabled**, timezone UTC:

- Schedule: every 10 minutes, 12:00–22:00 UTC, Monday–Friday. Equivalent cron
  expression: `*/10 12-21 * * 1-5` (fires 12:00, 12:10 … 21:50).
- Request: `GET https://alphaos.onrender.com/health`
- Headers: none. No `Authorization`, no body, no query parameter and no
  credential of any kind. The route is public and returns only
  `{"status":"ok","schema_version":"alphaos-research-v1","read_only":true,"authentication_configured":true}`.
- Request timeout: 90 s. It must exceed a ~60 s boot, otherwise the ping fails
  while the service is actually waking.
- Notifications: enable failure and recovery notifications; treat two
  consecutive failures as an outage. cron-job.org disables a job after repeated
  failures — re-enable it only after fixing the cause.

Cadence rationale: the sleep threshold is 15 minutes, so a 10 minute cadence
tolerates exactly one missed beat. An external scheduler does not fire at an
exact instant; the collector documentation already notes this.

## Free instance hours

Render grants **750 Free instance hours per workspace per calendar month**, and a
Free service consumes them while it is awake. A 31-day month is 744 hours, so one
service kept awake around the clock uses the entire allowance, and any second
awake Free service pushes the workspace over it — Render then suspends **all**
Free web services in that workspace until the next month begins.

Budget for the window above: 10 hours/day × ~21.7 weekdays ≈ **217 h/month**
(seven days a week would be ~304 h). Both leave ample headroom. Do not move this
job to 24/7 without checking the workspace allowance for every Free service.

## Monitoring and verification

- The scheduler's own failure and recovery notifications are the primary signal.
- `.github/workflows/backend-health-check.yml` is a dispatch-only,
  credential-free check: it requests `/health` with a bounded 60 s timeout,
  asserts HTTP 200 and `status: ok` / `read_only: true`, prints the timings, and
  fails the run otherwise. It is not scheduled, spends no runner minutes on a
  timer, and gives an operator a logged verification in Actions history with
  GitHub's failed-workflow notifications.
- Interpreting failures: `503` means the service is suspended (hours exhausted)
  or still booting; `404` means the health route changed; `429` means
  throttling; DNS or TLS errors mean the host or certificate changed. A 200
  proves process health only — never market data, authenticated research routes
  or archive freshness (see `docs/DEPLOYMENT.md`).

## Limitations

- Render does not document keep-warm pings as a supported mechanism; the
  documented way to remove Free limitations is a paid compute plan. This is an
  operational workaround, not an availability guarantee.
- A cold start still happens at the start of each window, after any missed beat,
  and whenever the job is disabled or its scheduler account lapses.
- It does not raise the evidence budget and does not make research data fresher.
- Keeping the service awake consumes Free instance hours that a sleeping service
  would not consume.

## Rollback

Disable the scheduler job. There is no credential to revoke and no code path to
revert; delete `.github/workflows/backend-health-check.yml` if the manual check
is unwanted. The service returns to its current behaviour: sleep after 15 idle
minutes.
