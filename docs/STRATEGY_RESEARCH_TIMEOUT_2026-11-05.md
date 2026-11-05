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

The targeted Python suite initially passed 82 tests and 7 subtests. The website unit suite passed 233 tests, including the new slow-body and cancellation cases. Full regression and post-change hosted measurements are recorded in the PR as they complete.

The staging service already carries the multi-strategy branch. Hosted verification of this timeout fix should use an integration commit retaining that branch's changes. Staging deployment requires approval beyond the workspace's confirmed read-only diagnostic access.

[Render deployment readiness](https://render.com/docs/health-checks)
