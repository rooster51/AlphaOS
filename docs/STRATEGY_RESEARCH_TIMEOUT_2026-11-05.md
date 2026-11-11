# Strategy Research timeout investigation — November 5, 2026

## Reproduction and correlation

The request is `POST /api/research/market` with `{"symbol":"QQQ","research_mode":"current","available_capital":150}`. Expiration and width are omitted so the backend selects the archive expiration and performs automatic observed-strike enumeration. The website deadline remains 12,000 ms.

The actual website route was executed locally with a synthetic website session and the existing authorized staging API credential. It called the real `https://alphaos-api-staging.onrender.com/v1/research/market` service. These measurements establish the staging workflow, separately from the originally reported production browser request. No production request ID was supplied when this report was prepared.

The Render workspace was confirmed by the owner before log access. The staging service was `srv-db6mql2d0e5s73atk5e0`. A separately initiated deployment of the multi-strategy branch was in progress during the initial measurements. Both timeout traces ran on a newly initialized backend process.

| Case | Website request ID | HTTP result | Elapsed |
| --- | --- | --- | --- |
| Independent QQQ current / $150 / auto | `797e5c240dee4ef2947aa46d7f97c8a7` | 200 | 6,671 ms inside bridge; 6,761 ms including caller |
| Following direct QQQ request | `fbb7866170b54df78712ac66386d4ea2` | 200 | 5,746 ms including body |
| Concurrent SPY current / $150 / auto | `6bc62e7abb37486ba0810b9106af9e8f` | 502 `backend_timeout` | 12,023 ms inside bridge |
| Concurrent QQQ current / $150 / auto | `0005b1f994404d578264b3b98e2a3e5d` | 502 `backend_timeout` | 12,024 ms inside bridge |

Every listed ID was found in the corresponding staging Render application trace. Successful responses echoed the ID. Both timed-out traces show backend computation followed by `client_disconnect` and cancellation, rather than a successful or partially transmitted research result.

## Stage measurements and root cause

Stages nest; their durations must not be summed indiscriminately.

| Stage | Independent QQQ | Cold concurrent QQQ | Cold concurrent SPY |
| --- | --- | --- | --- |
| Archive client preparation | 0 ms | 1,440 ms | 1,004 ms waiting/preparing |
| Archive retrieval and validation, including preparation | 1,624 ms | 2,757 ms | 2,895 ms |
| Completed daily history, including imports/authentication | 1,647 ms | 2,574 ms | 4,205 ms |
| Archive normalization / initial calendar work | 3 ms | 1,709 ms | 92 ms |
| Session calendar | 1 ms | 300 ms | 1 ms |
| History features | 189 ms | 309 ms | 298 ms |
| Market classification | 0 ms | 1 ms | 10 ms |
| Candidate generation / width enumeration | 4 ms | 96 ms | 194 ms |
| Candidate payoff processing | 1,006 ms | 3,215 ms | 3,597 ms |
| Candidate comparison | 1 ms | 3 ms | 8 ms |
| Response serialization | 1,096 ms | Cancelled before serialization | Cancelled before serialization |
| Backend request completion/disconnect | 5,779 ms | 12,045 ms | 11,739 ms |

The successful website probe took 6,337 ms to receive headers, 230 ms to consume the body, and 86 ms to validate the schema. Its decoded response was approximately 5.8 MB. These header timings include backend work, rather than measuring connection establishment alone. A separate DNS/TCP/TLS probe is recorded with the final staging measurements.

The demonstrated timeout combines first-request initialization on a new instance with simultaneous CPU-heavy candidate evaluation. QQQ cold history dependency imports took 674 ms, its SDK initialization took 405 ms, and the first archive transport construction took 1,439 ms. Cold calendar work and hundreds of candidate copies then consumed the remaining budget. The successful QQQ response had generated 1,024 candidates. Classification itself and width enumeration were small parts of the delay. Archive network retrieval contributed latency, while the cold setup and candidate CPU work explain the reproducible deadline overrun.

A local cProfile replay of the 1,016 valid QQQ candidate trades found 0.490 seconds of its 0.820 seconds in recursive copying. This is CPU profiling on the development host, not hosted latency. Five alternating unprofiled replays reduced median candidate processing from 180.78 ms to 127.01 ms, about 30%, with identical complete result hashes (`cdb3cafeb14263e8d4c546df482da4babf5710d1bc51eb887984a1d80d4b3058`).

## Changes

The CLI entry point prepares package-defined calendars, optional history imports and the configured archive HTTPX/TLS transport before opening the server port. It performs no archive queries, provider authentication, account requests, history retrieval or quote retrieval. Optional preparation failures retain the existing request-time error handling. Market observations and eligibility are still read and validated per request.

Quote-bearing trade copying now handles exact built-in scalar fields directly, while using the standard deepcopy implementation for mutable/custom values with a shared memo. Nested mutable observations remain independent of the caller and retain their original alias relationships. Strategy validation, payoff arithmetic, candidate enumeration, capital checks and the response contract are unchanged by this optimization.

The 12-second bridge deadline and cancellation behavior remain in place. No quote age, archive age, checksum, contract, risk or evidence gate is relaxed. Regression tests cover slow and incomplete bodies for the exact current QQQ/$150/auto request, sibling request isolation on cancellation, cancellation during payoff preparation, deepcopy parity and ownership, and startup preparation without provider/archive reads.

