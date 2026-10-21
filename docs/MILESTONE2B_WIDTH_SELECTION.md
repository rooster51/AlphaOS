# Milestone 2B: observed-strike widths (Issue #58)

## Audit and scope

Baseline: `03e6f81` on main, including merged PR #57. The market REST model,
MCP tool, market runner and opportunity session all defaulted to five points.
Debit discovery selected one observed delta nearest 0.50, then the strike nearest
the width target. Premium discovery also used nearest-target protection strikes,
paired condor shorts by index, and sampled at most 40 short anchors. Consequently,
capital eligibility could be correct for the structures constructed while an
affordable structure was never constructed. The website exposed no width input.

Opportunity discovery now enumerates observed geometry for the **same routed
families**. Legacy Strategy Selector/income/premium tools keep their own defaults
and behavior. This change adds no strategy, symbol, provider request, collection
coverage, classification threshold, volatility model, probability or EV estimate.
Unknown market evidence and unsupported routes retain their existing meaning.

## Shared website, REST and MCP contract

`POST /v1/research/market` and MCP `run_market`:

* Omit `width`, or send `null`: Auto Width, now the default. Enumerate multiple
  widths from actual unique strikes in the selected verified archive expiration.
* A numeric `width` greater than zero and at most 100: Manual Width. Require exact
  observed wing spacing (floating comparison tolerance 1e-8). Never round to a
  different listed strike. Booleans, strings and nonfinite widths are invalid.
* The numeric API/MCP argument remains supported; clients that explicitly sent
  five still request five. **Compatibility change:** a numeric target formerly
  allowed nearest-strike substitution and one debit anchor; it is now exact and
  may return multiple anchors, or no structure. Omitted width now means auto.
* Capital remains a dollar ceiling on one standard package's expiration maximum
  loss, including the existing constructor fee assumption. It is not broker
  buying power, margin, account equity or a recommendation.
* Exact requested expiration is unchanged across interfaces. No cross-expiration
  legs or substitute expiration are permitted. Width does not expand collection.

Examples (both supported symbols follow the same semantics):

```json
{"symbol":"SPY","available_capital":150,"expiration":"2030-01-03"}
{"symbol":"QQQ","available_capital":150,"expiration":"2030-01-03","width":1}
```

Dates above are illustrative requests, not claims of available market data.
The website defaults to Auto Width, shows a Manual Width input when selected,
and rejects a backend response that changes the requested width. REST's website
bridge performs the same check. Session diagnostics echo the effective mode.

## Construction coverage

| Existing family | Auto geometry | Manual geometry | Pricing/evidence retained |
| --- | --- | --- | --- |
| Call/put debit vertical | All bounded ordered observed pairs in the directional geometry | Exact strike difference | Both observed deltas of correct sign; recomputed bid/ask midpoint debit rounded to cents; existing zero fee assumption |
| Put/call credit vertical | Observed OTM short anchors and outward wings | Exact strike difference | Natural bid/ask, positive short bid, existing 5% short-distance gate, $0.65 per contract |
| Iron condor | Independent observed put and call pairs; unequal wings allowed | Both wings equal the requested width | Same premium gates and fees; shared payoff uses the larger actual risk wing |
| Iron butterfly | Existing nearest common ATM body; multiple symmetric observed wings | Both wings equal requested width | Same premium gates and fees |
| Put/call broken-wing butterfly | Observed inner/outer wings with outer strictly wider | Inner equals requested width; outer equals twice requested width | Existing OTM body/distance, credit/fee and natural quote gates; 1/-2/1 quantities |
| Symmetric long butterfly | **Explicit research only**, unchanged | Explicit legs/cashflow endpoint, unchanged | Shared explicit-scenario economics, not verified discovery |
| Long calls/puts | Existing discovery, unaffected by width | Width does not alter outrights | Existing quote and distance behavior |
| Unsupported routed families | Unavailable, unchanged | Unavailable, unchanged | No replacement strategy advertised |

