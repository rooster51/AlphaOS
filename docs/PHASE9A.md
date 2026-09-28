# Phase 9A: unified trade research and ChatGPT orchestration

## Architecture and scope

Option C: a thin `UnifiedResearch` orchestration service over the existing `ResearchService`, with a shared `build_unified_trade` presentation model used by REST/MCP and Streamlit. No new analog, structure, threshold, payoff, ranking or execution engine. Authentication, CSP, consent and the deployed quote-quality contract remain unchanged. The ten existing MCP tools and all existing REST routes remain available.

Four additive read-only MCP tools:

- `run_symbol_research`: mode `run` validates data, gets a shared research/structure snapshot, scans, then returns unified research for each returned candidate. `overview` stops at context/structure. `find` returns the unranked scan and candidate IDs for follow-ups. `refresh=true` bypasses normal quote/chain caches where those observations are requested.
- `unified_candidate_research`: uses a recent saved candidate ID; no silent refresh/repricing. Existing 120-second ID lifetime and observation freshness checks apply.
- `unified_vertical_research`: explicit symbol, expiration, put/call, short and long strikes; natural option credit from the existing exact-vertical service. Missing expiration is not guessed.
- `unified_explicit_trade_research`: a validated existing TradeRequest with explicit spot, premium and friction, for non-live scenarios including closed markets.

REST equivalents are GET `/v1/research/{symbol}/run`, GET `/v1/research/candidates/{candidate_id}`, GET `/v1/research/{symbol}/vertical`, and POST `/v1/research/trade`. These use the original authenticated router and sanitization boundary. The MCP adapter calls these routes in process using the original transport; no authentication implementation changed.

