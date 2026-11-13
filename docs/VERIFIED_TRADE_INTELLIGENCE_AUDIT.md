# Verified trade intelligence — Phase 2 audit

**Base:** `main` at `d932427` (PR #103, “Restore unified SPY/QQQ trading workspace”).
**Branch:** `feat/verified-trade-intelligence`.
**Scope:** SPY and QQQ, authenticated private research, read-only.

## What already existed and was reused

| Capability | Existing implementation | Reuse in Phase 2 |
| --- | --- | --- |
| Completed daily history and quote bundle | `ResearchService.snapshot`, `MarketProvider.history/quote`, `market_state.validate_ohlc` | Previous regular-session OHLC, ATR(14), and the existing market snapshot |
| Provider-normalised intraday candles | `PublicMarketDataProvider`, `CandleService`, `build_snapshot` | Confirmed 5-minute regular-session bars under `PRIVATE_RESEARCH`, with the existing freshness/completeness contract |
| Session clock | `market_session_gate.regular_session_bounds` | Open/closed/pre-open state and the expected 9:30 ET bar grid |
| Existing support/resistance | `price_structure.price_structure` and `nearest_levels` | Backend S/R zones included as reference levels; no duplicate clustering model |
| Data-use policy | `data_entitlements` | Public remains private-research/owner-private only; no `public_display`, `ai_analysis`, or redistribution |
| Options/risk research | `trade_analyzer`, `risk_guardrails`, `options_suggestions`, quote-quality modules | Not promoted from an underlying state. Contract-level options evaluation remains unavailable until exact quotes are supplied |
| Workspace and assistant | `/workspace`, `TradingWorkspace`, `workspace-evidence` | Extended the same page and deterministic assistant; no second research UI |

## What was missing

- No intraday VWAP or EMA 9 calculator in `main`.
- No traditional pivot projection or confirmed opening-range contract.
- No authenticated setup-state endpoint for the workspace.
- No setup-specific entry, invalidation, stop, or target references.
- No deterministic assistant answers for setup rules, missing conditions, or changes since the last confirmed candle.
- No position-specific exit evaluation in the workspace.

PR #102 (`research/confirmed-opening-range`) contains an internal opening-range helper and its tests. Its branch is based on an older `main`, so its tree was **not** cherry-picked. Phase 2 reuses the same core rules: 5-minute regular-session bars, a 15-minute opening range, a later confirmed close outside it, rejection when price returns inside, and rejection of incomplete/stale/unconfirmed data.

## Implemented contract

`GET /v1/research/trade-intelligence/{symbol}` is authenticated by the existing bearer boundary and returns a derived-only payload:

- `schema_version: alphaos-trade-intelligence-v1`
- session state/date/open/close, data status, provider, snapshot ID, timestamps, freshness, completeness, confirmed bar count, warnings
- previous-session high/low/close and traditional pivot/R1/R2/S1/S2
- current-session high/low
- first 15-minute opening range
- session VWAP and EMA 9 when supported by confirmed bars
- existing backend support/resistance references
- three setup families: opening-range breakout, VWAP + EMA 9 continuation, support/resistance reversal
- per setup: state (`BUY`, `SELL`, `WAIT`), evidence, missing conditions, entry trigger, invalidation, stop reference, target reference, risk distance, R:R, timestamp, freshness, wait reason
- `exit_early` only for an explicitly modelled position with a verified exit quote
- no confidence percentage and no raw candles

The module is `modules/trade_intelligence.py`; the route is `alphaos_api/trade_intelligence.py`. It projects over the existing `ResearchService` and `CandleService`; it does not fetch a second market series or create a second strategy engine.

## Finality and fail-closed rules

- A candle is used only when it belongs to today’s regular session, begins on the 9:30 ET 5-minute grid, and its interval has elapsed.
- If the provider does not mark the newest bar complete, that bar is excluded. Earlier bars remain usable because a later regular-session bar proves those intervals have elapsed.
- A missing opening bar, interior gap, stale feed, delayed feed, or pre-open/closed session prevents a live intraday setup from being asserted.
- BUY/SELL are underlying research states. They are never described as an options trade, fill, probability, or profit.
- `EXIT EARLY` requires a modelled position, an invalidation, a maximum modelled loss, a verified exit quote, and confirmed underlying evidence.
- Options candidates require a contract-level quote, maximum modelled loss, and a positive small-account budget. Without those, the status is `unavailable`.

## Website integration

`/workspace` now renders:

- session state and data freshness
- previous-session H/L/C, current-session H/L, pivots, opening range, VWAP, EMA 9
- three setup cards with state, evidence, missing conditions, entry, invalidation, stop, target, and R:R
- session/data warnings and the explicit early-exit gate
- deterministic assistant answers for confirmation rules, breakouts versus reversals, invalidation, WAIT reasons, closest setup, and the last confirmed candle change

SPY/QQQ switching and the existing mobile layout are preserved. No Public data is sent to an external AI provider.

## Validation performed

- `python -m pytest -q tests/test_trade_intelligence.py tests/test_trade_intelligence_api.py` — **21 passed**
- Backend regression slice (`test_trade_intelligence*`, `test_research_api`, `test_candles_api`, `test_structure_research`) — **77 passed**
- Expanded backend slice after merging `main` #104 (`+ test_market_data_gateway`, `test_public_intraday`) — **123 passed**
- `cd web && npm test` — **276 passed**, including the authenticated bridge validation and graceful setup-contract failure tests
- `cd web && npm run typecheck` — passed
- `cd web && npm run build` — passed
- Browser checks at 390px and 1440px with a mocked authenticated market response — rendered, no horizontal overflow; session/pivot cards, setup cards, and assistant visible
- The browser mock is a UI contract check, not a live market observation or a performance test.

## Limitations and blocked items

- Public’s adapter currently reports final-bar completion as unknown. Live finality is therefore not claimed; the newest bar is excluded and setups may remain WAIT with an explicit `unconfirmed_close`/`last_bar_excluded_unconfirmed` reason.
- The trade-intelligence endpoint does not request an options chain. It cannot state that a BUY/SELL setup is an executable or profitable options trade.
- No modelled position or exit quote is connected to the workspace, so EXIT EARLY is unavailable there by design.
- No historical replay or out-of-sample performance claim is made. Fixture tests validate decision mechanics, not profitability, win rate, or edge.
- Production environment variables, authentication, entitlements, `/api/candles`, and first-party Public candle display were not changed.
