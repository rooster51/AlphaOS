# Release 2.0 Milestone 1 performance optimization

Based on main after PR #52, `be430e860d4b220a63b5f03225875925039de792`.
Inspection and measurements: October 20, 2026. No deployment or infrastructure,
secret, strategy, symbol, timeout, or dependency changes.

## Complete production evidence

Read-only Render logs from AlphaOS (`srv-daqillmgekts73ak0mj0`) were fetched
separately for each request over 19:03–19:04 UTC. Both queries returned
`hasMore=false`, with arrival, stage starts/ends, headers and request completion.
Both requests used **current** mode, not historical mode, and completed HTTP 200
after the website deadline. They overlapped on the same instance with two active
executions. These are the traces matching the supplied SPY 15.7-second incident;
they are distinct from the earlier historical timeout IDs documented in PR #52.

| Span (ms) | SPY | QQQ |
|---|---:|---:|
| Archive client | 3,631 | 3,395 |
| Metadata query | 1,314 | 903 |
| Download | 982 | 591 |
| SHA-256 | 0 | 0 |
| Decompression | 2 | 1 |
| JSON decode | 6 | 99 |
| Metadata/payload validation | 0 / 0 | 0 / 0 |
| Archive read, inclusive | 5,936 | 4,996 |
| History SDK initialization | 504 | 503 |
| History accounts request | 74 | 77 |
| History provider context, inclusive | 579 | 581 |
| History token refresh | 0 | 0 |
| History provider request | 361 | 600 |
| History load, inclusive | 1,995 | 4,206 |
| Archive normalization | 7 | 4 |
| Session calendar | 2,002 | 1,901 |
| History features | 2,700 | 2,999 |
| Opportunity classification | 0 | 0 |
| Historical economics | 2,506 | 1,906 |
| Candidate/economics pipeline, inclusive | 2,700 | 2,093 |
| Research calculations, inclusive | 7,409 | 6,998 |
| Research execution, inclusive | 15,431 | 16,204 |
| Serialization | 205 | 104 |
| Arrival to response headers | 15,744 | 16,397 |
| Arrival to completion | **15,745** | **16,397** |

SPY ID: `c2b4808048584730a4a063a610627a41` (arrival approximately
19:03:25.658 UTC, completion 19:03:41.403 UTC).
QQQ ID: `8bfca0a6605d4507bcb1698989de7c67` (arrival
19:03:25.792 UTC, completion 19:03:42.189 UTC).
Nested spans overlap: do not sum inclusive rows. Zero means below log resolution.
The logs do not separate dependency network time from OS scheduling/CPU contention.
QQQ's history work is materially slower than SPY's; attributing it solely to its
600 ms provider request would be incorrect.

## Findings and changes

1. The API created a fresh Supabase client on every archive read. A dedicated,
   lazily initialized server research client now reuses its transports. A lock
   prevents duplicate cold creation and resolves lazy PostgREST/Storage clients
   before publication. Every query builder stays local to its request. Credentials
   are checked on each access; changed/missing configuration cannot return the
   old identity. Collector clients retain their original construction behavior.
   Never authenticate users, change headers, or sign in/out on this shared client.
2. Public already cached authenticated contexts, but `lru_cache` permits concurrent
   duplicate misses. Both production requests initialized SDK/auth/accounts.
   A lock around context acquisition prevents duplicate cold population; history
   requests retain independent execution. Token refresh/provider behavior and
   the existing two-context cache remain unchanged.
3. NYSE calendar creation/scheduling was repeated by the session gate and economics
   evidence groups (groups include spot). Package-defined schedules now have a
   bounded 128-entry process cache with serialized misses and defensive copies.
   Holiday/early-close checks and downstream gates remain intact. No market data
   or research response is cached. Calendar changes require a process restart,
   like the pinned calendar package itself.
4. Wilder RSI recurrence spent thousands of operations in pandas scalar indexing
   on five years of history. A NumPy array now runs the same seed, recurrence,
   order and float arithmetic, returning the same indexed Series. Exact equality
   regression tests cover short and five-year series; full market-state tests
   exercise the feature behavior.