Shared `research_position`/`options_payoff` compute full maximum loss/profit,
breakevens and capital at risk for every generated package **before** the capital
test. No capital-based width pruning, narrowest-width choice, score or winner is
introduced. Multiple eligible widths remain in descriptive comparison.
Invalid economics are excluded; cached constructor risk and probability values
are not trusted. Capital failures retain full research economics and the required
capital. Construction failures, missing observations, duplicate strikes,
archive rejections, routing failures and capital failures have separate stages.

## Deterministic search bounds and limitations

`modules/width_discovery.py` defines configurable constructor policy constants
and function arguments: at most 80 contracts per side (nearest observed strikes
to spot, deterministic ties), 100-point wings, and at most 1,024 geometry/quote attempts per family. Every
quote-constructed package in that enumeration reaches shared payoff research
before capital eligibility; there is no separate constructor output shortlist. Bounds
are independent of the user's capital. Output follows deterministic family and
strike order; it is not ranked or guaranteed exhaustive. No UI shortlist runs
before the economics/capital check. Issue #60 adds a shared 1,024-attempt request
budget, allocated fairly across routed families; the per-family 1,024 limit is
a ceiling rather than a multiplier. Applied quotas and truncation are explicit.
See [the performance audit](ISSUE60_RESEARCH_PERFORMANCE.md).

Diagnostics include the applied bounds and `search_truncated`; aggregate
`width_selection.search_complete` describes completion **within the declared
search domain**, not every listed or theoretical structure. When truncated, the
website displays a partial-results warning. An empty incomplete search is
`bounded_search_incomplete`, never a claim that all possible structures exceed
capital. Manual structures outside these bounds require explicit-leg research;
for example a 60-point BWB inner wing would require an outer wing beyond the
100-point discovery bound. No different wing is substituted.

Archive checksums, identity, strict current-mode freshness, historical labeling,
rejected-contract exclusions and quote observations are unchanged. Questionable
archive observations retain their warnings; missing liquidity/timestamps remain
unavailable. Neither a valid bid/ask nor affordability establishes executable
liquidity. Historical economics still fail closed when entry-aligned evidence,
execution validation or robustness is unavailable. A width-eligible result is
not automatically eligible for consideration. Collection coverage remains the
bounded subset described in the expiration-coverage documentation.

## Fixture before/after measurements

Local provider-free opportunity-session measurements, ten iterations per symbol
on 2026-10-21. Synthetic 11-strike-per-side quotes from
`tests/test_width_discovery.py`, mixed irregular spacing, spot 100, bullish
direction, $150 maximum loss. Baseline executes the main revision's original
opportunity-session code with default five; after executes auto with identical
inputs. These are **fixture observations, not production quotes or latency**.

| Symbol | Baseline / auto median ms | Generated before / after | Capital eligible before / after |
| --- | --- | --- | --- |
| SPY | 0.89 / 20.49 | 1 / 55 | 0 / 23 |
| QQQ | 0.81 / 20.75 | 1 / 55 | 0 / 23 |

The improvement is coverage of affordable observed structures, not faster
computation. More payoff calculations intentionally cost more CPU; recorded
local maxima were 3.54/23.30 ms for SPY and 1.39/80.51 ms for QQQ. Archive retrieval,
provider history, transport and website rendering are outside this microbenchmark.
These measurements cannot establish production 12-second reliability.

Final local validation on 2026-10-21: complete Python suite **1,095 passed plus
64 subtests**, 266.97 seconds; four existing Supabase SDK deprecation warnings.
Website suite **90 passed**, Chromium browser suite **27 passed**, TypeScript
typecheck and Next.js production build passed. No production calls are implied
by these checks.

Regression coverage includes all eight affected families, SPY/QQQ, 0DTE, next-day,
monthly and long-dated expirations, $150 capital, multiple eligible widths,
irregular spacing, exact/unavailable manual wings, immutable observed quotes,
missing deltas/quotes, duplicate strikes, wide quotes, rejected stale quotes,
stale archives, checksums, deterministic search bounds, REST/OAuth MCP parity and
browser Auto/Manual behavior. Existing cold/warm concurrency tests remain part
of the complete suite. Website fixtures were regenerated through the real REST
boundary using fixture storage, not hand-priced replacements.

**Milestone 1 cold-start production acceptance remains open.** No production
benchmark, deployment, subscription, secret, infrastructure or timeout change is
part of this PR.
