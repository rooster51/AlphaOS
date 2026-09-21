# Phase 3 — historical analog research

## Purpose and workflow

An analog is a prior observed session whose measured market conditions resemble
a selected target session. This is descriptive conditional historical research,
not a calibrated forecast or an options trading system.

1. Generate SPY or QQQ history in Quant Lab → Market State Research.
2. Open Historical Analogs and choose latest completed session or a historical
   target date from that dataset.
3. Select tolerance matching or standardized nearest neighbors, a research
   horizon, and the EMA-structure rule. Adjust tolerances manually if desired.
4. Inspect sample counts, matching transparency, outcomes, the date timeline,
   sensitivity and the exportable analog table.

Changing the dataset hides stale analog results. Changed controls take effect
only after submission. Invalid target/warm-up input clears the prior result.

## Matching features and default tolerances

The UI uses exactly five numerical features and one descriptive category:

| Feature | Inclusive tolerance around target |
| --- | --- |
| return_5d | ±0.02 decimal return (2 percentage points) |
| rsi_14 | ±10 RSI points |
| distance_ema_21_atr | ±0.75 ATR |
| realized_vol_20d | ±0.05 annualized decimal volatility (5 percentage points) |
| range_position_20 | ±0.20 on the 0–1 scale |
| ema_structure | Exact match by default |

These starting values are research choices, not statistically optimized
parameters. No automatic widening is performed. The pure API permits a unique,
nonempty subset of the five documented numerical fields; unknown fields,
including all forward-outcome fields, are rejected. The UI deliberately does
not expose a large feature-selection space.

Turning off the exact EMA rule ignores the category entirely; there is no hidden
categorical penalty. With exact matching, missing target structure is an error
and unavailable candidate structures are excluded. The existing Phase 2 strict
EMA ordering definition is unchanged; the label is not a directional trade call.

## Chronology and as-of maturity

The engine requires the complete chronological Phase 2 feature row sequence,
including warm-up rows. Never drop rows before calling the engine: session
offsets refer to positions in that sequence. Inputs must have unique dates and
one SPY/QQQ symbol. The engine does not sort or repair malformed inputs.

For target at row t and chosen research horizon H, a candidate at row i must:

- Have date strictly before the target (i < t).
- Satisfy i+H <= t: its H-th future observed bar has completed by target close.
- Have complete finite matching features and positive finite close.
- Satisfy the selected matching method and optional exact category rule.

The UI explicitly rebuilds Phase 2 predictor features using raw OHLC only through
target T before matching. The engine fits no statistics on T or later dates.
This is an after-close-T analysis, not a claim that the results were known at
open T or available for execution at the exact closing price.

All five outcome horizons are attached **after** feature-only selection.
For each attached horizon h, the outcome is independently blanked unless
i+h <= t. An outcome ending exactly on T is allowed. Consequently, a sample
chosen for H=1 can have fewer valid 10-session outcomes. Choosing a longer
research horizon can also change membership and the scaling pool: that is an
explicit date-availability restriction, not selection based on returns.

Outcome values, missingness, positivity and magnitude never determine matching,
distance or scaling. Missing/nonfinite labels reduce their reported valid N;
they do not remove feature matches. Outcomes are aligned by date and symbol,
not by their DataFrame row order. No target-date outcome enters the sample.

## Method A: tolerance filter and funnel

All active numerical differences must satisfy abs(candidate−target) <= tolerance
(with 1e−12 absolute allowance for floating-point boundary representation).
Tolerance matches are displayed chronologically, with signed differences from
the target. There is no arbitrary sample-size cap for this method.

Deterministic funnel order:

1. Strictly before target.
2. Selected-horizon maturity by target close.
3. Complete matching features (including category when required).
4. Exact EMA structure, when enabled.
5. 5D return.
6. RSI14.
7. EMA21 ATR distance.
8. 20D realized volatility.
9. 20D range position.

Each stage reports remaining and newly removed observations. Independent pass
counts apply each matching criterion to the same complete, matured candidate
pool. They identify restrictive individual features without conflating prior
filters; sequential exclusions still depend on the documented order.

## Method B: standardized nearest neighbors

For every numerical feature j, fit mean mu_j and population standard deviation
sigma_j (ddof=0) on the **complete, matured prior candidate pool before EMA
category filtering**. The target is never in this pool.

    z_ij = (x_ij − mu_j) / sigma_j
    z_Tj = (x_Tj − mu_j) / sigma_j
    distance_i = sqrt(sum_j((z_ij − z_Tj)^2))

Numerical features have equal standardized weight. Exact EMA matching is a
separate filter, enabled by default. Available N choices are 25, 50, 100 and
200, with 100 the default. Return at most N matches; never manufacture more.
Sort by ascending distance, then ascending date to break ties deterministically.

