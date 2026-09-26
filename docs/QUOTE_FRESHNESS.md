# Quote freshness and Public latency diagnostic

## Confirmed production evidence

Before these changes, fresh REST retrievals on 2026-09-26 around 03:05:51Z returned:

| Symbol | Last | Normalized lastTimestamp | Retrieval | Observation age |
|---|---:|---|---|---:|
| QQQ | 744.00 | 2026-09-25T07:55:31+00:00 | 2026-09-26T03:05:50.621599+00:00 | 69019.62 seconds |
| SPY | 768.61 | 2026-09-25T07:57:35+00:00 | 2026-09-26T03:05:51.025176+00:00 | 68896.03 seconds |

REST and MCP agreed. The provider observation was old; UTC conversion preserved the instant (QQQ 03:55:31 EDT). The 30-second process cache did not hold an entry for 19 hours. No historical-close fallback was involved in this API path. The defect was accepting an old observation as a research anchor. The first observable stale layer was the Public SDK/shared adapter output, not MCP serialization. Why Public returned that timestamp, account entitlement, and whether a newer upstream observation existed remain unverified.

The original HTTP timestamp spelling was not retained and cannot be recovered retrospectively. The adapter now retains the SDK `last_timestamp` representation, its original field name `lastTimestamp`, normalized UTC instant, and separate retrieval time. Public's [quotes documentation](https://public.com/api/docs/resources/market-data/get-quotes) shows ISO timestamps with `Z`; the SDK defines the field as the time of the last trade. There is no timezone-shift correction: aware timestamps preserve their instant; naive/invalid values are unknown. Explicit Unix seconds/milliseconds are supported; other units are rejected.

## Shared contract

`modules/quote_freshness.py` supplies REST, MCP (through REST), Streamlit and the diagnostic. REST returns `evidence.quote`, `evidence.retrieved_at`, `evidence.cache`, and `evidence.freshness`; `meta.quote_freshness` repeats the quality contract for research consumers. `quote.updated_at` and `freshness.quote_as_of` denote the provider observation, never retrieval. Times are aware UTC ISO-8601.

- `market_state`: `regular_open`, `extended_hours`, `closed`, `unknown`. Uses the existing NYSE calendar dependency, including holidays and early regular closes. The conservative extended-hours policy is 04:00-20:00 ET on exchange trading days. This is a standard-session calendar, not Public's status/entitlement feed. Overnight ATS support is unverified; `closed` means outside this standard/extended policy, not a guarantee that all venues are closed.
- `data_status` (also `freshness`): `fresh`, `stale`, `latest_available`, `unknown`. `delayed` is reserved; the production layer does not infer a 15-minute entitlement from age.
- Active-session default maximum age: 120 seconds (`ALPHAOS_MAX_QUOTE_AGE_SECONDS`, >0 to 900). This allows the existing 30-second cache plus network variation, but is not an execution latency promise. Invalid configuration falls back to 120. More than 60 seconds in the future is unknown.
- Closed sessions: an observation at/after the most recently completed regular close (within the configured age tolerance) is `latest_available`, suitable for dated context only. It stays contextual over weekends/holidays. An observation predating that close is still `stale`; a weekend does not rehabilitate a morning observation. This checks eligibility, not independent proof that Public returned the absolute newest venue print.
- `age_seconds`: evaluation minus observation; `cache_age_seconds`: evaluation minus retrieval. The REST cache remains 30 seconds, keyed by `['quote', symbol]`; reports hit, insertion timestamp and TTL. Stale provider data may be cached for that TTL, but status is recalculated on every read and never upgraded due to recent retrieval. Snapshot IDs exclude changing age/cache-hit metadata. Streamlit retains its separate 30-second cache and recalculates quality on reads; it does not claim a per-call cache-hit flag.
- `usable_for_live_research`: valid positive finite last price and fresh active-session observation.
- `usable_for_contextual_research`: valid last with `fresh` or `latest_available` status.
- `quote_quality`: last validity, bid/ask validity/reason, spread dollars and percentage of midpoint. Default abnormal underlying spread is >0.5 percentage points, configurable with `ALPHAOS_MAX_UNDERLYING_SPREAD_PCT` (>0 to 5). Missing/nonpositive/nonfinite, crossed or unusually wide bid/ask is flagged; original values and legitimate last price are preserved. Threshold is symbol-independent, not a fair-value model.
- `usable_for_execution_analysis`: live-research eligibility plus acceptable underlying bid/ask sanity. This means eligible for further execution-sensitive analysis, NOT an executable quote guarantee. Underlying bid/ask timestamps, venue, depth, fills and real-time entitlement are unverified. Option-leg quality is separate and unchanged.

Quote endpoints keep stale prices in evidence for diagnosis while setting `meta.current_spot` to null when unusable for live anchoring. They never replace it with `research_close`. Contextual market/structure/distribution snapshots may use a latest-available closing observation, explicitly labeled non-live in metadata. New provider-backed scans, exact vertical research and saved API candidate research fail closed with `stale_quote`, `quote_freshness_unknown`, or `market_closed_quote` (503). Manual/explicit scenario inputs still work and are labeled unverified non-live inputs.