## Validation status

The full Python suite passed 1,420 tests plus 64 subtests, with one skip. The website unit suite passed 233 tests, including the new slow-body and cancellation cases, and TypeScript checking passed. The integrated multi-strategy/timeout focused suite passed 80 tests. GitHub Actions for PR #88 passed Python, website, PostgreSQL integration and Workers checks.

## Approved staging deployment and observed limits

The owner approved deploying integration commit `6bfc2d1ee16d1763ad17a698519a9a08c159f863`, retaining PR #87's multi-strategy changes alongside this separate fix. Render staging deployment `dep-dbmb7km417fc73bsjeng` became live at 2026-11-05 16:52:53 UTC. Auto-deploy remains off. No production deployment or merge was performed. Runtime preparation completed before port readiness in 25,195 ms; this is startup time, not request time.

All following bridge measurements execute the actual website route locally against the deployed staging API. They are not measurements from a deployed website browser session. All requests used current strict freshness, $150 capital, omitted width and omitted expiration.

| Case | Request ID | HTTP result | Bridge / caller elapsed |
| --- | --- | --- | --- |
| First post-deploy SPY, simultaneous pair | `5b1e2193cd184fc9963644fd85c2f56a` | 502, body deadline | 12,014 / 12,055 ms |
| First post-deploy QQQ, simultaneous pair | `bdb092ca0bfe40b0b2692f63c7e536e2` | 502, body deadline | 12,018 / 12,019 ms |
| Isolated QQQ at 17:12:15 UTC | `ad68442897e547f5b70accb67623abfa` | 200 | 5,989 / 6,044 ms |
| Isolated SPY at 17:12:25 UTC | `50af71a90e314e2a9c89935771d7a91d` | 200 | 6,586 / 6,666 ms |
| Later simultaneous QQQ at 17:12:46 UTC | `9ea1bd4ec1cd43a8b8bf988f5ba1f008` | 200 | 5,285 / 5,321 ms |
| Later simultaneous SPY at 17:12:46 UTC | `a8b2e748d02145e4a52355e83038b8f0` | 200 | 7,684 / 7,745 ms |

The first post-deploy backend traces completed in 9,508 ms for QQQ and 10,014 ms for SPY, but the bridge deadline expired while reading the bodies. Serialization took 1,302 and 3,800 ms respectively. Preloading eliminated request-time archive transport construction and dependency imports, but did not guarantee the full cold concurrent response fits inside 12 seconds.

| Isolated post-change stage | QQQ | SPY |
| --- | --- | --- |
| Archive retrieval and validation | 1,410 ms | 955 ms |
| Completed history retrieval and validation | 1,638 ms | 1,383 ms |
| Market classification | 0 ms | 0 ms |
| Width enumeration | 8 ms | 94 ms |
| Candidate payoff processing | 897 ms | 798 ms |
| Response serialization | 1,004 ms | 1,195 ms |
| Complete backend request | 5,452 ms | 5,735 ms |
| Bridge headers / body / schema | 5,747 / 171 / 60 ms | 6,177 / 347 / 53 ms |

The successful isolated responses selected 2026-11-05 expiration from the archive, passed its unchanged 600-second maximum age (actual ages 66.9 and 82.2 seconds), and returned complete sessions. The later successful pair had archive ages 97.7 and 102.8 seconds. Candidate populations vary with newly archived quotes, so hosted before/after results are operational observations, not a controlled fixed-input benchmark. The fixed-input local replay above supplies that comparison.

Connection and transfer variability remain separate limitations. A direct negotiated-gzip diagnostic measured DNS/TCP/TLS completion at 3,153/3,205/3,264 ms for SPY and 3,122/3,412/3,460 ms for QQQ, with full responses taking 16,494 and 22,378 ms. Another warm bridge pair produced SPY 200 in 11,259 ms and a QQQ header timeout. The QQQ backend execution began at 17:04:29.284 UTC, about nine seconds after the local probe began, and was cancelled after 3,853 ms of execution. The available traces do not isolate that pre-admission delay to DNS, transport, proxy queuing or server scheduling. It must not be attributed entirely to candidate calculation.

Render reports a 0.15-CPU limit and 512-MiB memory limit for this free staging service. Observed memory remained below 190 MB. Minute-resolution CPU metrics do not prove request-level throttling; no OOM evidence was found.

The separately hosted staging website could not provide a valid end-to-end confirmation: QQQ request `69f9716f2bee4f908783c4976acece73` returned 502 `backend_rate_limited` in 547 ms. An earlier hosted request `2239b971a0ae45e9a0a0ad9789f753a2` logged an upstream non-JSON 429 with `backend_correlated=false`. Its configured upstream was not established by these observations. This result is distinct from the correlated staging API tests and must not be counted as a successful hosted website test.

**Release assessment:** the measured copying and cold initialization costs are improved, and both symbols pass realistic warm staging requests. Cold concurrent completion and the hosted website upstream remain unresolved. This is not evidence of a complete timeout cure or production readiness. Keep the PR in draft and retain the 12-second deadline, fail-closed behavior and all evidence/risk gates. No request ID for the original production failure was supplied, so an exact production-to-Render correlation is still unverified.

[Render deployment readiness](https://render.com/docs/health-checks)
