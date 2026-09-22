# Daily research and separate options archive — v1

## Execution and credentials

Run from the repository root with Python 3.12:

```sh
python -m pip install -r requirements-daily.txt
python scripts/run_daily_quant.py
```

The runner has no Streamlit dependency. `DailyPublicProvider` uses the pinned
Public SDK's authenticated transport, the same read-only market-data routes as
the interactive app, and shared account-selection helpers. Daily history reuses
the fixed `SINCE_PURCHASE/ONE_DAY` ten-year adapter. It does not use a second
market-data provider or import positions/orders.

GitHub repository Actions secrets:

| Name | Requirement |
| --- | --- |
| `PUBLIC_API_SECRET` | Required Public personal API secret with history/market-data access. Set directly in GitHub Settings → Secrets and variables → Actions. Never put it in this repository, configuration JSON or a workflow input. |
| `PUBLIC_ACCOUNT_NUMBER` | Optional preferred account number or ID, as in the existing app. Recommended for deterministic selection when the key sees several accounts. Otherwise existing brokerage/individual-account scoring is used. |

`PUBLIC_OWNER_EMAIL`, Alpaca, and Supabase credentials are not used. Streamlit
Cloud secrets are not transferred to Actions. Public account IDs are used only
in authenticated request paths, never saved or logged. The CLI suppresses HTTP
logging and prints fixed status/reason codes, not provider exception strings.

The workflow is `.github/workflows/daily-quant.yml`, scheduled at **22:23 UTC
Monday–Friday** (18:23 EDT / 17:23 EST). It also supports manual dispatch, without
force or historical-date inputs. NYSE calendar 5.4.0 gates the actual run: no
weekend/holiday collection, and no collection before both exchange close and
17:00 America/New_York. Early closes retain the 17:00 floor. Scheduled runs may
be delayed by GitHub; exact execution time is not promised. A delayed run on a
different date never backdates current option quotes to a missed session.

The calendar is an installed, version-recorded dependency and may need updates
for newly announced closures. It is also used to validate the observed daily
history against exchange sessions. The scheduled runner can include **today's
completed bar** after its timing gate; the interactive Quant Lab retains its
more conservative next-day policy. The Phase 2 formulas themselves are unchanged.

If Public has not returned today's completed bar for either symbol, exit
successfully with `latest_completed_session_not_returned`, without artifacts.
If only one symbol succeeds, preserve a clearly marked partial research snapshot
with the other symbol's status. Errors never turn unavailable observations into
zeros or fabricated sessions. Options retrieval is independent of a research
calculation failure; current option observations can still be retained.

The workflow commits available artifacts to `main`, including on partial
collection failure, and uploads a 90-day recovery artifact. It uses only the
repository `GITHUB_TOKEN` with `contents: write`; branch protection must permit
that bot's archive commits. A failed rebase/push fails visibly and retains the
uploaded recovery artifact; it never force-pushes. These files then reach the
Streamlit checkout through the existing deployment connection. GitHub can
disable schedules in inactive public repositories. Check workflow status.

No live Actions authentication is certified by fixture tests. If the repository
secrets are missing, expired, or lack market-data access, the job fails with
`provider_configuration_or_authentication_failed`. Configure those secrets to
activate real daily collection. No sample market artifacts are installed as
though they were genuine live observations.

## Storage, immutability and configuration

| Path | Contents |
| --- | --- |
| `config/daily_quant.json` | Frozen research configuration and configurable options collection universe. |
| `data/daily_quant/YYYY-MM-DD.json` | One research snapshot for that completed NYSE session. |
| `data/options/YYYY-MM-DD/SPY.json.gz` and `QQQ.json.gz` | Independent options snapshots for the actual New York collection date. |
| `data/archive_manifest.json` | Derived inventory, never authoritative over the files. |