OpenAI recommends goal-oriented descriptions, bounded schemas and server instructions for cross-tool sequencing: [MCP server guidance](https://developers.openai.com/plugins/build/mcp-server), [metadata guidance](https://developers.openai.com/plugins/guides/optimize-metadata). This implementation follows that guidance; actual natural-language routing must still be tested in ChatGPT, not inferred from SDK tests.

## Defaults and data gates

A bare `Run QQQ` uses 3 observed sessions, 1-7 calendar DTE, both PCS/CCS, $1 wings, $0.05 minimum credit/share, and at most the first four entries in existing generator order. The cap is configurable from 1 to 10. These are disclosed research scope defaults, NOT best-trade selection. Existing scan scope limits (including maximum five expirations) apply; return explicit partial/unavailable state instead of changing filters silently.

Quote validation happens before snapshot or scan. A stale/unknown quote stops live research and returns its state/reason. A latest-available closing observation can return contextual snapshot/structure but no new live candidate scan. A valid last with suspect underlying bid/ask can support live last-price research while execution-analysis usability remains false. Nothing here implies a guaranteed fill or real-time market-data entitlement.

The shared quote, history and snapshot are reused through the scan even if the quote-cache TTL passes. Freshness is re-evaluated during research and before returning; a quote that expires during the workflow removes live candidates and stops live presentation. Each returned candidate includes the same underlying timestamp and snapshot ID. Option chains can have distinct observation/retrieval times, retained in provenance; this is not an atomic exchange snapshot.

A failed provider stage returns sanitized error codes and a `partial` or `data_unavailable` result, preserving successful context where possible. Consumers must inspect `status`, `stop_reason`, `errors`, `stages` and `usable_for_live_research`, rather than assuming HTTP 200 means complete/live research.

## Versioned unified contract

`alphaos-symbol-research-v1` contains the data state, research context/structure, scan, ordered qualifying trade objects, stage/status/error information, defaults and presentation instructions.

`alphaos-unified-trade-v1` has five sections:

1. `trade_snapshot`: identity, legs, expiration, single-spread width, credit/share, max profit/loss, return on risk, breakeven and signed distances from the explicit scenario spot. `live_trade_state` preserves quote timestamp, retrieval, market/data status, quality and usability. `research_state` independently preserves completed session, close and observed-session horizon. `scenario_spot` is the computational input; an unverified explicit input is never silently called live current_spot.
2. `market_structure`: existing identified zones and evidence, nearest relevant support for PCS/resistance for CCS, signed strike-minus-level distance, and a price-ordered location table. Price order is display geometry, not candidate ranking. Relationships are descriptive, never protection/safety claims.
3. `historical_analog_behavior`: named short strike, breakeven and long strike, each with its actual price, distance, selected horizon, existing threshold summary, non-overlapping diagnostic, Wilson intervals and existing excursion summary. Reuses the same primary analog population and existing spot bridge. Terminal, touch and paired recovery denominators remain distinct. Recovery is terminal survival after a touch, not a reconstructed intraday path. Only existing supported intervals/metrics are exposed.
4. `historical_scenario_payoff`: existing gross/net summaries, median, EV, tails, sample size, friction and non-overlapping summary. Full-profit/max-loss/partial counts classify existing gross payoff observations at their existing endpoints (absolute dollar tolerance 1e-8), after saved entry fees and before extra modeled friction. Partial outcomes need not be profitable. Infinite profit factor is JSON null with an explicit `profit_factor_unbounded` flag. The descriptive Scenario EV caveat remains prominent.
5. `advanced_research`: engine/config/provider/research metadata always available. `include_advanced=true` adds full analogs, distributions, threshold observations, excursions, payoff rows and robustness. Raw quantitative calculations remain unchanged.

Distances are signed dollars and decimal fractions; frequencies are decimal fractions, not future probabilities. Credit is dollars/share, payoff dollars/structure. Observed-session horizon is independent of calendar DTE; scenario payoff is not automatically expiration-matched profitability evidence. The five-section Streamlit view layers over the existing submitted Trade Research result; full legacy evidence, exports and chain comparison remain in Advanced Research. Existing saved/manual workflows remain explicitly non-live.

## Natural-language acceptance set

1. `Run QQQ` -> one workflow using disclosed defaults. Show data state, concise market context/structure, qualifying candidates and trade evidence. Never label generator order best/top/recommended.
2. `What's QQQ doing?` -> overview without a candidate scan.
3. `Find QQQ trades` -> data gate, context, structure and unranked candidate discovery.
4. `Research the [short]/[long] PCS expiring [actual expiration] from that scan` -> exact returned candidate ID, or explicit vertical if no ID is available. Repeat for a CCS. Verify all three trade levels are labeled, and research/live state differ.
5. `Compare those two using the same scenario spot and observed-session horizon` -> existing `compare_trades`, with shared explicit symbol, spot, horizon, method and friction. Ask for missing context. Do not silently combine stale/different snapshots or select a winner. This reuses the existing comparison facility; Phase 9B side-by-side product functionality is not introduced here.
6. `Refresh QQQ` -> overview with fresh quote request, preserving completed research state.
7. `How is my spread looking?` -> ask for identity/expiration and any missing explicit entry/scenario inputs. No held-position inference, P&L monitoring or position management.

If ChatGPT caches the tool list, refresh the app's tools through its normal configuration flow. No credentials belong in chat or tool arguments. No natural-language routing success is claimed until the user runs this acceptance set in ChatGPT.

## Validation and exclusions

Deterministic tests cover QQQ fresh/stale/closed/wide-spread workflows, pre-scan data gates, shared snapshots, quote expiry during a workflow, exact PCS/CCS arithmetic, engine parity for each level and scenario payoff, metadata, explicit inputs, REST/MCP serialization, tool schema and granular compatibility, and the Streamlit view. Full pre-existing regressions must pass before commit/deployment.

No automatic merge. No execution, new broker/position integration, scheduling, notifications, ranking, winner selection or multi-leg unified research. Phase 9B comparison and Phase 9C multi-leg work remain separate future tasks.
