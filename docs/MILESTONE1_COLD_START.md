# Issue #54: first-request initialization cost

Base: latest main including merged PR #53,
`1b72b59b06d94402207b4723251f712c01d8d3bb`. October 20, 2026.
No deployment, restart, configuration, credentials, infrastructure, timeout,
dependency, symbol, strategy or calculation changes.

## Production observations: existing PR #53 deployment

Read-only Render queries fetched complete traces (`hasMore=false`) for the four
IDs below. These are baseline observations, **not measurements of this change**.
Times below are milliseconds. Nested stages overlap and must not be summed.

| Stage | Cold SPY | Cold QQQ | Warm SPY | Warm QQQ |
|---|---:|---:|---:|---:|
| Archive client acquisition | 3,863 | 3,855 | 0 | 0 |
| Metadata query | 506 | 504 | — | — |
| Archive download | 452 | 449 | — | — |
| Archive read, inclusive | 4,956 | 4,908 | 1,307 | 774 |
| Public context acquisition | 389 | 390 | — | — |
| Public SDK initialization (one shared construction) | — | 317 | — | — |
| Public accounts request | — | 72 | — | — |
| Public provider request | 1,206 | 379 | — | — |
| History load, inclusive | 4,606 | 2,740 | 649 | 1,306 |
| Session calendar (includes lock wait) | 310 | 2,293 | 1 | 1 |
| History features | 1,595 | 1,303 | — | — |
| Research calculations, inclusive | 2,196 | 3,705 | 1,399 | 1,207 |
| Backend completion, HTTP 200 | **11,865** | **11,652** | **3,465** | **3,483** |
| Website bridge elapsed | **12,001** | **12,011** | **3,793** | **4,318** |
| Website status | **502 timeout** | **502 timeout** | **200** | **200** |

Cold pair, approximately 19:30:51.99–19:31:03.85 UTC:

- SPY: `e4196355ac344bdb86e44199864f37c6`.
- QQQ: `875e603861514b4182cf3ff995639970`.

Warm pair, approximately 19:33:51.99–19:33:56.05 UTC:

- SPY: `91988059bccd43a49795cda22f4e3f8a`.
- QQQ: `10f9843bca9643808ddc94e1bbc263e7`.

Both pairs overlapped on their instance. The 12-second website timer starts
before backend arrival and includes transport; a backend duration under 12 seconds
does not ensure website success. Cold website timeout records precede the backend
response-header records. Later QQQ alone completed through the website in 2,185 ms
(`013252ec963345088b798fea13300b6f`). An earlier 19:28 website pair also timed out;
it is not used as the post-#53 cold baseline here.

The logs confirm a shared cold initialization cost: PR #53 already prevents two
Supabase constructions. Both threads can spend the same time in acquisition while
one waits for the other. The logs do **not** prove two constructions, TLS failure,
or Render instance startup. A lifecycle-log search did not yield a usable startup
trace. Render wake-up, DNS/TLS, queueing and network latency remain unseparated;
no restart was performed to force a production cold sample.

## Actual local attribution and selected optimization

A fresh Python process imported the actual FastAPI application before profiling
its first `research_archive_client()` call with fake credentials and no network.
The baseline call took 419 ms under cProfile: 387 ms was cumulative import work,
including 323 ms in the top-level Supabase package. This imports async clients,
auth/realtime and their dependency graph, although research only needs two GETs.
An earlier probe without API pre-import measured 845 ms and is not treated as an
equivalent application-warm profile. These are local profiles, not an attribution
of all 3.86 production seconds to imports.

The smallest selected change replaces **only the research archive transport**
with a fixed-identity HTTPX client providing:

1. The same PostgREST latest-row GET: provider/symbol, observed/created cutoff,
   observed-at descending then id descending, select all, limit one, public schema.
2. The same private Storage object GET, with the archive path URL encoded.

The existing `read_latest_option_snapshot` still performs all metadata validation,
freshness, path/identity checks, SHA-256, gzip/JSON parsing, payload/session/slot/
collection-time/quality checks, and safe error classification. SDK-compatible
injected readers and collector SDK use remain available unchanged. No response,
metadata, archive object, or history is cached. The existing singleton lock and
credential recheck remain. Requests own their params; the shared client holds
only transport/auth configuration.

HTTPX is already part of the API runtime. It retains verified TLS/hostname checks,
environment proxy handling and pooling. Request I/O timeout values match the
installed SDK defaults (PostgREST 120 seconds, Storage 20 seconds), verified by
wire-request comparison. They are not new end-to-end budgets and can exceed the
unchanged website deadline. Redirects are rejected rather than followed; errors
remain sanitized and fail closed, with no retry or SDK fallback. URL userinfo,
query and fragment configuration is rejected before creating a client.

No eager import, startup hook, background warm-up, calendar change, Public-client
change, or history parallelization was added. The improvement removes unnecessary
work instead of shifting that work into application startup. It does not remove
Public authentication/provider latency or first calendar construction.
The new `archive_transport_initialization` span separates actual new-client
construction from the existing outer `archive_client` acquisition span.

## Reproducible before/after fixture measurements