JSON is UTF-8, canonical key ordering, finite numbers only; unavailable values
are JSON `null`. Gzip uses zero metadata time for deterministic encoding. Atomic
no-overwrite publication plus a run lock prevents silent replacement. Existing
research/options files are skipped independently; same-date retries may create
an absent options file but never rewrite a partial existing snapshot. Data from
different collection times is not silently merged.

Explicit local debugging: `python scripts/run_daily_quant.py --force-rebuild`.
This preserves the previous exact bytes in a sibling `rebuild_backups/` directory,
named by their SHA-256, then atomically replaces the active file. `rebuild:true`
marks rebuilt artifacts. Rebuilds are not original point-in-time captures.
Force is refused when `GITHUB_ACTIONS=true`; the scheduled workflow never uses it.
Backups are excluded from the normal manifest counts. A stale `.daily-quant.lock`
after a killed local run causes a clear failure; verify no runner is active
before removing that lock. `--data-dir` can isolate developer test archives.

Config v1 fields:

| Field | Value / units |
| --- | --- |
| `version` | `daily-quant-config-v1`; change deliberately for configuration revisions. Full content is also hashed. |
| `symbols` | Default `[SPY,QQQ]`; a nonempty subset is allowed. |
| `history` | `TEN_YEARS`, using the existing explicit ten-calendar-year start request. |
| `analog.method`, `horizon` | `tolerance`, 3 observed sessions. |
| `analog.numerical_features` | Phase 3's five default feature names, in their existing order. |
| `analog.tolerances` | `return_5d:0.02`, `rsi_14:10`, `distance_ema_21_atr:0.75`, `realized_vol_20d:0.05`, `range_position_20:0.20`. These exactly match Phase 3 DEFAULT. |
| `analog.exact_structure` | `true`. |
| `sensitivity` | Boolean; default true, using existing Tight/Default/Wide routine and multipliers 0.75/1/1.5. |
| `thresholds.distances` | Positive decimal magnitudes `[0.005,0.01,0.015,0.02,0.025,0.03]`. |
| `thresholds.modes`, `horizons` | Both `put,call`; 1/2/3/5/10 observed sessions. |
| `options.min_dte`, `max_dte` | Inclusive calendar-day DTE, default 0–10; configurable nonnegative integers through 365. |
| `options.strike_band` | Decimal radius around observed underlying last price, default 0.10. Inclusive boundaries; configurable strictly between 0 and 1. |
| `calendar`, `earliest_collection_hour_et` | `NYSE`, 17. |

Research defaults are validated against the existing Phase 3 constants and are
not optimized. Changing those defaults requires an intentional implementation/
configuration version change, not a daily fitting step. Unknown configuration
fields are rejected, preventing accidental credentials from being copied into
snapshots. `config_sha256` fingerprints the complete canonical config.

## Research document (`daily-quant-v1`)

| Field | Meaning |
| --- | --- |
| `schema_version` | Structural contract `daily-quant-v1`. |
| `session_date` | Latest calendar-completed NYSE session, YYYY-MM-DD. Every successful symbol must end on this exact session. |
| `generated_at` | UTC ISO-8601 collector timestamp after research processing, not a guaranteed market-close timestamp. |
| `config_version`, `config_sha256`, `config` | Identifier, SHA-256 and complete validated configuration above. |
| `engine_versions` | `market_state`, `historical_analogs`, `threshold_research` engine identifiers; `dependencies` records pandas, numpy, Public SDK and calendar package versions. |
| `code_revision` | Full 40-character commit SHA recorded from the actual Actions checkout, or null outside Actions unless supplied programmatically. |
| `provider` | `Public`. |
| `status` | `complete` if every configured symbol succeeded, otherwise `partial`. No research document is created when none succeed. |
| `warnings` | Interpretation, dependence, adjustment and data-revision limitations. |
| `rebuild` | Boolean, explicit developer replacement rather than original daily capture. |
| `symbols` | Object keyed by configured SPY/QQQ. Successful entries below; unavailable entries have only `status` and a fixed `reason` code. |

