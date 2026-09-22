# Public daily-history retrieval fix

## Root cause, reproduced September 22, 2026

The deployed app sent `GET /userapigateway/historicdata/EQUITY/SPY/TEN_YEARS/ONE_DAY`.
Public returned HTTP 400, rejecting the period/aggregation combination. The
pinned Public SDK 0.1.17 raises `public_api_sdk.exceptions.ValidationError` for
HTTP 400. This is **not** Pydantic schema validation or AlphaOS market-state OHLC
validation. No OHLC rows were returned by the failing request, so duplicate
dates, adjusted prices and floating-point comparisons could not cause it.

The original reported wording came from Portfolio Research. The deployed
Market State Research path reproduced the same underlying error, with its own
generic wording. Both use `get_public_research_bars`.

The SDK enum accepting TEN_YEARS does not mean every aggregation is supported.
Live read-only compatibility probes found:

| SPY request | Result |
| --- | --- |
| TEN_YEARS / ONE_DAY | HTTP 400, no history |
| TEN_YEARS / provider default | 120 monthly bars, 2016-10-01 to 2026-09-01 |
| ALL / ONE_DAY | HTTP 400, no history |
| ALL / provider default | 405 monthly bars, 1993-01-01 to 2026-09-01 |
| SINCE_PURCHASE / ONE_DAY, purchaseDate=2016-09-22 | 2,513 daily bars, 2016-09-22 to 2026-09-22 |

Default long histories contain month-boundary timestamps, including weekends;
they are not daily trading sessions and were never substituted into research.
The successful raw SPY dated request had zero invalid/duplicate normalized
dates, weekend rows, missing/nonfinite/nonpositive OHLC, or OHLC bounds failures.
No close-to-close moves exceeded 25%; this coarse check is not proof of
corporate-action adjustment. Temporary compatibility-probe UI was removed.

## Fix and data path

`market_state_workspace` → `load_market_state` → cached
`get_public_research_bars` → `public_history.fetch_research_bars` → authenticated
Public SDK transport → raw public-field diagnostics → unchanged SDK
`BarsResponse` validation → numeric OHLC normalization → strict OHLC and
coverage checks → existing features/outcomes. Portfolio Research shares this
adapter. No analog, threshold, payoff or Pulse methodology changes.

| AlphaOS selection | Public period | Aggregation | Parameters |
| --- | --- | --- | --- |
| FIVE_YEARS | FIVE_YEARS | ONE_DAY | none |
| TEN_YEARS | SINCE_PURCHASE | ONE_DAY | purchaseDate = New York request date minus 10 calendar years |
| YEAR / MONTH | unchanged | ONE_DAY | none |
| MAX / ALL | rejected in research | — | native daily support not verified |

The [Public bars documentation](https://public.com/api/docs/resources/market-data/get-bars-v2)
documents `SINCE_PURCHASE` and `purchaseDate`; the pinned SDK supports the
aggregation override and purchase-date query. The date is used solely as the
history start: no order, purchase or brokerage-holding import occurs. The
endpoint returns through the present; no undocumented end-date parameter,
pagination token or chunking scheme is invented. Leap-day subtraction uses
calendar arithmetic. No request falls back to a shorter period or monthly bars.

Daily MAX/ALL is not enabled: Public rejected ALL/ONE_DAY, while default ALL
returned monthly data. An earliest-available daily query has not been certified.

## Validation and diagnostics

The existing positive/finite/complete OHLC, exact high/low bounds, unique UTC
session dates, chronological order and weekend checks remain strict. No
floating-point tolerance was added because precision was not the failure.
Bad rows are not dropped or repaired. No forward fill or resampling is used.

For five-/ten-year equities, endpoints must cover the requested window within
seven calendar days. This allowance accommodates ordinary exchange closures;
it cannot accept a five-year response for a ten-year request. Interior gaps
over seven calendar days or median spacing over three days fail. These are
gross truncation/density checks, **not** an authoritative exchange calendar.
Holidays and isolated missing weekdays still require the existing gap audit.
Synthetic leading-fill descriptors and mismatched response symbols/periods fail.

Diagnostics report requested/provider periods, start/end, aggregation, retrieval
time, raw rows and date extrema, quality counts, completed rows, and failure
stage. Pydantic errors expose only allowlisted field locations and error codes;
provider error terms use a fixed vocabulary. Raw error text, inputs, context,
headers, account IDs, tokens and secrets are never serialized. Both research
UIs show a collapsible diagnostic on failure; successful Market State metadata
includes the same audit. Error messages identify dates/counts for bad OHLC.

## Price convention and limitations

All four fields come together from Public `regularMarket.bars`:
`open`, `high`, `low`, `close`. AlphaOS does not substitute `value` or an adjusted
close, and does not invent adjustment factors. Public's documented schema does
not establish whether these OHLC fields are split-adjusted, dividend-adjusted
or raw. **Adjustment remains unverified**, not total-return data. Internal
OHLC consistency does not establish an adjustment convention or point-in-time
revision guarantees.

Today is conservatively excluded from research even after market close. Raw
retrieval counts can therefore exceed feature counts. Reads remain cached up
to 300 seconds. Session completeness and corporate actions remain caveats.

## Regression coverage

Tests exercise the actual HTTP-400 period/aggregation issue, explicit start-date
mapping, all four symbol/period combinations, long valid history and features,
normalized duplicates, malformed/null/nonfinite/nonpositive OHLC, truncation,
stale/coarse/sparse history, unsupported periods, no fallback, SDK schema
validation/redaction, no adjusted-close substitution, leading fills, strict
bounds, and both UI diagnostic paths. Prior Phase 1–4 tests are retained.
