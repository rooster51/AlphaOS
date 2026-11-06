# Strategy Research performance stabilization — November 6, 2026

Status: implementation and local verification; **not a hosted timeout cure**.
Continue draft PR #88; retain PR #87 and Freebuff charting separately. No merge,
production change or deployment is authorized by this continuation request.

## Contract and implementation

`POST /v1/research/market` retains its existing full response by default. The
website Strategy Research dashboard now explicitly requests
`response_format: "summary-v1"`. Other consumers retain the full contract.
The interface-v2 envelope identifies this transport format explicitly.

The summary retains every accepted candidate in original order, all exclusions
with their input indices, reasons and required/available capital, complete
archive provenance, classification, comparisons, diagnostics and unavailable
routes. Accepted candidates retain exact canonical quote-bearing legs, risk
metrics, entry prices, breakevens, evidence, max-loss eligibility and missing
evidence. It never ranks or silently truncates candidates. Excluded candidates
remain rejected records, not qualifying opportunities. Counts and complete
coverage are independently checked by the website before forwarding.

Redundant trade/position identities, candidate caveats, full payoff grids and
supporting historical economics move to explicit detail access. The transport
manifest names these detail-only fields. Summary encoding is bounded at 2 MiB;
overflow returns `research_summary_too_large` without returning partial evidence.
The final redacted encoded length is checked too.

`POST /v1/research/market/candidate` uses the same server-to-server authentication,
request cancellation, no-store responses, correlation and compression as market
research. Supply the original market request plus the summary's `detail`
reference: bucket, ordinal index, archive SHA-256 and whole-candidate SHA-256.
It re-reads and validates the archive, rejects a different checksum before loading
history, then recomputes and checks the complete candidate digest. A changed
archive or candidate returns HTTP 409 `research_evidence_changed`. Missing,
stale or corrupt evidence retains its existing fail-closed error. No research
cache or stored candidate is reused. A process restart requires no recovery.

The website bridge preserves the 12-second deadline for summary and detail,
binds detail to the requested symbol/mode/capital/width/expiration/reference,
and validates the full body before returning it. Details load only on demand;
changed evidence asks the user to rerun research instead of substituting a newer
candidate. Quote checks and NO TRADE promotion gates remain unchanged. The
initial dashboard reports all budget exclusions and lazily renders their list.

Detail recomputation intentionally costs another research request. It can fail
after archive rollover or during rate limiting. It is not a promise of persistent
historical retrieval or executable quotes. Full legacy responses remain available
to authenticated API consumers that need an entire research record at once.

## Fixed-input replay: sizes and CPU

These are local replays of actual previously received staging payloads, **not
hosted measurements of the new code**. Byte sizes exclude the website's small
outer wrapper. Compression uses the deployed middleware's gzip level 1.
Every accepted candidate and exclusion is retained.

| Captured payload | Accepted / excluded | Full bytes | Summary bytes | Full gzip bytes | Summary gzip bytes |
| --- | --- | --- | --- | --- | --- |
| Nov 5 QQQ | 66 / 880 | 5,154,107 | 663,975 | 414,841 | 82,601 |
| Nov 5 SPY | 216 / 795 | 6,663,552 | 1,391,082 | 527,430 | 122,729 |
| Nov 6 QQQ | 216 / 538 | 5,579,945 | 1,189,947 | 453,953 | 110,529 |
| Nov 6 SPY | 176 / 525 | 4,942,674 | 1,007,234 | 387,157 | 100,562 |

Five alternating measured replays after warmup gave full encoding versus summary
projection plus encoding medians of 183.03/172.86 ms (Nov 5 QQQ), 232.54/227.01 ms
(Nov 5 SPY), 201.49/200.89 ms (Nov 6 QQQ), and 178.01/175.35 ms (Nov 6 SPY).
Other local regression processes were active. These are development-host numbers,
not a Render CPU guarantee. The substantial demonstrated gain is a 77–87%
decoded reduction and roughly 74–80% gzip reduction, with similar total local
encoding/projection CPU. Do not claim a comparable computation speedup.

## New live baseline against the unchanged staging deployment

At 10:32–10:33 a.m. Eastern (15:32–15:33 UTC), the local actual website bridge
called authenticated `alphaos-api-staging.onrender.com`, still serving integrated
commit `6bfc2d1`. These requests used current strict freshness, $150 capital,
automatic width and backend archive expiration selection. Both selected
2026-11-06 and completed schema validation before the unchanged deadline.