Run `scripts/benchmark_research_cold_start.py` with repo and tests on PYTHONPATH.
The script starts **18 fresh Python processes**: two versions × three workloads
(SPY alone, QQQ alone, concurrent pair) × three repeats. Each worker runs a cold
workload and two warm repeats, giving **72 REST responses**, with three cold and
six warm samples per symbol/workload/version. All full-response SHA-256 digests
match across cold/warm, independent/concurrent, and baseline/optimized execution.

The baseline factory is loaded from the exact main SHA above. Real API handlers,
the original or new client constructors, TLS contexts, archive reader, calendars,
research calculations and serialization execute. Only HTTPTransport network I/O
is replaced with verified synthetic archive fixtures; Public history is injected
as 1,260 synthetic daily bars. These fixtures never become production evidence.
API imports occur before request timing, are measured separately, and are not
claimed to be instance-start latency. Baseline imports stay cold until the first
request. Every response requires a fresh query and download; the script asserts
operation counts and that optimized workers never import `supabase`.

REST timing below is median [min–max], milliseconds. It includes local middleware,
handlers and serialization, not website/provider/Supabase network latency.

| Workload | Before cold (n=3) | After cold (n=3) | Before warm (n=6) | After warm (n=6) |
|---|---:|---:|---:|---:|
| SPY alone | 475.30 [438.21–488.61] | 274.96 [266.40–298.11] | 45.89 [44.68–52.70] | 50.05 [46.50–56.01] |
| QQQ alone | 473.76 [467.74–496.73] | 271.19 [265.53–279.43] | 49.65 [47.46–51.67] | 47.88 [46.82–49.17] |
| SPY in pair | 491.76 [490.32–539.79] | 354.48 [347.73–358.59] | 106.06 [102.43–116.86] | 111.65 [108.44–117.63] |
| QQQ in pair | 493.92 [486.37–542.76] | 356.37 [350.58–360.44] | 114.91 [103.72–117.13] | 121.60 [117.77–123.78] |

Archive-client acquisition, median [min–max] milliseconds:

| Workload | Before cold | After cold |
|---|---:|---:|
| SPY alone | 278 [250–288] | 78 [69–83] |
| QQQ alone | 272 [249–282] | 74 [69–75] |
| SPY in pair | 242 [239–250] | 77 [73–78] |
| QQQ in pair | 242 [238–250] | 76 [72–77] |

Warm acquisition was 0 ms at the log's resolution in every sample. The measured
improvement is cold import/construction overhead; there is no demonstrated warm
speedup. Slight warm differences are reported rather than hidden. The paired
cold REST medians improve by about 28%, not a prediction of production seconds.
Three samples are not a reliability distribution. This run used Windows/Python
3.12, Supabase 2.31.0, HTTPX 0.28.1, Public SDK 0.1.17,
pandas-market-calendars 5.4.0, pandas 3.0.6 and NumPy 2.5.3.

## Regression coverage and validation

`tests/test_research_cold_start.py` covers cold/warm independent SPY and QQQ and
paired requests in both modes. Barriers prove simultaneous metadata queries;
an event holds cold creation while requests compete for the singleton. Complete
REST results match the original reader and OAuth MCP, and the website's five
shared fixtures match both interfaces. Fresh queries/downloads are counted.
Malformed evidence, stale/future evidence, path/identity/checksum errors, missing
metadata, HTTP/Storage errors, timeouts, invalid JSON and redirects fail closed.
Failure responses do not reveal fixture credentials or retry requests.

A fresh API subprocess asserts initialization makes no network request, never
loads Supabase, retains TLS verification, reuses its singleton and rejects missing
credentials after initialization. A real SDK comparison verifies both HTTP paths,
query params, auth headers, I/O timeouts and the complete verified archive record.
The tests never authenticate to a production service.

Validation on the final code:

- Complete Python suite: **949 passed, 64 subtests passed in 169.00 s**.
  Four deprecation warnings come from the deliberately exercised baseline SDK
  constructors in the wire-parity test.
- Focused new cold-start file: **25 passed in 7.49 s** before the complete run.
- Website unit/contract suite: **87 passed**.
- Typecheck and production build: passed.
- Browser suite: **23 passed in 5.6 s**.
- Diff whitespace check: passed.
- Fresh-process benchmark: **18 processes / 72 equal full REST responses**.

## Remaining acceptance and approval boundary

No post-change production measurements exist. Production cold/warm independent/
concurrent requests inside 12 seconds are **not yet verified**, including correct
fail-closed errors during slow upstream requests. Provider, network, first Public
context, first calendar, CPU scheduling, Render wake-up and website overhead remain
risks. This change is narrower than claiming all first-request latency solved.

After separately approved merge/deployment, repeat independent SPY and QQQ and
paired requests across genuinely new processes and warm repeats. Retain matching
website/backend IDs, stage records, correct status/labels and verified response
contracts. Record startup/wake-up separately; do not call a cleared fixture cache
a production cold start. No restart, merge or deployment is authorized by this PR.

Primary protocol references inspected:
[Supabase REST routes](https://supabase.com/docs/guides/api/creating-routes),
[PostgREST filters/order/limit](https://docs.postgrest.org/en/stable/references/api/tables_views.html),
[Storage download](https://supabase.com/docs/reference/python/storage-from-download),
plus the installed synchronous SDK implementations and HTTPX SSL configuration.
