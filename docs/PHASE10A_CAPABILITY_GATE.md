# Phase 10A capability gate

Baseline: 4ef8d5bb1487af1612d8be33cf53f2b2c3be7124, tested Phase 9 index support, deployed and pinned on Render; not merged.

## Confirmed chain-quality defect

October 1 production evidence includes bid timestamps of 2015-01-01T05:00:00Z on distant SPXW261001C09600000, SPXW261001C10000000 and XSP261001C00814000/816/817/818 contracts. Existing chain_quality.timing takes the oldest timestamp across all contracts; this produces roughly 370 million seconds despite fresh selected legs. The calculation reflects returned old values; the defect is ambiguous aggregation scope, not a timezone or epoch conversion error. Whether Public uses this 2015 date as a sentinel is unverified, so it is retained, never silently replaced or clamped.

The fix adds explicit entire-chain newest/oldest observation timestamps and ages, retrieval/evaluation times, fresh coverage counts/percentage and missing/future counts. It reports consumed-contract quality independently on vertical and scan evidence, using both bid and ask timestamps and the existing 900-second option warning policy. Chain coverage is informational, not an all-chain eligibility gate. Cache hits recompute age. The option timestamp parser now delegates to the existing shared epoch-seconds/milliseconds normalizer; this was a separate deterministic compatibility issue, not the cause of the observed 2015 values.

## Intraday gate

Public documentation exposes aggregation overrides and DAY/WEEK session toggles:
https://public.com/api/docs/resources/market-data/get-bars-v2-with-aggregation

A read-only runner audit tests actual returned intervals, depth, sessions, timestamps, missing/duplicate observations and volume for SPY/QQQ EQUITY and XSP/SPX INDEX. Requested aggregations alone are not capability evidence. Adjustments and bar start/end conventions must not be inferred solely from enum names. No intraday model may use daily bars as fabricated paths. Production stays pinned to Phase 9 while this gate is unresolved.

## Gate result: STOP — insufficient historical intraday depth

Live audit October 1, 2026 at 15:09–15:10 EDT, 100 symbol/period/aggregation requests:
https://github.com/rooster51/AlphaOS/actions/runs/36912153845

| Symbol | 1-minute | 5/15/30-minute | Hourly | Volume | Overnight |
|---|---|---|---|---|---|
| SPY | DAY only | DAY/WEEK; 4 completed regular sessions plus today | DAY/WEEK/MONTH; 22 dates including today | Positive | DAY overnight and WEEK ALL_SESSIONS returned observations |
| QQQ | DAY only | DAY/WEEK; 4 completed regular sessions plus today | DAY/WEEK/MONTH; 22 dates including today | Positive | DAY overnight and WEEK ALL_SESSIONS returned observations |
| XSP | DAY only | DAY/WEEK; 4 completed regular sessions plus today | DAY/WEEK/MONTH; 22 dates including today | Zero | No overnight session fields with data; occasional post-close index observations are not overnight trading |
| SPX | DAY only | DAY/WEEK; 4 completed regular sessions plus today | DAY/WEEK/MONTH; 22 dates including today | Zero | No overnight session fields with data; occasional post-close index observations are not overnight trading |

ONE_MINUTE WEEK/MONTH/QUARTER/YEAR returned HTTP 400 for all symbols. FIVE_MINUTES, FIFTEEN_MINUTES and THIRTY_MINUTES MONTH/QUARTER/YEAR returned HTTP 400. ONE_HOUR QUARTER/YEAR returned HTTP 400. These are verified limits for the tested endpoint/period combinations, not a claim that no other vendor or future Public endpoint can provide deeper data.

WEEK five-minute regularMarket counts were SPY/QQQ 1,117 each (ALL_SESSIONS merges multiple session types), XSP 408 and SPX 404. MONTH hourly counts were 175/175/196/178 respectively. The index week has five date labels, including today's incomplete session; numerous ETF calendar labels are overnight fragments and must not count as independent matched trading sessions. Hourly bars cannot resolve a 14:03 or 15:30 start without including time before entry or dropping relevant price movement. Four completed recent days are not a defensible time-of-day research sample or a representative set of 1DTE paths.