There was one metadata query in each measured market request, not repeated
archive fetching within that request. The service already injects its verified
record into `run_latest_market`. Historical evidence bundles already reuse
identical contexts within each request. Neither was replaced with a market cache.
Separate current/historical website requests still perform separate verification.

## Before/after local measurements

`scripts/benchmark_research_performance.py` runs baseline source from PR #52 and
the optimized functions in the **same interpreter**, using real REST handlers,
archive download/checksum/identity logic over fixture storage, 1,260 synthetic
daily bars and three repeats per symbol/mode. It asserts complete response equality
for independent/concurrent and before/after runs. Synthetic bars are test-only,
never production data. Provider and Supabase network latency are excluded.

| REST fixture condition | Before range, ms | After range, ms |
|---|---:|---:|
| Current SPY independent | 293.50–386.56 | 50.01–156.80 |
| Current QQQ independent | 291.15–304.11 | 50.69–64.18 |
| Current SPY concurrent | 732.22–760.16 | 118.93–127.50 |
| Current QQQ concurrent | 730.95–745.21 | 110.65–128.01 |
| Historical SPY independent | 281.72–306.72 | 54.35–138.14 |
| Historical QQQ independent | 290.59–305.32 | 53.64–92.38 |
| Historical SPY concurrent | 705.10–729.95 | 135.36–150.16 |
| Historical QQQ concurrent | 715.76–731.84 | 136.17–150.36 |

All samples, including first optimized requests, are included. This benchmark
reduces calculation/REST overhead locally; it is not a production forecast.
An additional offline SDK probe measured pair initialization: separate clients
1,024.76 ms; shared first acquisition 31.08 ms; shared repeated acquisition
0.56 ms. Those sequential measurements include Python import warming and must
not be interpreted as isolated cold-construction speedups. The reliable
regression assertion is one shared construction instead of two, plus reuse.

## Validation

- Full Python: **923 passed, 64 subtests passed in 158.60 s**. This run collected
  seven new tests; an eighth SDK transport test was added during that run.
- Final performance regression file: **8 passed in 2.45 s**, including actual
  Supabase 2.31.0 + HTTPX MockTransport concurrent read queries and rejection of
  tampered archive bytes. The transport test uses no external credentials/network.
- Final combined performance, website/MCP parity and timing suites: **28 passed
  in 6.10 s**, after all code/test edits.
- Website: **87 passed**; typecheck and production build passed.
- Browser: **23 passed in 6.9 s**.
- REST/OAuth MCP/website fixture parity is covered by the existing full suite;
  the benchmark also compares full REST responses for both symbols/modes.
  This is local fixture parity, not live OAuth verification.
- No fabricated market probabilities/expected values; unknown and unaligned
  intraday economics remain unavailable. Archive SHA-256, identity, provenance,
  age/session checks and historical labels are unchanged.

Runtime: Supabase 2.31.0, HTTPX 0.28.1, pandas 3.0.6, NumPy 2.5.3,
pandas-market-calendars 5.4.0, Public SDK 0.1.17.
The Supabase changelog and Python initialization reference were inspected;
the installed synchronous SDK client/query implementation was also inspected.

## Remaining acceptance gate

**Production completion reliably below 12 seconds is not yet verified.** No
optimized code has been deployed. Cold startup, third-party latency and shared
CPU remain variable. The client compatibility test covers the installed SDK,
while production requirements allow other Supabase 2.x versions. The schedule
cache is bounded; many distinct ranges can evict entries and recompute them.
The first shared-client request still pays initialization. Existing Public
token-refresh behavior is unchanged, and no claim of SDK-wide thread safety is
made beyond the existing read-only use and tested Supabase read path.

After a separately approved deployment, run repeated independent and concurrent
SPY/QQQ requests in both modes, including cold and warm acquisition. Correlate
website and backend IDs and retain full traces to verify the actual 12-second
boundary and response parity. Do not mark the latency acceptance criterion
complete from fixture timings. No merge or deployment is part of this PR.