A successful symbol contains `status:complete`, `market_state`,
`source_metadata`, `historical_analogs`, and `thresholds`.

### Market-state fields

These are the existing Phase 2 latest feature row, not new calculations:

| Field / family | Units |
| --- | --- |
| `date`, `symbol` | Session timestamp at normalized UTC calendar date, symbol string. |
| `open`, `high`, `low`, `close` | Provider OHLC in USD per underlying share. |
| `return_{1,2,3,5,10,20}d` | Trailing signed decimal returns, e.g. 0.01 = 1%. |
| `ema_{9,21,50,200}` | USD per share; recursive EMA seeded as in Phase 2. |
| `distance_ema_{9,21,50,200}_pct` | `(close/EMA)-1`, decimal fraction despite the `pct` suffix. |
| `distance_ema_{21,50}_atr` | Price distance divided by ATR14, dimensionless ATR units. |
| `true_range`, `atr_14` | USD per share; ATR is the existing 14-observation arithmetic mean, not Wilder ATR. |
| `atr_pct` | ATR14/close, decimal fraction. |
| `rsi_14` | Wilder RSI, 0–100. |
| `realized_vol_{10,20,60}d` | Annualized decimal sample log-return volatility, sqrt(252). |
| `high_20`, `low_20` | Trailing 20-observation high/low, USD per share. |
| `range_position_20` | Dimensionless location within trailing high/low range, normally 0–1. |
| `distance_high_20_pct`, `distance_low_20_pct` | Close divided by the corresponding trailing bound minus one, decimal fraction. |
| `ema_structure` | `bullish`, `bearish`, `mixed`, or null while unavailable. |

Warm-up/unavailable values remain null. `source_metadata` preserves Phase 2's
`version`, `symbol`, `start`, `end`, `observations`, `source_ohlc_sha256`,
`feature_conventions`, `outcome_conventions`, `audit` and provider metadata.
`source`, `requested_period`, `completion_policy` describe this collection.
`audit` records `excluded_uncompleted`, `completed_before`, `calendar_verified`,
`possible_missing_weekdays`, `max_calendar_gap_days`, and `warnings`. An empty
calendar mismatch check is required for this runner; the possible-weekday list
still includes exchange holidays. See [Phase 2 conventions](market_state.md).

`provider_diagnostics` preserves requested/provider periods, provider,
aggregation, start/end/request dates, retrieval timestamp, adjustment statement,
returned/completed row counts and date extrema, exclusion count, invalid/duplicate
date counts, weekend rows, null/nonfinite/nonpositive OHLC counts, inconsistent
OHLC row count, count of absolute close moves over 25%, regular expected bars,
maximum calendar gap, calendar-verification flag and stage. Counts are integers;
dates/times are ISO strings. The provider adapter's calendar flag describes its
own gross coverage check; the dataset audit records the runner's subsequent
authoritative-calendar check. See [provider diagnostics](public_history_debugging.md).

### Historical analog fields

| Field | Meaning / units |
| --- | --- |
| `config` | Existing Phase 3 version, symbol, target_date, method, horizon, numerical_features, tolerances, exact_structure, neighbors. `neighbors` remains engine metadata and is unused in tolerance matching. |
| `candidate_n`, `final_n` | Eligible complete candidates before tolerance/category filters; final selected analog count. |
| `audit` | Counts `prior_dates`, `as_of_matured_dates`, `eligible_dates`, `missing_feature_dates`. |
| `feature_funnel[]` | Each sequential `filter`, integer `remaining` and `removed` counts. |
| `independent_passes[]` | `feature`, `passed`, `eligible`, `eliminated` counts before combined filtering. |
| `sample_warning`, `notes[]` | Existing Phase 3 interpretation text. |
| `matched_dates[]` | Exact selected signal-session dates, YYYY-MM-DD. |
| `sensitivity[]` | `preset`, `multiplier`, `sample_n`, `horizon`, `n_valid`, `median_return`, `positive_frequency`; 15 rows when enabled. Decimal returns and 0–1 historical frequencies. |
| `outcome_summaries[]` | One summary per 1/2/3/5/10 observed sessions, with horizon-specific maturity masks. |

