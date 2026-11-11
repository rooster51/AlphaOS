# Multi-strategy contract research

Open **Options Chain**, select SPY or QQQ and an expiration, then refresh its chain. The **Strategy Comparison Workbench** uses those actual contracts. Choose a strategy, pick its legs and position units, and add it to the comparison. Evaluate the queue to price up to eight scenarios against a common chain observation and underlying quote.

The named strategies are long calls and puts, bull call and bear put debit spreads, bull put and bear call credit spreads, iron condors, iron butterflies, long call and put butterflies, long straddles, and long strangles. Custom signed legs accept up to eight unique contracts with whole signed quantities. Positive quantities buy at ask and negative quantities sell at bid. Each leg is limited to 20 contracts and the configurable contract limit counts absolute quantities across all legs.

The workbench displays net entry cash, entry fees, theoretical maximum profit and loss, expiration breakevens, capital at risk, direction, quote age, and return on maximum risk where finite positive risk and finite nonnegative profit permit it. Expand a scenario to inspect contract identifiers, entry-side observations, liquidity warnings, signed Greek exposures, and a terminal payoff table. Sorting uses the chosen numerical measure. Missing measures sort after available measures. Unlimited values retain their meaning and are labeled explicitly.

## Pricing, eligibility and constraints

The existing Public adapter, explicit dated chain lookup, provider authentication and quote checks supply all pricing evidence. Every selected contract must match SPY or QQQ, the requested date, option side and strike, with unique identifiers and strikes per side. Both provider bid and ask timestamps must be within 30 seconds at evaluation and no later than retrieval. The underlying must satisfy the existing regular-session eligibility check, verified bid/ask and last timestamps, successful provider outcome, acceptable spread, and a 15-second age cap. Stale data can remain visible in the chain, while a scenario using it returns unavailable.

Named strategy geometry is checked independently from pricing. Vertical legs have equal opposing quantities. A butterfly has equal wings and a 1:-2:1 ratio. An iron condor has ordered protective and short strikes, with the short put below the short call. An iron butterfly shares the short strike and has equal wings. Straddles share a strike, while strangles buy a lower put and upper call. Position units scale the complete geometry. A named strategy with incompatible premium direction, no positive theoretical potential profit, or invalid risk is unavailable. A custom position can have mathematically unbounded profit or loss, with an explicit infinity flag and an unavailable finite numeric value.

Hypothetical constraints cover maximum debit, maximum loss, minimum credit, maximum absolute contracts, maximum per-leg bid/ask spread in dollars per share, and calendar DTE range measured in New York. Debit and loss include entry fees. The minimum credit applies to credit structures after entry fees. Entry fees are charged exactly once per absolute contract. Exit commissions and exercise/assignment charges are excluded and must be considered separately. The multiplier is fixed explicitly at 100 for standard contracts.

A result distinguishes eligibility for analysis, liquidity quality and constraint breaches. Displayed entry-side size below the quantity is a warning. Missing sizes, zero or missing volume/open interest, and missing Greeks remain explicit. Signed Greek exposure is available only when every selected leg supplies that Greek, using quantity × 100; it is an observation rather than a future volatility or time model. Known event risk evidence is unavailable in this milestone.

Capital at risk describes terminal payoff under the stated assumptions. Brokerage margin, exercise timing, early assignment, legging and fills require separate treatment. Custom signed positions receive a complex-margin label. A valid payoff does not establish a trading edge.

## API and engine reuse

`POST /v1/options/{symbol}/chain/{expiration}` evaluates a bounded batch with the existing bearer authentication. It accepts `scenarios` containing a strategy and signed contract selections, `limits`, and `entry_fee_per_contract`. Prices, strikes, timestamps, expirations and multiplier are resolved from the provider chain. The response echoes the normalized request, retains input order and returns an independent status per scenario. The existing GET methods and legacy quick scenarios remain available.

The website uses the existing `/api/options` bridge with a session, same-origin POST protection, a 20 KB streamed input limit and an eight-second upstream deadline. Backend schemas reject additional fields, nonfinite inputs, ambiguous quantities and excessive batch sizes. The bridge checks the echoed request, result schema and selected contract identities before rendering. Requests occur on user actions. Changing symbol, date, chain or constraints clears comparison results. A displayed comparison is a dated evaluation and is checked again only through an explicit action.