Strategy Selector checks before generation and again on saved scan display. Saved Trade Research can still run historical scenarios, but warns that stale/closed candidate spot is not a live entry. Its manual close-seeded default is explicitly described before submission. Option Economics and completed-history workflows remain available. Other Streamlit quote consumers expose dated status and no longer substitute historical close or a different symbol for a missing quote. No quantitative calculation, candidate ordering or authentication code changed.

## Internal diagnostic

Run from the repository root with dependencies installed. No new REST route or MCP tool. Default QQQ/SPY, 30 minutes, 60-second interval; polls at the start and end (31 planned polls per symbol). Direct mode calls the shared Public adapter, bypassing both AlphaOS caches, using already configured `PUBLIC_API_SECRET` and account configuration. It does not change production TTLs. REST mode samples the existing authenticated quote endpoint and records its actual cache flag; other callers can cause cache hits even at 60-second intervals. REST supports SPY/QQQ; direct mode accepts plain equity symbols.

The local `.env.alphaos-api` contains the owner API credential, not a Public secret. It is read only for the named `ALPHAOS_API_TOKEN`; no credentials are command-line arguments or output. Existing environment value takes precedence. Direct mode also supports existing Render secret mounts. Logs and exceptions are suppressed to a fixed safe failure message; output is allowlisted market metadata only.

Five-minute production smoke test (PowerShell, from the repo):

```powershell
python -m scripts.quote_latency --api-url https://alphaos.onrender.com --token-env-file .env.alphaos-api --symbols QQQ SPY --duration-minutes 5 --interval-seconds 60
```

Monday 2026-09-28, start around 10:00 AM America/New_York (14:00 UTC), run until about 10:30 AM:

```powershell
python -m scripts.quote_latency --api-url https://alphaos.onrender.com --token-env-file .env.alphaos-api --symbols QQQ SPY --duration-minutes 30 --interval-seconds 60
```

To test Public directly in an environment with Public credentials configured, omit `--api-url` and `--token-env-file`:

```powershell
python -m scripts.quote_latency --symbols QQQ SPY --duration-minutes 30 --interval-seconds 60
```

Use a Python environment with `requirements-api.txt` installed. No task is scheduled by these commands; start it during the target session. Default outputs are `diagnostics/quote-latency/<UTC-start>/observations.csv` and `summary.json`, ignored by Git. `--output <directory>` changes the location (keep generated results uncommitted). Partial results are saved after every poll and on interruption. Direct runs on Render write ephemeral local files; local REST mode is preferable for retaining artifacts on your computer.

Each record includes symbol, last/bid/ask, SDK timestamp provenance, normalized observation/retrieval/evaluation times, observation lag at retrieval, state/status, research/execution usability, bid/ask quality/spread, provider, cache flag/age, safe success/failure, and empty reference timestamp/price/source columns for optional manual comparison. No other provider is contacted. Raw HTTP timestamp spelling is unavailable through the SDK; the SDK timestamp representation is retained where valid.

Summary per symbol: attempted and successful observations, min/median/mean/max/p95 lag, six latency buckets with counts/percentages, unique timestamps, longest unchanged timestamp run and seconds, unchanged-price pairs, cache hits, provider retrievals, unknown-cache counts and regular-session retrieval counts. Bucket bounds are [0,30), [30,120), [120,600), [600,1200), [1200,3600), [3600,infinity) seconds; negative lag is counted separately. Percentiles use linear interpolation at `(n-1)*p`. Cache hits remain visible in overall descriptive statistics; interpretation uses only successful non-cache regular-session retrievals.

At least 10 such samples spanning 5 minutes are needed for an interpretation. Median <=30s and p95 <=120s describes effectively real-time behavior during that test. p05 >=600s, p95 <=1200s, and p95-p05 <=180s describes a cluster near 15 minutes. A >300s p05/p95 range mixing <=120s with older observations describes unstable freshness. Otherwise a median >120s describes stale observations. These are documented empirical heuristics, not provider guarantees. A 5-minute smoke test normally cannot establish feed behavior. Frozen runs require advancing retrieval times and identical observation timestamps; unchanged price alone is not classified as stale.

## Validation scope

Deterministic tests cover regular/extended/closed/holiday states, Saturday/Sunday, Monday transitions, timezone/epoch conversion, invalid timestamps, stale cache hits and provider misses, distinct observation/cache ages, quality anomalies, shared REST/MCP serialization, snapshot/candidate/vertical gates, explicit research, Strategy Selector and saved Trade Research. Diagnostic tests cover lags, linear p95/buckets, frozen sequences, multiple symbols, cache accounting, interpretation and artifact redaction/serialization. Authentication remains frozen. No automatic merge or Phase 9 UI implementation.
