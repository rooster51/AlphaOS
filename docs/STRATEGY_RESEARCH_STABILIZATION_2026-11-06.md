# Strategy Research performance stabilization — November 6, 2026

Status: approved API staging verification recorded below; Netlify preview and
idle-resume acceptance remain incomplete. **Not a complete hosted timeout cure.**
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

## Approved deployment and actual API acceptance (11:06–11:10 a.m. Eastern)

After the report above, the owner explicitly approved integration `42e4106` for
`alphaos-api-staging` in My Workspace and preview publication once its staging
backend target is verified. The configured staging branch was advanced by
fast-forward; production and merges were untouched. Auto-deploy remains off.

The first deployment, `dep-dbmvg2rncjis73akj2ag`, checked out the approved commit
but initially stalled during rollout. A health request timed out after eight
seconds; another instance startup was subsequently logged. Render reported the
deployment live at 16:02:12 UTC, yet the served OpenAPI schema still lacked
`MarketTransportRequest` and the candidate-detail endpoint. Requests
`1b5eace507fa409fb69674a06aafc419` (QQQ) and
`ae594c7fd81e47d48ca8f9cf5af9b7d0` (SPY) returned backend HTTP 422
`invalid_request` on instance `5fzq9`. They are failed version-verification
attempts, not new-code performance acceptance. The precise platform mechanism
behind this routing/artifact discrepancy was not established.

A cleared-cache redeployment of the same approved commit,
`dep-dbmvl3om7kps73cf4a6g`, became live at 16:06:10 UTC. Served OpenAPI then
confirmed both the summary model and detail endpoint. The measured requests
below correlate to new instance `tnvkr`. Runtime preparation took 12,594 ms before
port readiness; this startup interval is separate from request latency.

These execute the actual website bridge locally against the real authenticated
staging backend, then consume and validate the complete body. They are **not
measurements from a deployed Netlify website session**. Current cases use $150
capital and strict freshness; width is automatic and expiration is archive-selected
except in the explicitly selected expiration case. All selected 2026-11-06.

| Case | Symbol | Bridge / caller ms | HTTP | Complete decoded bytes | Request ID |
| --- | --- | --- | --- | --- | --- |
| First research pair after readiness | SPY | 9,491 / 9,499 | 200 | 1,045,428 | `d1deeb215e434f458224609b6803374d` |
| First research pair after readiness | QQQ | 9,548 / 9,573 | 200 | 1,248,542 | `90f6f43193904a1ca5ff3267df136133` |
| Warm isolated | QQQ | 4,950 / 4,989 | 200 | 1,248,542 | `7e1cf19297294386938bcec55578e760` |
| Warm isolated | SPY | 5,510 / 5,537 | 200 | 1,045,428 | `fd42067d2bc640b38db9061f8ebb8072` |
| Pinned detail pair | QQQ | 6,052 / 6,074 | 200 | 17,124 | `54e35b5a695242ff803935afc5f80058` |
| Pinned detail pair | SPY | 6,527 / 6,529 | 200 | 17,150 | `ff43d7260224488d9918e4d2223bd872` |
| Explicit expiration pair | SPY | 7,908 / 7,915 | 200 | 1,045,437 | `3ae912d20dd34636bee197615a8b0ab0` |
| Explicit expiration pair | QQQ | 7,939 / 7,965 | 200 | 1,248,550 | `6c6df951e4fb49f6b92239f364b417fe` |
| Historical pair | SPY | 7,278 / 7,287 | 200 | 1,045,567 | `7c201bb59990456eae7b7181914de4f0` |
| Historical pair | QQQ | 8,157 / 8,182 | 200 | 1,248,681 | `26f9836a9f7c4f71adcdb15874d336a8` |

The first pair is cold **research on an already-ready fresh process**, following
the application's static preparation. No research/provider/archive call had
warmed that process. It is not a sleeping-service wake-up test or an isolated
cold-start trial per symbol. Every 200 response above passed complete-body schema
validation within 12 seconds. First-pair archive ages were 43.0/47.0 seconds;
isolated warm ages were 66.0/75.1 seconds, with the unchanged 600-second maximum.
Historical mode explicitly retained its non-current evidence semantics.

### Correlated processing stages

Nested stages must not be added as independent work.