All economics come from `modules/options_payoff.py` and `modules/premium_engine.py`. Geometry reuses the shared structure classifier. Provider, cache and underlying infrastructure remain shared. Chain retrieval uses a bounded 30-second cache with eligibility recomputed when consumed; option fetches and per-symbol underlying quote locks retain independent SPY/QQQ handling. The SDK's existing per-request 30-second transport timeout can outlast the website deadline. Sanitized traces cover option research POST requests.

## Deferred multi-expiration valuation

Calendars, diagonals, double calendars and LEAPS combinations spanning expiration dates need a separate PR. An extension should accept individually dated contract bundles and a valuation horizon, with an explicitly supplied and validated valuation model for remaining legs. Its result must distinguish horizon liquidation value, path/assignment assumptions, model parameters and scenario bounds. It must not feed legs with different dates into the shared expiration payoff calculator or claim a closed-form maximum from that calculator. Same-expiration long-dated standard contracts already use the normal dated lookup when the provider supplies them and DTE limits permit.

Comparisons in this release share one symbol and expiration. Event calendars, volatility surfaces, calibrated probability/EV, live execution, brokerage buying-power verification, and paper-trade records are outside the response contract.

## Staging acceptance checklist

1. Confirm the draft branch's CI and preview build. Authenticate the preview and staging backend using the existing staging credentials.
2. For SPY and QQQ separately, record quote/discovery/chain HTTP statuses, latency, requested expiration, call/put counts, provider timestamp ages, missing timestamps, and liquidity/Greek coverage. Use a provider-confirmed expiration. Record SPY discovery failure separately from any explicit dated retrieval result.
3. During regular market hours, evaluate a long, debit vertical, credit vertical, iron condor, iron butterfly, long butterfly, straddle and strangle using fresh contracts. Record the normalized request and sanitized response with evaluation time. Check selected identifiers, buy asks, sell bids, fees, multiplier, roots and risk against deterministic payoff landmarks.
4. Compare multiple qualified structures using a shared observation time. Change fees and risk constraints, verify previous results clear, and confirm failed limits produce NO TRADE with the calculated risk still visible.
5. Exercise stale/missing timestamps, missing Greeks, crossed markets, duplicate or mismatched contracts, bad wings, expired dates and provider/authentication failures. Confirm absent evidence stays unavailable.
6. Check custom short calls for explicitly unbounded loss and null return on risk. Apply a finite loss cap and verify rejection. Confirm multi-expiration inputs fail schema or contract matching.
7. Check desktop/mobile contract selection, sorting, payoff tables, manual refresh, symbol independence, session/CSRF denial, and the absence of automatic provider fetching during navigation.

Deterministic fixtures establish mathematical and interface behavior. Actual provider outcomes and hosted authentication checks are recorded in the PR; they establish only the scope actually exercised.

## Observed staging data on November 5, 2026

Authenticated staging discovery succeeded for both symbols, including November 6, 2026. Initial requests timed out while the retained staging service warmed up. A later health request completed in 660 ms. The snapshot below was evaluated at approximately 11:06:57 a.m. New York time. Latency measures the complete staging HTTP request, including transport and backend processing.

| Symbol | Expiration | Calls / puts | Fresh contracts / total | Chain latency | Underlying latency | Supported families evaluated |
| --- | --- | --- | --- | --- | --- | --- |
| SPY | 2026-11-06 | 171 / 171 | 286 / 342 | 2,656 ms | 860 ms | 12 / 12 available |
| QQQ | 2026-11-06 | 186 / 186 | 347 / 372 | 2,906 ms | 875 ms | 12 / 12 available |

Both underlying quotes passed the 15-second eligibility check. All selected contracts passed the 30-second option gate. An earlier full-chain observation at 11:04:57 a.m. had bid/ask timestamps and delta for every returned contract (342 SPY and 372 QQQ), while some quotes exceeded the freshness cap. Available status describes the stated evidence and configured research limits.

These observations exercise the new local research code against actual authenticated staging market responses. Acceptance of the new hosted POST route and authenticated comparison workbench remains pending staging deployment. The retained staging service supplied the contract data. The evidence file contains identifiers, observed prices, provider timestamps, liquidity fields, fees, and calculated economics for each of the 24 evaluated scenarios.

[Sanitized staging research observations](evidence/multi-strategy-staging-2026-11-05.json)
