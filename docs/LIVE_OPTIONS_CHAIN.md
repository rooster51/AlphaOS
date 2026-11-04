# SPY and QQQ options-chain research

Open **Options Chain** from the research navigation. Choose SPY or QQQ, then discover available expirations or enter a known date. Select **Refresh chain** to request the selected date and underlying context. All requests require a website session and the existing server-to-server bearer token. The page makes requests only after a user action.

## Dated lookup and quote integrity

The existing expiration and chain endpoints continue to support discovery-based callers. The website requests the same chain endpoint with `explicit=true` for SPY and QQQ. This path requires a non-expired date in New York and matching provider underlying and contract identity. At least one returned standard contract identifier must agree with the underlying, date, side, and strike. Other rows can be shown with their validation status. Empty or unverifiable responses fail closed. The API does not retry using an invented date or silently replace a failed discovery response. Public documents using a listed expiration and can still reject a dated request independently of AlphaOS discovery.

Each row identifies the Public source, bid and ask provider timestamps, and retrieval time. The **30-second** research threshold applies to both provider observations, measured at request time. Future, missing, crossed, invalid, and ambiguous observations are ineligible. Missing Greeks and sizes display as unavailable. The legacy 15-minute chain timing summary remains informational for legacy API consumers. The underlying quote retains the existing 15-second live research rule and can still appear as labeled context. The thresholds are application policy. Provider timing and market data entitlements must be measured in staging.

## Strategy scenarios

Select a buy contract and optionally a sell contract on the same side and expiration. The server evaluates the selected contracts against the same chain validation rules and requires a fresh underlying quote. A long pays the displayed ask and a short receives the displayed bid. An invalid or nonpositive fill price, or a vertical premium that conflicts with the shape or exceeds its width, returns an unavailable scenario. Expiration economics use the existing payoff engine and a standard 100-share multiplier. Fees, assignment, displayed size, latency, and multileg fill uncertainty affect real execution. This interface is read-only and shows a theoretical one-lot scenario.

The selected-leg list is the extension point for other structures. Calendars and diagonals require separately validated dated chains and a time-aware valuation model. Additional strategy shape and contract terms must be validated before enabling them.

## Reliability and staging checks

The website bridge aborts after eight seconds including the response body. The Public SDK retains its per-request 30-second transport timeout. A bridge timeout can occur before an in-progress SDK call ends. No provider retry is initiated by the bridge. Chain and discovery fetches run outside the cache lock. An explicit refresh bypasses the chain cache. The bounded cache stores chain observations for up to 30 seconds and recomputes eligibility when read. The existing request trace records elapsed time and provider stages without credentials, contracts, or raw responses.

For staging acceptance, record HTTP status and elapsed time for both symbols' quote, expirations, and dated chain routes. Use an independently confirmed SPY expiration when discovery fails. Record call and put counts, contract identity coverage, bid and ask age, missing timestamps, and availability of Greeks, volume, open interest and sizes. Check one valid and one unavailable scenario with the same endpoint. Use the staging service's authorized credentials and keep credentials and raw account information out of the report.

[Public option-chain fields and expiration requirements](https://public.com/api/docs/resources/market-data/get-option-chain)
