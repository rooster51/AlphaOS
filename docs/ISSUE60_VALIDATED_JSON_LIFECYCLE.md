# Issue #60: validated JSON reuse — NO-GO

**Do not propose a PR.** Reusing parsed-and-validated upstream JSON did not
produce a reproducible complete-body improvement with the actual Next.js server.
The prototype has been removed from this branch's application and route-test
files, restoring deployed baseline **76a6a1696d007aeb6aab31fa33c6dad847608688**.
The diagnostic harness and results remain for audit; no PR, production settings,
Render plans, secrets, timeout, merge or deployment were changed. **Issue #60 and
Milestone 1 remain open.**

## Tested source, constraints and scope

- Measured candidate: **78604eebd87259c5b656534eb32f45ef1b6a8093** on
  `diagnostics/issue60-validated-json-lifecycle`.
- [Completed Linux workflow 39893829563](https://github.com/rooster51/AlphaOS/actions/runs/39893829563):
  all five jobs succeeded (Python, web and three lifecycle trials).
- Three independent Ubuntu runners; order **baseline/candidate,
  candidate/baseline, baseline/candidate**. Comparisons within each trial use the
  same runner, images/dependencies, inputs, local trusted TLS and Docker network.
- Each backend and Next container has **0.15 CPU, 512 MiB memory, no extra swap**.
  All twelve Docker inspections confirm these settings; no OOM kills occurred.
- Python **3.12.14**, Node **24.21.0**, Next.js **16.4.1**. Both frontend images
  build the real application and run `next start`; this is not the earlier HTTP
  adapter or an in-memory response-only replay. Backend is unchanged 76a6a16.
- Existing verified synthetic archive/history fixtures: 2,820 contracts across
  ten expirations and 1,260 history rows, frozen at 2030-01-03. Main workload is
  SPY/QQQ **monthly unrestricted Auto Width**, expiration 2030-01-18. Additional
  inputs exercise $150 Auto, $150 manual $5, long-dated 2031-01-17 and errors.
- **162 HTTP probes:** 36 warm paired requests per variant, six first research
  requests per variant, six warm sequential requests per variant, direct REST,
  compatibility cases and failure cases. Five-second gaps drain preceding pairs.

Provider/history HTTP is stubbed in this fixture harness; it does not measure
production authentication/provider latency. Each fixture backend still performs
archive checksum/payload checks, research and economics, sanitization/redaction,
encoding, gzip and real HTTPS transfer to Next. Next performs full parsing,
validation, wrapper construction, framework compression and HTTP transfer. The
external client measures through complete body consumption, then parses and
validates separately. Client validation time is outside the recorded body time.
Comparisons are between the unchanged deployed code and a candidate using
identical inputs; these fixtures are not production acceptance evidence.

## Prototype and safety

The prototype changed only the successful bridge response path: read text, fully
parse JSON, run all existing symbol/expiration/mode/width/schema/provenance checks,
and only then assemble the existing wrapper using that validated JSON text.
It never streamed or emitted partially validated evidence. Error paths,
authentication, backend sanitization/redaction and the 12,000 ms AbortSignal
remained intact. REST and MCP application code were unchanged.

Direct text reuse differs from the current stringify for unusual numbers.
Conservative numeric guards therefore retain the original Response.json path
for unsafe integers, negative zero, large exponents and possible underflow.
Tests cover those cases, escaped text/Unicode, malformed JSON, stale errors,
authentication, exact-expiration/width substitution and cancellation. A separate
test confirms ordinary research can take the reuse path even when archive hashes
contain exponent-like text. Two body-error test doubles were updated to model
both text() and json(); their abort/error assertions were retained.

The first diagnostic revision used overly broad exponent guards that also
matched archive hashes. It was corrected before the measured run. Superseded run
39893698875 was canceled; none of its timings are included here. No dependency
upgrade, candidate cap, strategy, provider, infrastructure or other optimization
was included.

## Complete response-body results

Seconds; p95 is the **nearest-rank sample p95**, not a population estimate. Small
cold/sequential samples therefore have p95 equal to their maximum. Times include
complete error responses where present; errors never count as successful research.

| Workload | Baseline median / p95 / worst | Candidate median / p95 / worst | Deadline successes |
|---|---|---|---|
| Warm concurrent, 36 requests each | **8.508 / 10.785 / 11.012** | **8.835 / 11.229 / 11.500** | **36/36 -> 36/36** |
| Cold first research, 6 each | **12.199 / 13.203 / 13.203** | **12.258 / 12.999 / 12.999** | **3/6 -> 2/6** |
| Warm sequential, 6 each | **4.505 / 5.701 / 5.701** | **4.994 / 5.342 / 5.342** | **6/6 -> 6/6** |

Warm concurrent median regressed **3.8%**, p95 **4.1%**, worst **4.4%**.
Warm sequential median regressed **10.9%**, despite a better aggregate tail.
Cold response p95 improved modestly, but complete research deadline passes fell.
Both variants returned HTTP 200 on five of six cold requests; a late 200 fails.
Each had one cold timeout. No cold pair had both symbols finish within 12 seconds
except trial 1, where both variants passed; baseline's third passing individual
request in trial 2 became a late 200 for the candidate.

### Per-trial warm paired results

| Trial (12 requests per variant) | Baseline median / p95-worst | Candidate median / p95-worst | Passes |
|---|---|---|---|
| 0, baseline first | 10.189 / 11.012 | 9.810 / 11.500 | 12/12 -> 12/12 |
| 1, candidate first | 7.087 / 8.977 | 7.859 / 9.615 | 12/12 -> 12/12 |
| 2, baseline first | 8.490 / 9.511 | 8.221 / 9.609 | 12/12 -> 12/12 |

Two small median improvements do not repeat in reversed order. **The warm worst
case worsened in all three trials**, and warm deadline success did not improve.
All 18 warm pairs per variant passed in this fixture harness. That ceiling
differs from production's earlier 1/12 successful individual responses: do not
claim these fixture passes establish production reliability or a production
speedup. Real archive/provider latency and candidate observations differ.

### Other unchanged functionality (six requests per variant per case)

| Case | Baseline median / p95-worst | Candidate median / p95-worst | Passes |
|---|---|---|---|
| Direct monthly REST | 5.663 / 6.626 | 5.567 / 6.566 | 6/6 -> 6/6 |
| Monthly $150 Auto | 2.044 / 2.928 | 2.295 / 2.872 | 6/6 -> 6/6 |
| Monthly $150 manual $5 | 0.262 / 0.358 | 0.295 / 0.985 | 6/6 -> 6/6 |
| Long-dated unrestricted Auto | 5.022 / 5.499 | 5.126 / 5.993 | 6/6 -> 6/6 |

## Cold startup versus application latency

Both services start in fresh containers for each variant/trial. Their already
built images exclude image acquisition, host provisioning and Render edge/idle
activation delay. The readiness checks warm health endpoints, not research or
history imports. First research requests include cold history dependencies,
provider-model setup, first TLS connections and first route execution.

Time from starting containers to both services ready was **9.414–11.467 s** for
baseline and **9.235–11.179 s** for candidate. Complete first bodies measured
from container launch had medians **22.434 -> 22.695 s**, worsts **24.180 ->
24.179 s**. These include startup and research, not Render provisioning.
They cannot certify the separately observed production activation/startup gap
or the earlier approximately 53-second first REST bodies. No production restarts
or deployment changes were performed to manufacture cold trials.

## Integrity, economics and measured costs

All **142 successful full bodies** passed research validation. Eight distinct
input cases had identical complete semantic hashes across variants and trials,
covering every research field, economics and provenance. Semantic normalization
accounts only for JSON's 1 versus 1.0 notation; it does not round economic values.
Independent payoff recomputation checked max loss/profit, breakevens, grids,
capital-at-risk, and $150 eligibility; per-leg contract/quote timestamps,
expiration matching, complete archive quality and SHA-256 provenance were checked.
The full body was scanned for diagnostic token/secret leakage.

Expected failure records matched across all trials and variants: invalid date
400, exact unavailable date 502/archive_expiration_unavailable, direct REST
without credentials 401/authentication_required. Existing web tests exercise full
error bodies and failure-before-success behavior. No malformed production archive
was inserted; this is not a new production fail-closed certification.

The reuse path changes harmless JSON numeric spellings, so raw wrapper bytes
need not be identical. Complete parsed research content, quotes, economics and
provenance must match and did. No response truncation or candidate reduction was
used; the main response remains about 12.736 MB decoded.

Correlated warm Next logs show median body read/parse **1707 -> 1739.5 ms** and
the residual bridge time after fetch/body/schema stages **399.5 -> 604.5 ms**.
That residual includes guards and response construction; it is not a separately
instrumented JSON encoder CPU measurement. The earlier isolated adapter's
wrapper saving did not translate to the real server lifecycle. Required numeric
compatibility scanning adds work, and buffering/compression/scheduling remain.
An uncapped local diagnostic measured guard CPU about 31 ms versus 63 ms for
stringify plus body construction on a large fixture; it suggests an eroded
component benefit, not a causal explanation of every Linux regression.

Next cgroup peak memory ranged **212.2–240.2 MB** baseline and **205.4–241.0 MB**
candidate; backend peaks remained below 299 MB. No meaningful memory improvement
or OOM occurred. CPU quota throttling and backend/provider variation still affect
wall times. Three paired runners are not sufficient to prove that every observed
regression is intrinsic to the code; they are sufficient to reject the claimed
reproducible benefit under the requested acceptance gate.

## Complete validation on measured candidate

- **1,184 Python tests + 64 subtests passed**, Python 3.12.14, 292.79 s.
- **102 website tests**, **29 Chromium browser tests**, typecheck and production
  build passed.
- Production dependency audit: **zero vulnerabilities**.
- Full dependency audit passed the unchanged reviewed Issue #41 exception:
  two moderate/five high existing development-tool findings; no new exception.
- All three lifecycle jobs passed their integrity assertions and completed.

Passing functional/security checks does not override failed performance criteria.
No live ChatGPT MCP reauthentication or production parity acceptance is claimed;
MCP code and backend contracts are unchanged and covered by existing tests.

## Decision and next action

**NO-GO for a wrapper-reuse PR.** The warm median gain is inconsistent, warm
tails regress, sequential median regresses, and deadline pass counts do not
improve. Cold individual deadline passes decrease. The prototype is discarded
from the application tree rather than tuned further against these samples.

Retain 76a6a16 and the open production acceptance blockers. Before another
optimization experiment, calibrate the full-lifecycle workload against the
measured production archive/provider delays and cold activation path; the current
fixture ceiling of 36/36 warm passes does not reproduce production's failure
frequency. No alternative production correction is proposed or implemented here.

## Durable evidence

- [Per-trial and aggregate statistics](performance/issue60-validated-json-summary.json)
- [All 162 request records](performance/issue60-validated-json-measurements.json)
- [Semantic/error integrity and artifact SHA-256s](performance/issue60-validated-json-integrity.json)
- [All twelve resource limits and memory peaks](performance/issue60-validated-json-resources.json)

Workflow artifacts (seven-day retention): trial 0 **12476550810**, trial 1
**12476266559**, trial 2 **12475814113**. Local complete ZIP copies and extracted
logs are in `../issue60-validated-json-results/`. The manifest records SHA-256s;
artifacts contain no private TLS key or production credentials. The diagnostic
workflow becomes manual-only and pins measured source 78604ee, so documentation
pushes do not rerun experiments and the rejected measurement remains reproducible.
