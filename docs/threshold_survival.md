# Phase 4 — threshold / strike survival research

## Purpose and workflow

This phase measures how selected historical analogs behaved relative to a
normalized underlying-price threshold. It does not price options, reconstruct
option execution, recommend trades, choose strikes, or calculate options EV.

Generate Market State Research, run Historical Analogs, then open Quant Lab →
Threshold Research. Choose put-style (finish ABOVE) or call-style (finish BELOW),
an observed-session horizon, and a price or signed percentage threshold. An
optional shortcut copies one short strike from a saved selected/manual trade.

The Phase 3 sample stays fixed. Changing a threshold, distance grid or threshold
horizon never rematches candidates, changes scaling, or optimizes a parameter.
The original analog-selection horizon is retained in metadata. Longer threshold
horizons can have fewer matured outcomes; shorter horizons do not restore dates
excluded during the original Phase 3 selection.

## Normalization and directional validation

For target-date spot S and threshold price K:

    threshold_return = K/S − 1
    equivalent historical threshold_i = close_i × (1 + threshold_return)

For S=770, K=760, the decimal threshold return is approximately −0.012987013
(−1.2987013%). An analog close of 400 maps to approximately 394.805195.
The raw 760 strike is never applied directly to historical price levels.

Percentage UI inputs use percentage points: enter −1.5 for a threshold 1.5%
below spot; the pure engine accepts −0.015. Only one of price or decimal-return
input is allowed. Spot and threshold price must be finite and positive;
percentage distance must exceed −100%.

Put thresholds normally lie at/below spot and call thresholds at/above spot.
Opposite-side settings fail until the user explicitly checks the acknowledgement.
An accepted opposite-side result displays a prominent warning. Zero distance is
allowed for both styles.

## Events, equality and denominators

Let r be the H-session forward close return, l the minimum future-low excursion,
u the maximum future-high excursion, and d the normalized threshold return.
The Phase 2 excursion windows exclude the signal session and include the next H
observed sessions.

| Event | Put style | Call style |
| --- | --- | --- |
| Terminal survived | r > d | r < d |
| Strict terminal breached | r < d | r > d |
| Terminal equality | r = d | r = d |
| Intraperiod touched/breached | l <= d | u >= d |
| No touch | l > d | u < d |
| Breached then terminally survived | touched AND survived | touched AND survived |

Floating-point equality uses an absolute tolerance of 1e−12 in decimal-return
units. Values inside that band count as terminal equality, never survival;
touch includes the band. This is representation tolerance, not a trading buffer.

Terminal survived, strict breached and equal counts partition all valid terminal
returns. Equality remains in the denominator of survival and breach frequencies;
those two frequencies alone need not sum to one. Touch/no-touch partition all
valid relevant excursions. Missing observations never count as survival,
breach, equality or no-touch.

Denominators are deliberately explicit:

- Terminal valid N: finite, physically valid, matured close returns.
- Touch valid N: finite, physically valid, matured relevant low/high excursions.
- Recovery paired N: observations with both terminal and relevant excursion data.
- Recovery among all valid observations: recovery count / paired N.
- Recovery among breached observations: recovery count / touched count within
  that paired sample. A touch without a known terminal return is not silently
  treated as a failed recovery.

Nonfinite or missing outcomes, or returns/excursions below −100%, are unavailable.
Zero denominators yield unavailable frequencies and intervals, never fabricated
zero or 100% results. Counts and exact denominators are shown separately.

For example, price can cross below a put-style threshold early, then finish
above it: terminal survival YES, no-touch NO, recovery YES. No option
mark-to-market loss, stop execution or trader behavior is inferred.

## Chronology safeguards

The engine accepts the saved Phase 3 analog result, including its target spot,
full session-date sequence and selected sample. It does not fetch a live quote
or overwrite the target with a saved trade's quote.

For each analog signal at position i, target position t and horizon H:

    signal date < target date
    i + H <= t

Both are rechecked from the complete session sequence, even when supplied
as-of flags claim an outcome is available. An explicit false Phase 3 flag is
also respected. Every exported horizon is re-masked; an endpoint exactly on
the target close is eligible. Target/later signals are ineligible, and missing
dates, duplicates or inconsistent symbols are rejected. Outcomes are not
recovered from unknown future bars.

Historical targets therefore use target-date spot and only matured observations.
Tests mutate all OHLC after T and verify target normalization, selected analog
membership and survival outputs remain unchanged. Phase 3 separately tests
invariance of its target features and distance scaling.

## Grid, matrices and distribution context

Default grid magnitudes are 0.5%, 1%, 1.5%, 2%, 2.5%, 3%. They become negative
for put style and positive for call style. Custom grids allow 1–30 positive
magnitudes below 100%; duplicates are removed and magnitudes sorted. This is
display ordering, never an outcome ranking or best-strike search.

