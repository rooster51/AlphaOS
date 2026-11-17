# After-hours research in the unified trading workspace

Date: 2026-11-17
Branch: `fix/after-hours-workspace-research`
Base: `origin/main` at `73a5624` (PR #109)

## Problem

During the regular session the workspace displayed a verified SPY/QQQ quote,
support/resistance, ATR, structure and the Phase 2 setup contract. After the
close it returned:

```json
{
  "status": "unavailable",
  "code": "market_closed",
  "stage": "market_validation",
  "upstream_code": null,
  "error": "Market research is unavailable; no market data was substituted."
}
```

The backend was not failing to provide contextual evidence. The website bridge
was discarding it.

## Confirmed root cause

1. `web/src/lib/alphaos-server.ts` calls `GET /v1/market/{symbol}` and
   `GET /v1/structure/{symbol}?snapshot_id=...`.
2. After a completed session, `modules/quote_freshness.py` marks the Public
   closing observation `data_status: "latest_available"`,
   `market_state: "closed"`, `usable_for_live_research: false` and
   `usable_for_contextual_research: true`.
3. `alphaos_api/service.py` intentionally hides that price from
   `meta.current_spot` for live anchoring, but still builds the completed
   daily-history structure snapshot. The underlying closing price remains in
   `evidence.underlying_quote.quote.last`; ATR and levels remain in
   `/v1/structure`.
4. `web/src/lib/research-evidence.ts#verifiedMarketPair()` requires
   `data_status === "fresh"`, a regular/extended market state, a positive
   `meta.current_spot`, and `usable_for_live_research === true`.
5. `getMarketSnapshotServer()` therefore threw `market_closed` at
   `market_validation` even though both upstream responses were valid,
   snapshot-matched contextual evidence.

The failure is a frontend trust-boundary defect, not missing historical data
and not a backend closure failure. No archived or latest-session evidence was
substituted while the live gate rejected the response.

## Existing capability inventory

| Capability | Existing implementation | Endpoint / service | Data source and freshness | Used by workspace before | Missing integration |
| --- | --- | --- | --- | --- | --- |
| Latest verified session quote | `alphaos_api/service.py` (`snapshot`, `meta`), `modules/quote_freshness.py` | `GET /v1/market/{symbol}` | Public quote; after close `latest_available`, `market_state=closed`, `usable_for_live_research=false`, `usable_for_contextual_research=true` | Rejected by the live-only bridge | Accepted only as non-live context after this change |
| Daily structure / ATR / support-resistance | `modules/price_structure.py`, `alphaos_api/app.py` | `GET /v1/structure/{symbol}?snapshot_id=...` | Completed Public daily OHLC, anchored to the verified snapshot price | Rejected with the market pair | Reused unchanged as historical structure |
| Snapshot consistency | `alphaos_api/service.py#snapshot` | Shared `snapshot_id` on market and structure | Same market bundle, expiry, symbol and horizon | Partially used for live only | Extended to require the same verified non-live pair |
| Previous-session pivots | `modules/trade_intelligence.py` | `GET /v1/research/trade-intelligence/{symbol}` | Completed previous-session OHLC | Available when the optional contract succeeded | Displayed as historical context; still optional |
| Opening range | `modules/trade_intelligence.py` | Same optional contract | First three confirmed regular-session five-minute bars | Live only in practice | Returned only if the candle gateway supplies that session; otherwise unavailable |
| VWAP | `modules/trade_intelligence.py` | Same optional contract | Confirmed regular-session five-minute bars with positive volume | Live only in practice | Same |
| EMA 9 | `modules/trade_intelligence.py` | Same optional contract | Confirmed regular-session five-minute closes | Live only in practice | Same |
| Phase 2 setup evaluation | `modules/trade_intelligence.py`, `alphaos_api/trade_intelligence.py` | Same optional contract | Confirmed intraday bars plus completed daily OHLC and ATR | Yes during live sessions | Preserved; closed sessions are forced to WAIT by the backend |
| Supabase archive observation | `modules/archive_observation.py`, `alphaos_api/research2.py` | `POST /v1/research/observation` with `research_mode=historical` | Verified Supabase options snapshot; observation-only | No | Not used for workspace structure; it contains no daily candles, ATR, pivots, VWAP or opening range |
| Archive-backed historical options research | `ArchiveResearchService`, `run_latest_market`, `modules/market_archive_adapter.py` | `POST /v1/research/market` with `research_mode=historical` | Verified Supabase archive plus completed Public daily history | No | Not duplicated in the workspace; existing strategy research remains the options surface |
| Historical candles / provenance | `alphaos_api/candles.py`, `modules/market_data_gateway.py` | `GET /candles/{symbol}` | Public regular-session candles with completeness and retrieval provenance | No direct workspace chart use (first-party chart remains gated by display entitlement) | Not changed |
| Session classification | `modules/market_session_gate.py`, `modules/quote_freshness.py` | Shared modules | NYSE calendar; regular/extended/closed state | Only indirectly | Preserved and used to distinguish live from historical |

The Supabase archive observation is real, verified evidence, but it is not a
substitute for market structure. Using it to invent ATR, pivots, VWAP, EMA 9 or
opening range would violate the existing observation-only contract. The
workspace therefore reuses the existing last-verified-session market/structure
pair, which already carries those fields.

## Phase 2 compatibility

| Model | Required evidence | Available after close | Workspace behavior |
| --- | --- | --- | --- |
| Opening Range Breakout | Confirmed five-minute bars from the session open, opening range, later confirmed close | Only if the existing candle gateway still holds the completed session; bar completeness is checked by `confirmed_session()` | Levels may display. The backend returns WAIT for a closed session. Any non-WAIT state is relabeled as historical by the bridge and cannot become the current stance. |
| VWAP + EMA 9 Continuation | Confirmed contiguous session bars, positive volume, at least nine closes | Same as above | VWAP/EMA 9 are shown only when calculated. Missing values remain `Unavailable`, never inferred. |
| Support/Resistance Reversal | Verified structure levels, ATR, tested level and confirmed closes | Structure levels and ATR are available from completed daily history; confirmed intraday closes depend on the candle gateway | Setup conditions may be inspected. No closed-session entry is actionable. |

No historical setup results are fabricated by applying the latest price to old
indicators. The existing backend already gates a closed session to WAIT. As a
second boundary, the website treats every non-live snapshot as historical and
never exposes its state as the current trading stance.

## Minimal fix

- `web/src/lib/research-evidence.ts`
  - Added `verifiedLatestSessionPair()` for `latest_available`/`closed`
    responses: same symbol, schema and snapshot ID; contextual usability; no
    live usability; verified closing quote in `underlying_quote`; positive ATR;
    matching observation timestamp.
  - Added `latestSessionSpot()` to read the verified closing price only after
    that pair passes validation.
- `web/src/lib/alphaos-server.ts`
  - Keeps the original live validation and all live safeguards unchanged.
  - Falls back only to the paired last-verified-session evidence, labels it
    `last_verified_session`, sets `isLive: false`, and never reads a live
    `current_spot`.
  - Marks the optional trade-intelligence contract as historical when the
    market is closed.
- `web/src/lib/workspace-evidence.ts`
  - Accepts the new source with an explicit non-live requirement.
  - Forces the current assessment stance to WAIT for every non-live snapshot.
  - Keeps historical setup observations visible but marks them historical.
  - Makes the evidence assistant answer in historical terms and never confirm a
    current BUY/SELL from historical evidence.
- `web/src/components/workspace/TradingWorkspace.tsx`
  - Shows the last verified session date and observation timestamp.
  - Adds a visible historical-only notice.
  - Labels setup states as `HISTORICAL BUY` / `HISTORICAL SELL` when applicable.
  - Preserves SPY/QQQ selection, optional trade-intelligence isolation, backend
    diagnostics and authenticated access.
- `web/src/types/research.ts`
  - Adds the explicit `last_verified_session` source.

No backend endpoint, archive contract, authentication rule or deployment
configuration was changed.

## Regression coverage

Added or updated tests cover:

- Live market pair acceptance (existing regression remains green).
- Closed market with a valid last-verified-session pair for SPY and QQQ.
- Closed market without a verified underlying observation.
- Closed market with structure present and optional trade intelligence failing.
- `latest_available` / `closed` validation, snapshot mismatch, symbol mismatch,
  missing quote, ATR failure and timestamp mismatch.
- Source/`isLive` mismatch rejection.
- Historical session snapshot normalization and display fields.
- Historical BUY observation cannot become the current BUY/SELL stance.
- Assistant answers remain historical and do not assert a current entry.
- Existing authentication, configuration and optional trade-intelligence
  failure isolation tests remain unchanged.

## Verification

- Focused web tests: `workspace-bridge`, `workspace-evidence` and
  `research-evidence`.
- Full web test suite.
- `npm run typecheck`.
- `npm run build`.
- Deployment-boundary checks.
- Full Python suite (unchanged backend, but required by the release gate).

## Production verification

Production is protected by Netlify Edge Access. An unauthenticated request to
`https://alphaostrading.netlify.app/api/health` returned HTTP 401, so the
`backend_target` value could not be read from this environment without the
owner's authenticated session. That is a verification limitation, not evidence
of a staging/production mismatch.

After signing in to the production site, the owner should:

1. Open `https://alphaostrading.netlify.app/api/health` and confirm
   `research_configuration.backend_target` is `production`. The expected URL is
   `https://alphaos.onrender.com`; `staging` means Netlify production still
   points at `https://alphaos-api-staging.onrender.com`.
2. Confirm the deployed frontend commit matches the merge commit for this PR.
3. Confirm the production Render service is running the merged backend commit.
4. After the close (or on a weekend/holiday), open `/workspace` and verify:
   - the header says `LAST VERIFIED SESSION`;
   - the session date and observation timestamp are shown in New York time;
   - ATR, support/resistance and any available pivot/opening-range/VWAP/EMA
     fields are visible;
   - the current state is `WAIT` and no live BUY/SELL is asserted;
   - the historical-only notice is visible;
   - both SPY and QQQ load.
5. If the workspace still returns `market_closed`, inspect the Netlify bridge
   log request ID. A `backend_target` of `staging`, a missing `latest_available`
   response, or a structure snapshot mismatch should be treated as configuration
   or deployment drift, not as permission to synthesize data.

Do not expose the API token, Netlify session, Render credentials or raw upstream
bodies during verification.