Features with nonfinite or <=1e−12 sigma are omitted and disclosed. If all
features are omitted, distances are zero, and dates break ties; the UI explicitly
warns that this is not meaningful evidence of similarity. Mean, scale, active
status and fitted sample count are available in Matching transparency and CSV
metadata. There is no learned model, parameter fitting against outcomes or
maximum-distance acceptance threshold. Even the nearest states may be dissimilar;
inspect their distance and features.

## Outcome summaries and charts

For horizons 1,2,3,5,10, summaries report valid close-return N, positive/negative
frequencies, mean, median and 10/25/75/90th percentiles. Zero returns count as
neither positive nor negative, so those frequencies need not sum to 100%.
Percentiles use linear interpolation. No-valid-outcome statistics stay NaN;
the application never displays an invented zero frequency.

Excursion summaries retain Phase 2 signs and formulas: median high excursion,
median low excursion, 10th-percentile low excursion and 90th-percentile high
excursion. High and low valid counts are reported separately. Signal-day highs
and lows are excluded by Phase 2; signed excursions are not clipped.

The histogram uses the selected display horizon's valid close returns, with
zero and median lines. The percentile chart shows 1/2/3/5/10-session historical
percentiles; it is not a forecast cone or confidence interval. The timeline and
yearly counts show clustering. Nearest-neighbor timelines also show distance.
Tables in Observed outcomes show percentage units; the analog table and CSV
retain decimal fractions (0.01=1%). Distance is not a probability.

## Sample warnings and sensitivity

The following are descriptive warnings, not statistical confidence statements:

| Sample N | Message |
| --- | --- |
| <30 | Very small historical sample. Results are highly uncertain. |
| 30–99 | Small historical sample. Interpret cautiously. |
| 100–249 | Moderate historical sample. |
| >=250 | Larger historical sample, but historical frequency is not a guarantee of future outcomes. |

Warnings appear for both the final analog sample and selected horizon's valid
outcome count. No result is labeled a trade win rate.

Tolerance sensitivity compares TIGHT=0.75×, DEFAULT=1×, WIDE=1.5× the documented
starting numerical tolerances. These are not multipliers of manually edited
tolerances. All five numerical features, the same target, maturity horizon and
EMA rule are used for each preset. Each reports total sample N and per-horizon
valid N, median return and positive-return frequency. No preset is chosen,
ranked or recommended based on future returns.

## Export, limitations and interpretation

CSV contains every selected analog, matching features, close, applicable
distances/differences, as-of flags, and all masked forward labels. Metadata
records engine version, target, settings, candidate audit, fitted scales,
warnings, and the Phase 2 source metadata. This joined export is research-only;
it must never be fed wholesale into live predictor code.

Carry-forward limitations remain:

- Public split/dividend adjustment is unverified. Corporate actions may distort
  features; no total-return claim is made.
- Exchange-calendar completeness is not certified; horizons count observed
  bars, not guaranteed consecutive exchange sessions. Possible gaps are audited.
- Today is conservatively excluded by the provider loader, even after close.
  Latest mode means the latest completed bar in the loaded snapshot, not a
  guarantee that the provider has supplied the most recent possible session.
- Public history may be revised; retrospective source data is not guaranteed
  to be an archived point-in-time snapshot. Exact upstream retrieval time is
  unavailable from the existing cached adapter.
- Results depend on feature choice, tolerance, sample history, seed conventions
  and target. Similar measurements do not imply identical market conditions.
- Daily analogs can cluster. Overlapping horizons create correlated outcomes;
  raw N is not an effective independent sample size.
- Historical frequencies describe this selected past sample. They are not
  calibrated future probabilities, evidence of a trading edge, or guarantees.

Resolve session completeness, corporate actions and point-in-time provenance
before treating downstream validation as established. Phase 3 does not add
options survival, options EV, recommendations, PCS/CCS selection, historical
option-chain backtests, ML, optimization or automated trading.

## Validation

The full suite passes 100 tests: 71 existing and 29 Phase 3 tests. New coverage
includes both matching methods, boundaries, scaler formula/pool, ties and
constant dimensions, N limits, funnel counts, warnings, statistics/percentiles,
sensitivity, CSV metadata/masking, latest/historical UI modes, stale results,
empty samples and warm-up errors. Mandatory leakage tests show:

- Every candidate precedes target and never matches itself.
- Outcomes ending after T are excluded by per-horizon as-of masks.
- Changing raw OHLC after T leaves target features, membership, distances,
  scales, attached known outcomes and summaries unchanged.
- Changing outcome values or missingness cannot change membership or distance.
- Forward-outcome columns cannot be configured as similarity features.

Existing tests exercise Phase 1, Phase 2, Portfolio Research and Pulse. UI tests
use deterministic fixtures; they do not validate actual provider data quality.