The selected-horizon table reports terminal N, touch N, paired N, terminal
survival, touch/breach and recovery frequencies. Separate matrices show survival
and touch percentages for horizons 1,2,3,5,10, with corresponding valid-N tables.
All cells use the same original Phase 3 membership with per-horizon maturity
masks. Matrix frequencies can have different denominators across horizons.

Distribution context displays the 10th/25th/50th/75th/90th percentiles of valid
forward close returns using linear interpolation, plus a histogram with threshold
and median markers. It is context, not a trade grade or forecast.

## Non-overlapping robustness subset

Use observations with both terminal and relevant excursion data available.
Sort by full-history session position, accept the earliest, then skip candidates
whose future windows overlap the last accepted window. The forward window for
signal i is [i+1, i+H]; the next accepted signal j must satisfy j >= i+H.
Thus adjacent future windows are allowed, and their signal/endpoints can touch.

Spacing is in the complete observed-session history, not calendar days and not
row counts within the filtered analog table. The UI compares full sample and
non-overlapping sample counts, survival and touch frequencies. Because the subset
uses paired-complete observations, it also changes missing-data composition when
full terminal and touch denominators differ. This is disclosed.

Disjoint forward windows do not make observations fully independent: market
regimes, common drivers and overlapping predictor histories can remain correlated.
The subset is a robustness diagnostic, not an independence guarantee.

## Wilson interval

Terminal-survival and touch-frequency summaries display a nominal 95% Wilson
score interval. For success count k, valid N=n, p=k/n and z=1.959963984540054:

    denominator = 1 + z²/n
    center = (p + z²/(2n)) / denominator
    half_width = z × sqrt(p(1−p)/n + z²/(4n²)) / denominator
    interval = [center − half_width, center + half_width], bounded to [0,1]

The implementation follows the [NIST Wilson score interval formulation](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm).
The label is “95% Wilson interval for the observed historical frequency.”
This nominal binomial calculation assumes independent Bernoulli observations;
overlapping, selected analogs do not establish that assumption. The interval is
not a calibrated future forecast or a statement of a 95% chance about future
returns. Phase 3 sample warnings remain visible for terminal N, touch N and the
non-overlapping subset.

## Saved-trade integration and POP separation

Valid Phase 1 saved trades must match the target symbol. Extract only negative
quantity option legs, retaining their put/call type and strike. Long protective
wings, premiums, quantities, Greeks and model POP do not affect normalization or
frequency. Multiple short legs, including both condor sides, are selectable for
separate research. No full multi-leg historical P&L is calculated.

The shortcut is restricted to explicit latest-completed-session mode. For
historical targets, a later saved trade is not evidence of an available historical
strike; the shortcut is disabled. Users can enter an explicit hypothetical price
or percentage instead. The selected session horizon is not inferred from the
option expiration date. The market-state target spot is used even if the saved
trade quote differs.

Provider/model POP remains unchanged in its existing workflow. It is never
overwritten, averaged with analog survival, or represented as the same event.

## Exports, limits and validation

Observation CSV includes normalized historical thresholds, terminal prices,
terminal categories, touch/recovery flags, as-of flags and masked outcomes.
Metadata records threshold configuration, originating analog configuration,
denominator conventions, equality tolerance and interpretation. Changed market
datasets or analog settings invalidate the displayed threshold result; changed
threshold controls take effect on submission.

Limitations carried forward and displayed:

- Daily OHLC cannot reveal intraday path or event order; touch uses high/low only.
- No option premium history, Greeks path, bid/ask spread, slippage, early
  assignment or stop-loss execution is modeled.
- Terminal survival is not realized option profitability and ignores credit.
- Provider corporate-action adjustment and exchange-calendar completeness remain
  unverified. Horizons count observed bars, not certified consecutive sessions.
- Today is conservatively excluded; Public history can be revised and may not
  represent archived point-in-time values.
- Sample selection, features, tolerances and clustered/overlapping observations
  affect results. Historical frequencies are not calibrated future probabilities.

The full suite passes 133 tests: 100 existing and 33 new Phase 4 tests. New tests
cover normalization, both styles, equality, touch, recovery denominators, price
and percentage input, directional acknowledgement, grids, matrices, Wilson,
missing/empty samples, non-overlap boundaries, as-of rechecks, post-T mutation,
PCS/CCS/condor extraction, malformed trades, UI modes and exports. Existing
tests exercise Phases 1–3, Portfolio Research and Pulse. Tests use deterministic
fixtures and do not certify actual provider data quality.

No options EV, historical options P&L backtesting, recommendations, best-strike
selection, rankings, grades, ML, parameter optimization or automated trading is
added. Phase 5 is not started.