| Stage, ms | First-pair QQQ | First-pair SPY | Warm QQQ | Warm SPY |
| --- | --- | --- | --- | --- |
| Archive read and validation | 1,315 | 1,591 | 701 | 894 |
| Completed history | 2,211 | 2,208 | 1,376 | 1,270 |
| Classification | 0 | 0 | 0 | 0 |
| Width enumeration | 99 | 201 | 93 | 6 |
| Candidate payoff | 2,303 | 2,002 | 708 | 1,409 |
| Summary projection, including digests | 1,499 | 1,600 | 895 | 795 |
| Response serialization | 402 | 400 | 202 | 197 |
| Backend complete request | 9,145 | 9,098 | 4,377 | 5,058 |
| Bridge headers / body / schema | 9,459 / 77 / 8 | 9,417 / 49 / 19 | 4,791 / 141 / 14 | 5,454 / 40 / 12 |

### Same-archive full/summary and detail consistency

A legacy full-response control pair on this same deployment returned 200 in
9,113 ms QQQ (`8f881814830741a08bf1c795426a1665`) and 8,910 ms SPY
(`4cc1ae5dfd0d4ba3a976bf06a4893cee`). Archive checksums matched the warm summaries.
Every accepted candidate's summary fields, exact quotes, economics and order
matched the corresponding full record: all 236 QQQ candidates and 188 SPY
candidates. Both website assessments produced identical accepted eligibility
results. Exclusion counts were 467 QQQ and 487 SPY. The first retrieved complete
detail for each symbol also matched its summary and reference.

Actual complete decoded full/summary sizes were **5,419,767 / 1,248,542 bytes QQQ**
and **4,877,820 / 1,045,428 bytes SPY**. The legacy control was another warm
concurrent trial, so comparing its latency to the first research pair does not
isolate projection performance. The earlier fixed-input replay supplies that
controlled comparison. The measured benefit is payload reduction; no new
candidate calculation speedup is claimed.

A separate direct HTTPS transport probe, with a fresh connection per symbol and
negotiated gzip, received 113,337 bytes QQQ and 102,233 bytes SPY. QQQ DNS/TCP/TLS
completion was 106/246/279 ms, headers 9,268 ms, complete transfer 9,308 ms
(`8eba4d598abd4a7aa7e0e3916981a9dd`). SPY was 137/277/316 ms, headers 9,319 ms,
complete transfer 9,483 ms (`60cfa3b69fb5499f8956bd8be6f12dee`). These transport
probes are distinct from bridge schema-validation acceptance.

### Real cancellation and fixture-only failures

Both client cancellations returned bridge HTTP 499 without research:
QQQ 764 ms (`796a2ea96ad943e9a3e0458df7ae6e80`), SPY 752 ms
(`9d75f2d69daf438a8e0477908b92ba35`). Render observed both disconnects at
444 ms after backend admission. Archive download/read and execution were
cancelled at 497/552 ms respectively; no history or candidate work followed.

Missing/stale/corrupt archives, malformed/slow response bodies, reference changes,
size overflow and upstream 429 handling were exercised with explicit fixtures.
Those results are not represented as destructive live-archive tests or an
authenticated Netlify 429 reproduction.

### Verification and remaining acceptance

Functional PR #88 commit `b17fa2a` passed local full Python: **1,439 tests plus
64 subtests**, one skipped. Website unit tests: 237; TypeScript and production
build passed; Chromium: 59 passed, two skipped. GitHub
[tests run 42245494545](https://github.com/rooster51/AlphaOS/actions/runs/42245494545)
and [Workers run 42245494758](https://github.com/rooster51/AlphaOS/actions/runs/42245494758)
passed, including PostgreSQL, Windows and both Workers configurations.
Integrated `42e4106` passed 119 focused Python tests, 239 website tests,
TypeScript/build and Chromium 61 passed / two skipped.

Netlify publication remains conditional on verifying its intended staging
backend. The local Netlify CLI has no authenticated user or token. A dedicated
browser sign-in reached GitHub authentication for Netlify, but no authenticated
dashboard was available; the handoff tab subsequently disappeared. The requested
non-secret preview backend URL is still missing. The PR's preview-skip guard
remains in place until that condition is satisfied. Do not claim the actual
Netlify website path or the original uncorrelated 429 is resolved.

The free service's idle-wake behavior must also be measured separately. Its
observed static preparation alone took 12.594 seconds before listening. Render
[documents idle suspension after 15 minutes and roughly a minute to resume](https://render.com/docs/free#spinning-down-on-idle).
Ready-instance research passing does not establish a sleeping-service 12-second
guarantee. An idle-wake trial is pending; its outcome will be recorded in PR #88.
No periodic keep-alive or increased website deadline is being used to hide this
constraint. An approved always-on staging compute plan would be the least
disruptive infrastructure alternative if idle wake prevents acceptance.

**Recommendation remains draft / do not merge.** The new API summary/detail path
passed the ready-instance trials above, while Netlify and idle-wake acceptance
are still outstanding. Production and charting remain untouched.
