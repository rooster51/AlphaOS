# Phase 2: market state and forward research outcomes

## Inputs and availability

The pure engine requires a chronological, single-symbol daily OHLC frame and
an explicit `completed_before` cutoff. It preserves warm-up rows. Invalid order,
duplicate/malformed dates, missing/mixed symbols, missing/nonfinite/nonpositive
prices, inconsistent OHLC bounds, and weekend bars are rejected. No sorting,
backfilling, forward-filling, or fabrication of missing bars is performed.

Public mode supports SPY/QQQ and FIVE_YEARS/TEN_YEARS through the existing
regular-market ONE_DAY adapter. No supported maximum-history endpoint already
exists, so no MAX option is invented. Today and later dates are conservatively
excluded using the New York date, even after today's close. Provider daily
timestamps retain their UTC calendar-date labels, matching existing research.
Features for T are available after close T, not for an assumed entry at open T.

## Formulas and warm-up

C, H, L mean close, high and low. Percentages/volatilities are decimal fractions
in tables/CSV (0.01=1%). Observation numbers below are one-based.

| Fields | Formula/convention | First available |
| --- | --- | --- |
| return_Hd; H=1,2,3,5,10,20 | C[T]/C[T-H] − 1 | H+1 |
| ema_N; N=9,21,50,200 | E[1]=C[1]; E[T]=a*C[T]+(1−a)*E[T−1], a=2/(N+1); mask first N−1 values | N |
| distance_ema_N_pct | C/EMA_N − 1 | N |
| true_range | max(H−L, abs(H−prior C), abs(L−prior C)); first bar H−L | 1 |
| atr_14 | Arithmetic mean of trailing 14 TR values | 14 |
| atr_pct | ATR14/C | 14 |
| distance_ema_N_atr; N=21,50 | (C−EMA_N)/ATR14; NaN when ATR=0 | N |
| rsi_14 | Wilder gains/losses described below | 15 |
| realized_vol_Nd; N=10,20,60 | Sample SD (ddof=1) of trailing N log(C[T]/C[T−1]) values × sqrt(252) | N+1 |
| high_20 / low_20 | Maximum HIGH / minimum LOW of trailing 20 observations including T | 20 |
| range_position_20 | (C−low20)/(high20−low20); NaN for zero denominator | 20 |
| distance_high_20_pct | C/high20 − 1 | 20 |
| distance_low_20_pct | C/low20 − 1 | 20 |
| ema_structure | bullish: C>EMA9>EMA21>EMA50; bearish: C<EMA9<EMA21<EMA50; mixed otherwise, including equality | 50 |

RSI: seed G and D with arithmetic mean positive gains and absolute negative
losses from the first 14 close changes. Subsequently update each with
(13*prior+current)/14. RSI=100−100/(1+G/D). D=0,G>0 gives 100; G=0,D>0 gives 0;
both zero gives 50. Missing history remains missing.

EMA recursion matches existing Pulse convention with added warm-up masks;
the seed depends on the supplied history start. ATR retains existing AlphaOS
daily arithmetic-mean ATR, not Wilder ATR. Existing helpers drop rows and mix
in UI diagnostics, so the research engine implements these formulas directly
without changing existing behavior. All windows are trailing.

## Future labels: separate function, table and CSV

For H=1,2,3,5,10:

- `future_return_Hs` = C[T+H]/C[T] − 1.
- `future_high_excursion_Hs` = max(HIGH[T+1], …, HIGH[T+H])/C[T] − 1.
- `future_low_excursion_Hs` = min(LOW[T+1], …, LOW[T+H])/C[T] − 1.

Signal-day high/low is excluded. Every label requires H future completed
observations; the last H rows are NaN. Labels become available only after close
T+H. Exact signed excursions are not clipped: a gap wholly above the signal
close can yield a positive low excursion, and wholly below can yield a negative
high excursion.

`market_state_features()` never imports outcomes. `forward_outcomes()` returns
date/symbol and labels only. Exports stay separate. Each CSV includes its kind
and JSON metadata containing source, requested period, actual coverage,
data-read timestamp/cache limitation, OHLC SHA256, engine version, formulas and
quality audit. A separate JSON manifest is available too.

## Data limitations

- Missing OHLC values fail validation. Absent weekdays are audited as possible
  gaps: without an authoritative exchange calendar they may be holidays or
  missing provider bars. Gaps over seven calendar days get an extra warning.
- Horizons count observed bars. Do not assume they are consecutive exchange
  sessions until calendar completeness is verified. Pure functions accept
  optional `expected_sessions`, rejecting missing/extra dates within the input
  span; the Public UI does not yet have a verified exchange calendar.
- Exact upstream retrieval time is unavailable from the existing cached
  adapter. Metadata records data-read time and the 300-second cache limit.
- Split/dividend adjustment and historical revisions are unverified. Corporate
  actions can distort all price-derived features. No total-return or guaranteed
  point-in-time archival-data claim is made.
- Requested period does not guarantee coverage. Actual dates/counts are shown.
  No synthetic fallback is used. Today's completed bar is also excluded until
  an authoritative close/half-day schedule is available.

## Tests and scope

The complete suite passes 71 tests: 47 existing and 24 new. New tests include
hand-verifiable indicators, returns/excursions, warm-up/tail NaNs, malformed
input, gap audits, exports, SPY/QQQ provider/UI flows, failed-refresh handling,
and preserved Pulse execution. The anti-look-ahead test changes all prices after
T and asserts every predictor through T is unchanged, also comparing truncated
history; future outcomes change. Existing integration tests run Phase 1 options
analysis and synthetic Portfolio Research. Provider tests use fixtures and do
not establish actual Public history quality.

No analogs, similarity, option survival, expectancy, grades, signals, rankings,
optimization, machine learning or automated trading is added. Before downstream
research, resolve session completeness, corporate actions, point-in-time
provenance, entry timing and chronological validation.
