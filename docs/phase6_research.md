# Phase 6: integrated trade research

Open **Quant Lab > Trade Research** after generating SPY or QQQ Market State Research. Enter a plain credit vertical or load a selected scanner/saved manual trade. Explicitly set current spot, net credit, expiration, observed-session horizon, and additional friction; submit once. The workspace combines the research anchor, structural zones, distributions, selected short-strike context, Phase 5.2 economics, fixed robustness comparisons, and auditable exports. Existing pages and archive writers are unchanged.

## Boundary regression: verified by hand

Anchor 100; resistance 101 and support 99. The five observations are:

| Observation | Terminal return | Max upside | Max downside | Resistance touch / terminal state | Support touch / terminal state |
|---|---:|---:|---:|---|---|
| 1 | +2% | +3% | -0.2% | yes / beyond | no / original side |
| 2 | +1% | +2% | -0.5% | yes / equal | no / original side |
| 3 | 0% | +1% | -1% | yes / original side | yes / original side |
| 4 | -1% | +0.5% | -2% | no / original side | yes / equal |
| 5 | -2% | +0.2% | -3% | no / original side | yes / beyond |

Both sides therefore have touch frequency 3/5, strict finish-beyond frequency 1/5, terminal equality 1/5, rejection conditional on touch 1/3, break-and-hold conditional on touch 1/3, and equality conditional on touch 1/3. Unconditional rejection and break/hold are each 1/5.

The previous engine accidentally missed exact touch/terminal equality because 101/100-1 is not represented exactly as .01. The old tests also conflated equality with beyond and missed a touch. We corrected both layers rather than accepting .20 while leaving touches wrong. Comparisons use the Phase 4 decimal-return tolerance 1e-12. Touch includes equality; terminal beyond is strict outside that tolerance. Equality belongs to neither rejection nor break/hold. Tests cover both signs, exact equality, representation-sized differences and economically larger differences on each side.

## Data and timing

The pure orchestrator accepts an explicit completion cutoff, strictly validates OHLC, and rebuilds features and outcomes on the completed prefix. The UI conservatively excludes today even after close, preserving the existing research convention. Historical target selection uses the latest remaining completed close, while distributions and strike thresholds use explicit current trade spot. No daily bars are manufactured and no option history is inferred. Exchange-calendar verification and provider adjustment limitations remain in source/audit metadata.

All five horizons (1,2,3,5,10 supplied observations) select their own matured sample with the chosen primary method. Each downstream Phase 6 computation independently checks chronological session positions and outcome availability through the existing Phase 4 validator, even if supplied flags incorrectly claim maturity. Missing columns/outcomes stay unknown. Contradictory terminal/high/low paths are excluded. Distributions count each available series independently; joint level behavior requires all three outcomes. Empty samples yield null statistics and zero counts, not zero-risk claims.

## Structure and interpretation

The existing structure detector uses confirmed centered swing highs/lows and 20/50/100/252-session extrema, clustered with completed-history ATR. A pivot requires its right confirmation bars to exist by the research cutoff. Distances and nearest-side eligibility use current trade spot; the zones themselves use only completed prices. Unique structural observation dates are counted so a rolling extreme and pivot on the same day do not inflate the count. These are not counts of all daily or intraday touches. Recency is observed sessions since the most recent contributing date. No automatic role reversal is inferred when current spot crosses an old support/resistance.

Level behavior uses zone centers, not the entire zone width. Touch/rejection and break/hold describe excursion and terminal outcomes; they do not establish event timing or persistent intraday holding. Continuation is the maximum excursion beyond the center among touched observations (including zero at exact touch), in decimal return relative to current spot. Support and resistance are descriptive levels, never predictions.

## Economics and robustness

Phase 5.2 payoff implementation and existing fee treatment are preserved. Every scenario uses exact expiration payoff including partial vertical gains/losses. Existing fees are included once, with explicit additional commission/slippage/exit friction. EV/max risk retains the existing Phase 5.2 entry-risk denominator before additional modeled friction; that convention is labeled. Historical positive-payoff frequency is not forecast POP, and sample EV does not establish future expectancy.

Always display Tight (.75), Default (1), Wide (1.5) frozen tolerance multipliers, Nearest 50, and primary non-overlapping results. None is picked using payoff outcomes. All retain the same submitted horizon and friction. Non-overlap is a dependence diagnostic, not proof of independent samples. Threshold survival/touch/recovery/Wilson context remains separate from payoff frequencies.

## Candidate foundation

Upload a normalized chain CSV with symbol, expiration, type (put/call), strike, bid, ask, observed_at (timezone required), and contract. Optional archive quality/rejection flags are respected. At most 100 input contracts / 200 generated spreads: oversized requests fail and are never favorably truncated. Equal one-lot, same-expiration verticals are built in deterministic contract order with short bid minus long ask. Only mathematically valid positive credits below width are candidates. Missing, crossed, invalid, expired or future-dated observations are reported; duplicate identifiers/strikes are rejected. Numeric fields are explicitly normalized. No mid-price fallback, quote freshness inference, orders, or fill guarantee is provided.

The table includes DTE, structure, strike distances, nearest level, survival/touch frequencies, scenario EV, payoff frequency, risk ratio and N. The submitted observed-session horizon applies to every candidate; DTE never silently selects or rounds it. Users must narrow expirations to their intended research horizon. Quote timestamps and both source leg records are retained in comparison exports. A CSV upload is the adapter boundary for current/provider or archived chain records; this phase does not add another live chain fetcher. All observations remain dated observations, not guaranteed live quotes.

## Provenance and limitations

JSON exports include source metadata, OHLC hash, completion cutoff, selected dates/config, diagnostics, scenario observations, fixed robustness results and submitted trade. Candidate exports retain quote records and research provenance. Results are invalidated when source data or saved trade changes and explicitly labeled as last-submitted inputs. No immutable archive is modified. This MVP supports SPY/QQQ daily research and plain vertical credit spreads; it does not model historical options, assignment, exercise sequence, volatility changes, liquidity, taxes or execution. Deployment is verified separately from tests and Git pushes.