| Symbol | Request ID | HTTP | Bridge / caller | Decoded response | Archive age |
| --- | --- | --- | --- | --- | --- |
| QQQ | `d0de453c79ac45459b42fbebd7bffe1f` | 200 | 7,376 / 7,482 ms | 5,580,001 bytes | 77.4 s / 600 s |
| SPY | `6b8ddccde1174df3ab5a35c17f28047b` | 200 | 5,075 / 5,139 ms | 4,942,748 bytes | 98.8 s / 600 s |

Render traces correlate both IDs. QQQ/SPY stages respectively: archive
1,415/1,074 ms; completed history 1,782/1,449 ms; classification 0/0 ms;
width enumeration 90/4 ms; candidate payoff 608/595 ms; serialization
1,002/803 ms; complete backend request 6,316/4,528 ms. Bridge headers/body/schema
were 7,067/194/70 ms and 4,731/266/65 ms. Startup coldness was not established,
so these must not be labelled controlled cold-start results.

A later simultaneous pair on the unchanged backend also completed: QQQ ID
`86ba69d940a84a61a8d99261c5678b9b` returned 200 in 9,874 ms inside the bridge
(9,952 ms caller, 5,493,869 decoded bytes); SPY ID
`664e4443f36249b49146935c7e254feb` returned 200 in 10,143 ms inside the bridge
(10,203 ms caller, 4,871,078 decoded bytes). Archive ages were 242.7 and 246.8
seconds against the same 600-second limit. This is another old-deployment warm
baseline, not new-code acceptance or proof of a reliable latency margin.

## Hosted 429: separate the actual observations

The earlier uncorrelated non-JSON upstream 429 was recorded on the **Render
website** `alphaos-web-staging.onrender.com`, not demonstrated to originate in a
Netlify preview. Do not relabel that trace as a confirmed Netlify failure.
That Render website remains on main with auto-deploy off; its backend environment
value has not been established. The API staging service remains on the
multi-strategy integration branch with auto-deploy off.

A November 6 unauthenticated read of
`https://deploy-preview-88--alphaostrading.netlify.app/api/research/market`
returned HTTP 401, Server Netlify, HTML, without a research correlation header.
This establishes an access boundary before research, not a backend 429 cause.
No authentication bypass was attempted. The local Netlify CLI configuration has
no authenticated user. Browser diagnostics ended because Computer Use could not
verify the Chrome URL sufficiently to enforce its access policy. The failing
Netlify request ID and non-secret preview backend URL were requested from the
owner; authenticated Netlify function logs/configuration are still needed.

The bridge now logs a fixed backend-target label (staging/production/other) and
an allowlisted upstream Server label alongside status, JSON content type and
correlation match. Arbitrary URLs, bodies, credentials and header values remain
excluded. A Server label alone does not identify the component that generated
a 429. Legitimate rate limiting and website authentication remain unchanged.

## Verification and approval boundary

Local checks: 237 website unit tests, TypeScript checking, Next production build,
and Chromium 59 passed / 2 skipped. New tests cover golden summary/full accepted
eligibility parity, deterministic order, missing quote evidence, count/reference
tampering, authenticated detail equality, checksum/digest changes, summary size
overflow, missing history, missing/stale/corrupt archives, projection cancellation,
concurrent summary isolation, disconnects and sanitized non-JSON 429 handling.
The API inventory explicitly includes the authenticated detail endpoint.
Full Python and GitHub CI results will be recorded after completion.

The initial full Python attempt encountered Windows shared-temp permissions;
the replacement run uses a unique workspace-local pytest temp directory.

PR #88 uses `[skip netlify]` in its title to prevent an automatic preview deploy
while allowing GitHub Actions to validate the branch. This follows
[Netlify's documented Deploy Preview skip mechanism](https://docs.netlify.com/deploy/manage-deploys/manage-deploys-overview/#skip-a-deploy).
No new Render deployment is triggered. A reviewable integration commit retaining
PR #87 must be approved before advancing the staging source branch and deploying.

## Release assessment

**Keep draft; not ready to merge.** Cold/warm and simultaneous complete-response
acceptance on the new deployment, actual authenticated Netlify preview acceptance,
and current GitHub CI success are required. The November 5 first concurrent pair
still timed out during download despite backend completion around 9.5–10 seconds.
The original copying optimization and startup preparation addressed measured CPU
and cold setup costs; this change addresses measured response duplication and
transfer size. It has not yet demonstrated a hosted timeout cure.

If the bounded response still misses the deadline, first establish the intended
preview backend and compare correlated server/bridge stages. The measured free
staging limit is 0.15 CPU / 512 MiB; minute metrics did not prove per-request CPU
throttling or OOM. The least disruptive infrastructure experiment would be a
temporary approved staging compute increase on the same service and revision,
then repeat isolated cold and simultaneous trials. Do not change production,
increase the deadline, add stale research reuse or rebuild the engine to hide an
unmeasured infrastructure problem.