Outcome summary fields: `horizon`, `n`, `n_high_excursion`, `n_low_excursion`
are integer horizon/valid sample counts. `positive_frequency` and
`negative_frequency` are historical fractions (zero returns are neither).
`mean_return`, `median_return`, `p10_return`, `p25_return`, `p75_return`,
`p90_return`, `median_high_excursion`, `median_low_excursion`,
`p10_low_excursion`, `p90_high_excursion` are signed decimal returns/excursions.
Missing/zero-sample values are null. Future labels for the target session are
never included as known information. See [Phase 3 maturity rules](historical_analogs.md).

### Threshold fields

`thresholds[]` contains 60 cells per symbol: two styles × six distances × five
horizons. Each contains `config`, `summary`, `non_overlapping_summary`, and
`distribution_percentiles` from the existing Phase 4 engine. No options quote or
contract is used to construct these underlying thresholds.

`config` fields: `version`, `symbol`, `target_date`, `mode` (`put` or `call`),
`target_spot` and `threshold_price` (USD/share), `threshold_return` (negative
decimal for put style, positive for call), `horizon` and
`analog_selection_horizon` (observed sessions), `opposite_side` (false here).

Both summaries have the same fields:

| Fields | Meaning |
| --- | --- |
| `sample_n`, `as_of_eligible_n` | Selected observations and those mature by target for this horizon. |
| `terminal_valid_n`, `survived_n`, `terminal_breached_n`, `equality_n` | Terminal denominator and mutually exclusive terminal-event counts. |
| `survival_frequency`, `terminal_breach_frequency`, `equality_frequency` | Corresponding historical counts / terminal_valid_n. |
| `survival_wilson_low`, `survival_wilson_high` | Nominal 95% Wilson bounds for observed terminal-survival frequency. |
| `touch_valid_n`, `touch_n`, `no_touch_n` | Relevant excursion denominator, touch and no-touch counts. |
| `touch_frequency`, `no_touch_frequency` | Historical counts / touch_valid_n. |
| `touch_wilson_low`, `touch_wilson_high` | Nominal 95% Wilson bounds for observed touch frequency. |
| `paired_valid_n`, `paired_touch_n`, `recovery_n` | Both terminal/excursion known; touched within that paired sample; touched and then terminally survived. |
| `recovery_frequency_all`, `recovery_frequency_touched` | recovery_n / paired_valid_n and recovery_n / paired_touch_n respectively. |

All counts are nonnegative integers; all frequencies/interval endpoints are
0–1 fractions or null if unavailable. `non_overlapping_summary` uses Phase 4's
greedy disjoint paired-valid future windows, not an independence guarantee.
`distribution_percentiles` maps string keys `0.1,0.25,0.5,0.75,0.9` to decimal
forward-return quantiles. See [Phase 4 exact event definitions](threshold_survival.md).

## Options document (`options-archive-v1`)

This contains observations only; it does not include underlying research,
analog survival, recommendations, expected values or provider/model POP.

