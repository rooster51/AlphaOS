# Strategy Selector → Quant Lab workflow

## Trader workflow

1. In Strategy Selector, choose **Public · connected quotes**, SPY or QQQ, expiration/risk filters, and **Observed-session research horizon** (1/2/3/5/10). The historical forward window is independent of calendar DTE.
2. Run the scan. Above the opportunity table, compare the latest completed research close with the current Public quote, its original timestamp, spot change, and completed-history ATR. Inspect up to three support and three resistance zones with bounds, center, current-spot/ATR distances, unique structural observations, age, and sources.
3. Compare the existing opportunity columns and added descriptive context for plain vertical credit spreads. PCS use nearest support and survival strictly ABOVE the short strike; CCS use nearest resistance and survival strictly BELOW. No historical score or automatic winner is introduced; existing ranking choices remain unchanged.
4. Click one opportunity. The full candidate, saved credit/fees/legs/quotes and research context are retained. **Research selected trade in Quant Lab →** opens Trade Research first and fills the selected candidate and research horizon. Run the integrated research without retyping the trade.
5. Use **Refresh market research** deliberately to retrieve a new completed-history snapshot. Original candidate research/quote anchors remain visible alongside refreshed research date, close and read timestamp. This action does not refresh the option quote, replace the saved premium, or rewrite its timestamps. To obtain a new quoted candidate, rescan Strategy Selector.

Manual vertical entry, saved manual trades, demo mode, non-SPY/QQQ scans, all existing strategy generators and ranking methods, Options stress lab, and the separate Option Economics page remain available. Deep structural Trade Research supports plain vertical credit spreads; other structures continue through their existing stress/economics views.

## Data/API behavior

`selector_research.build_scan_research` invokes the existing `load_market_state(symbol, FIVE_YEARS)` once per supported Public scan, before candidate construction. This delegates all provider access, validation, completion timing, provenance and existing 300-second provider caching to existing functions. No new raw Public API client is introduced. Current-quote, expiration and chain retrieval retain their prior behavior (one chain request per selected expiration, subject to existing caches).

One completed-state feature/outcome dataset, one structure map and one frozen-default tolerance analog population are shared across every candidate. Repeated short-strike/type combinations reuse the same threshold result, including across expirations, because the explicit observed-session horizon is shared and is not inferred from expiration. Different strikes reuse the population. Merely selecting a row, opening Quant Lab or changing tabs makes no history call.

Quant Lab reuses a valid saved prepared dataset and primary sample. Other horizons and fixed robustness configurations are computed only as needed; the default tolerance robustness row reuses the primary default population. Explicit refresh loads once and prepares a reusable dataset/population. No history is fetched per candidate or robustness definition.

Provider-history failure leaves quote discovery/payoffs functional, shows an explicit warning and makes research fields unavailable. No synthetic history or previous scan context is silently substituted. Existing research and archive modules retain their validation and immutable-write behavior.

## Interpretation and boundaries

Nearest support/resistance means nearest to **current underlying spot**, from completed historical zones. Candidate location compares its short strike to zone low/high: equality at either bound is INSIDE (representation tolerance = 1e-12 × price scale). ABOVE/INSIDE/BELOW does not imply good, bad, safe, unsafe or attractive. Distance from the nearest level is signed strike minus zone center in dollars. A missing zone stays unavailable.

Threshold calculations preserve the Phase 4 decimal-return equality convention: touch/breach includes equality; terminal survival and finish-beyond are strict; terminal equality is separate. Research N counts valid matured terminal observations. Touch N is shown separately because missing excursions can produce a different denominator. Nonvertical strategies leave these fields blank. Historical frequencies are not forecast probabilities, and neither structural location nor scenario EV establishes future expectancy.

## Snapshot integrity

Each research snapshot has a content hash, version, OHLC/provider metadata, research date/close, original quote timestamp/current spot, scan retrieval time, explicit horizon, analog config, selected zones and threshold statistics. The selected candidate has a normalized payoff-input fingerprint; full leg quote timestamps and source fields are preserved. `quant_selected_option` remains the handoff key. `quant_selected_research` holds the shared dataset/sample once, rather than embedding historical rows in every candidate.

Quant Lab validates the selected fingerprint, snapshot hash, symbol, spot, horizon, analog config and research anchors before reuse. Mismatched context requires explicit refresh and is never silently transplanted onto a changed trade. A matching saved snapshot is still a dated historical observation, not a freshness guarantee. Newly selected candidates reset the default input mode; manual entry can still be chosen explicitly. Changing source data invalidates submitted results. Refresh displays both old and new anchors even when the dates coincide.

No look-ahead: selection uses completed state; outcome maturity is rechecked using the full chronological session sequence. Current quote/spot only anchors scenario prices and strike distances. Provider adjustment status and exchange-calendar completeness remain qualified as in prior phases. Nothing here fabricates historical option prices or places orders.