Timestamps explicitly carried -04:00 and normalized to UTC. Returned DAY regular observations start at 09:30 ET; hourly bars align at 09:00, requiring boundary treatment. The current endpoint appends a sub-minute timestamp with repeated OHLC/volume-like values; one SPX appended observation even had close above the returned high. It must not be treated as a completed bar or double-counted volume. The audit found no duplicate exact timestamps or parse failures in successful requests, but that does not establish complete historical session coverage. WEEK interval gaps and post-close observations require calendar-based filtering, not forward filling. Split/adjustment behavior and authoritative bar start/end conventions remain unverified. No longer-term corporate-action inference is justified by this sample.

## Smallest alternative architecture (proposal only)

1. Add an intraday data adapter with explicit symbol, timezone, interval-start/end convention, session, adjustment provenance, coverage and dataset version. Obtain existing, licensed 1- or 5-minute history with materially deeper regular-session coverage, exact SPX/XSP identities, and overnight gap preservation. Public remains the live quote/option source. Start with at least 60 completed sessions and require a declared minimum matched N (e.g. 30); neither number guarantees statistical adequacy. Validate coverage and sensitivity before release.
2. A separate exchange-calendar time-state module computes remaining regular trading minutes, excluding overnight hours, holidays/weekends and handling early closes. Disclose that session close is an analysis horizon unless contract expiration/settlement timing is verified. Friday-to-Monday next-session expiry is calendar DTE 3, not silently renamed DTE 1.
3. Use configurable five-minute entry buckets only when supported by data. Choose a completed, clearly timestamped entry boundary, expose requested versus effective start and avoid including a bar's pre-entry range. One observation per historical session; 0DTE ends at that session close, 1-next-session paths retain the close-to-open gap and continue to next session close. Reject incomplete paths; never interpolate daily OHLC. Expose horizon/calendar-DTE separately. Missing coverage reduces N rather than fabricating bars.
4. A separate intraday engine rebases actual path returns to live spot, evaluates short/breakeven/long levels, touch/terminal/recovery and excursions, and computes expiration-horizon spread payoff. Keep historical frequencies and descriptive EV separate from all Phase 9 multi-session fields. Disclose serial dependence; do not use an unqualified independent-binomial confidence interval for overlapping paths.
5. Remaining movement should first be descriptive empirical matched-path return quantiles/RMS with method, sample and timestamps. An option-implied alternative requires verified IV units, annualization and contract expiry time; do not silently scale daily IV by remaining wall-clock hours or combine methods without validation.
6. ETF volume makes current-session volume-weighted reference research plausible, but OHLCV alone cannot reconstruct exact trade-weighted VWAP unless the bar's volume-weighted price/turnover is available. Label any bar-price approximation explicitly; never call an EMA VWAP. SPX/XSP have no underlying volume here, so VWAP is unavailable. Opening 5/15/30-minute and prior-day levels are plausible after bar-validation; index overnight levels stay unavailable. None are implemented at this gate.
7. Load/version intraday history once per symbol/request and reuse matched paths across the unranked candidate curve. Cache by dataset version, symbol, analysis bucket/effective entry, horizon and sample settings; current quote and option legs retain their separate freshness checks. Precompute path-return matrices so candidate loops evaluate levels/payoff rather than rerun history retrieval.
8. Extend the existing unified REST/MCP response with a separate expiration_matched_research section; retain 14 tools. Candidate curve includes associated short delta and current credit/structure distances, with no ranking. Expected future files: modules/intraday_data.py, intraday_time.py, intraday_research.py; alphaos_api/provider.py, service.py, phase9.py, phase9_contracts.py and mcp_server.py; modules/unified_trade.py and unified_trade_view.py; focused time/path/coverage/integration tests. No OAuth changes.

A growing archive could eventually supply depth, but it would not solve today's historical requirement and scheduled collection is explicitly out of scope. No collector, scheduled scan, monitor, alert, execution or scoring system was added. No intraday model, expected-move model, VWAP, opening-range, candidate curve, or expiration-matched EV was fabricated. No Phase 10A deployment is justified by this failed data gate; production remains pinned to 4ef8d5bb1487af1612d8be33cf53f2b2c3be7124.

## Validation

Focused chain-quality/audit/API compatibility suite: 50 passed. Complete local suite: 453 passed, 40 subtests. GitHub full CI for the gate implementation passed:
https://github.com/rooster51/AlphaOS/actions/runs/36912192743

Before/after intraday-engine runtime comparison is unavailable because the engine was deliberately not built. Provider audit successful request times were sub-second in the GitHub runner; these are not Render workflow performance estimates. Existing production workflow timings are recorded separately in the PR. No defensible runtime forecast exists until a usable dataset is profiled; request-scoped reuse is the planned mitigation.