| Root field | Meaning |
| --- | --- |
| `schema_version` | `options-archive-v1`. |
| `config_version`, `config_sha256`, `code_revision`, `rebuild` | Same identifiers/rebuild meaning as research, without joining research results. |
| `symbol`, `snapshot_date` | SPY/QQQ and actual New York collection date. |
| `collection_started_at`, `generated_at` | Actual UTC collection start/end; not interchangeable with provider quote timestamps. |
| `provider`, `quote_timing` | `Public`, `last_available_not_guaranteed_close`. |
| `underlying_price`, `underlying_last_timestamp` | Public last traded USD/share and its provider timestamp, if supplied. No historical-close fallback is substituted. |
| `universe` | Validated `min_dte`, `max_dte`, `strike_band` settings. |
| `status` | `complete` (requests returned), `partial` (expiration failure/malformed expiration), or `empty` (no observations). Complete does not mean every quote is valid. |
| `provenance` | Per-field direct-provider/request-context/derived mapping. |
| `warnings[]` | Timing, missing-universe, model-unit and partial-collection limitations. |
| `requested_expirations[]` | Unique in-universe expiration dates. |
| `requests[]` | Successful expiration requests: `expiration`, `started_at`, `received_at`. |
| `expiration_failures[]` | `expiration` and fixed `reason:chain_retrieval_failed`; no raw error text. |
| `invalid_expiration_count` | Number of malformed expiration entries; their untrusted text is not stored. |
| `excluded_expiration_count`, `excluded_strike_count` | Counts intentionally outside configured universe. No liquidity, spread, premium, IV or attractiveness exclusion. |
| `received_contract_count` | All observations received across requested expirations before strike filtering. |
| `valid_contracts[]` | Structurally valid in-universe observations with no quote-quality warnings. |
| `questionable_contracts[]` | Structurally valid in-universe observations with incomplete/stale/unknown quote information. Retained, not treated as executable quotes. |
| `rejected_contracts[]` | Malformed observations retained with rejection reasons. Even a malformed out-of-band observation is retained for audit. |
| `rejection_counts` | Fixed reason-code → integer count. |
| `missing_field_counts` | Numeric/quote-timestamp field → count of null normalized values across all retained observations. |

Each retained contract has:

| Field | Source / units |
| --- | --- |
| `symbol` | Requested underlying, checked against response and OSI contract root. |
| `contract` | Public `instrument.symbol`; standard OSI identifier. Null if malformed; `invalid_contract_identifier_sha256` fingerprints malformed input without exposing arbitrary text. |
| `expiration` | Requested chain date, verified against OSI date; null on invalid date. |
| `type` | Lowercase `call`/`put` from the provider's calls/puts bucket, verified against OSI. |
| `strike` | Public optionDetails.strikePrice, USD/share, positive. |
| `dte` | Derived calendar days: expiration − actual New York snapshot date. |
| `observed_at` | Collector UTC time after that expiration response. |
| `quote_outcome` | Provider `SUCCESS`/`UNKNOWN`, or null for unexpected values. |
| `bid`, `ask`, `last` | Direct Public quoted/traded premium, USD per underlying share; null remains null. |
| `provider_mid` | Direct Public optionDetails.midPrice, stored separately. |
| `mid` | Derived `(bid+ask)/2` only if both finite, nonnegative, and ask≥bid. Missing quotes never become zero; a genuine zero bid remains zero. |
| `volume`, `open_interest` | Optional nonnegative integer contract counts. SDK defines volume for last-trade date; open-interest as-of is unspecified. |
| `iv` | Direct impliedVolatility value. SDK does not certify its scale; no percent/decimal conversion is invented. Treat as provider-native model data until calibrated/documented. |
| `delta`, `gamma`, `theta`, `vega`, `rho` | Optional finite Public model Greeks. No rescaling. SDK describes delta per $1 underlying move, gamma as delta sensitivity, vega/rho per 1% volatility/rate move; theta time basis is not specified. These are not POP or historical frequencies. |
| `bid_timestamp`, `ask_timestamp`, `last_timestamp` | Optional provider-aware timestamps normalized to UTC. Last trade can be older than collection day. |
| `rejection_reasons[]`, `quality_warnings[]` | Fixed codes; no arbitrary provider messages. |
| `missing_fields[]` | Numeric/timestamp names whose normalized value is null. A malformed provided value also has an explicit rejection code, distinguishing it from ordinary absence. |

Validation covers OSI root/date/type/strike consistency, positive strike,
nonnegative quote/count values, crossed bid/ask, duplicate IDs (all duplicates
rejected), expiration/DTE, timestamp validity/future dates, and finite model
values. Missing optional Greeks/IV remain null and do not filter attractiveness.
Missing bid/ask or bid/ask timestamps, stale timestamps, and non-success quote
outcomes mark an observation questionable. Malformed numeric values become
null **with a rejection reason**; the observation itself is retained. Unknown
response fields and raw sensitive error payloads are never serialized.

The pinned SDK inspection confirms all fields above are representable, not that
Public populates all fields for every contract. The existing scanner omits
records missing strike/details; the archive uses the same SDK transport but
inspects individual quote records before normalization, preserving those
malformed records. Full missingness is reported in each actual collection.

After-hours chains may contain delayed or stale last-available observations,
and expired 0-DTE chains may already be unavailable. No close/EOD guarantee,
simultaneous-snapshot guarantee, per-contract completeness guarantee, or
historical backfill is claimed. Endpoint/schema inspection and deterministic
tests do not certify after-hours live field availability.

## Manifest and external readers

`archive-manifest-v1` fields: `latest_research` (entry/null), `latest_options`
(SPY/QQQ → entry/null), `research_sessions`, `option_snapshots` (counts),
`earliest_date`, `latest_date`, `config_versions`, complete `research[]` and
`options[]` inventories, and `issues[]` (`path`, fixed reason).

Each inventory entry has `date`, relative `path`, `config_version`, `sha256` of
exact stored bytes, and `status`. Options entries add `symbol`, `valid_n`,
`questionable_n`, `rejected_n`. Corrupt/misnamed files produce an issue and are
not counted. Backups and manifest contents are not used to infer available
sessions. Rebuild the manifest from actual files after recovery.

Consumers should check `schema_version`, status, warnings, collection timestamps,
nulls and each valid-N denominator before interpreting values. Decimal historical
frequencies are descriptive observations; provider model values are separately
labeled; option quotes are observations; mid/DTE are derived. **There is no
provider/model POP field in these documents.**

The read-only Quant Lab `Daily Archive` tab opens historical research JSON and
shows each symbol's separate options status/counts/warnings. It does not trigger
collection or modify the existing interactive research controls.

## Validation and remaining limits

Tests use deterministic providers and clocks, exercise all existing engines,
and cover runner/schema, immutability/force/backups, no-new-session, holidays/
weekends/DST/early close, universe boundaries, malformed/missing quotes,
duplicates, partial failures, safe errors, manifest recovery and UI history.
Live credentials are never required by tests. Use a real workflow run to verify
repository credentials and actual after-hours field coverage once configured.

Implementation validation: **45 changed-area tests passed**, then the full
regression suite ran once: **204 tests passed in 62.752 seconds**, retaining all
159 tests present after the Public ten-year fix. The workflow YAML parsed and
its schedule/contents permission checks passed. No browser deployment loop or
live provider-dependent test was used for this daily-pipeline implementation.

The archive begins with its first successful live collection. It cannot
reconstruct earlier option observations or prove that currently retrieved
historical OHLC was known unchanged at every historical date. Files record the
research produced at collection time; source hashes and versions aid audit, but
full historical input bars are not copied into every daily summary. Storage
grows daily; a database/object-store migration may eventually be appropriate.
No Phase 5, EV, rankings, recommendations, optimization, ML or trading is added.

References: [Public option-chain schema](https://public.com/api/docs/resources/market-data/get-option-chain),
[Public quotes](https://public.com/api/docs/resources/market-data/get-quotes),
[Public daily bars](https://public.com/api/docs/resources/market-data/get-bars-v2),
[exchange calendar usage](https://pandas-market-calendars.readthedocs.io/en/latest/usage.html),
[GitHub workflow scheduling and permissions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).
