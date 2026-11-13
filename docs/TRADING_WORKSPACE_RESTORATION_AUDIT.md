# AlphaOS Trading Workspace Restoration Audit

Date: 2026-11-13  
Branch: `fix/restore-trading-workspace`  
Base: `origin/main` at `c56cbd2` (merge of PR #100)

## Scope and method

Audited the current `main` route tree, components, server bridges, deployment
configuration, recent merged PRs, and the existing Python research modules.
The objective was to reconnect existing capabilities into one SPY/QQQ
workspace, not to build a second chart, research, or AI stack.

No production environment variables, deployments, authentication rules, or
Public entitlements were changed.

## Capability matrix

| Capability | Existing implementation | Status before this branch | Root cause / action |
| --- | --- | --- | --- |
| SPY/QQQ chart | `CandleChartPanel.tsx`, `LightweightCandleChart.tsx`, `candles.ts`, `/market/chart` | Implemented but disabled in production | `ALPHAOS_CANDLE_CHART_ENABLED !== "true"` selects `TradingViewFallback`. First-party display remains disabled pending provider display authorization. |
| External chart fallback | `TradingViewFallback.tsx` | Connected, broken for QQQ | Hardcoded `AMEX%3A${symbol}`. QQQ is Nasdaq-listed. Fixed with an explicit exchange map (`SPY -> AMEX`, `QQQ -> NASDAQ`) and mobile-sized iframe. |
| Current quote / freshness | `/api/current-quote`, `current-quotes.ts`, `CurrentQuoteCards.tsx`, `/api/market` | Implemented and connected on the dashboard | The unified workspace reads the existing `/api/market` bridge and displays source, `as_of`, and live/archive state. No new quote feed was added. |
| Trend classification | Existing research classifier; `opportunity_state.direction` through `/api/market` | Implemented; visible inside Strategy Research | Surfaced directly in the workspace as UP / DOWN / CHOP / UNKNOWN, explicitly labelled descriptive rather than a trade signal. |
| Support and resistance | Backend structure levels returned by `/api/market` (`levels`) | Implemented but not present in one unified surface | Reused unchanged. The workspace displays only returned levels and does not recalculate them. |
| Pivot points | Backend price-structure modules exist | Not supplied by the validated website market payload | No values are inferred. The workspace reports the field as not supplied. |
| Previous-day high/low | Backend research has completed-session observations | Not supplied by the validated website market payload | No values are inferred. The workspace reports the field as not supplied. |
| Opening range | No validated website payload field found | Missing connection | Not fabricated. Reported as unavailable. |
| BUY / SELL / WAIT | No validated signal endpoint returning confidence and evidence | Missing connection | The workspace shows `WAIT` (or `UNAVAILABLE`) because no verified entry/invalidation model is connected. Direction bias is shown separately and is not promoted to a signal. |
| Entry / invalidation / stop / target | Python research modules exist (for example `modules/trade_analyzer.py`, `modules/income_risk.py`) | Not exposed as validated website evidence | Not invented. Listed as not connected, with links to the existing research surfaces. |
| Early-exit warnings | No validated website payload field found | Missing connection | Not invented. Listed as not connected. |
| Options strategy research | `/market`, `/strategies`, `/options`, `/structures`, `StrategyResearchDashboard.tsx`, `MarketResearchPanel.tsx` | Implemented and connected | Preserved. The workspace links to the existing pages and does not duplicate their candidate logic or quotes. |
| AI research chat | External MCP/ChatGPT OAuth server code only (`alphaos_api/mcp_server.py`, `mcp_auth.py`); no visible web chat component | Missing from the website | Added a visible deterministic evidence assistant. It calls no external AI provider and answers only from the current validated snapshot. General concept education is allowed; missing live fields are stated explicitly. |
| Unified navigation | `Sidebar.tsx` | No workspace entry | Added `Trading Workspace` at the top of primary navigation and a dashboard link. |

## Production chart diagnosis

1. **Why the first-party chart is disabled.** `/market/chart` checks
   `process.env.ALPHAOS_CANDLE_CHART_ENABLED !== "true"` and renders the legacy
   fallback unless the flag is exactly `"true"`. The flag was not enabled.
   `/market/chart?view=legacy` also forces the fallback. The deployed build does
   contain `CandleChartPanel` and its client chart dependency; this is a flag
   decision, not a missing component.
2. **Why QQQ failed.** The fallback constructed
   `https://s.tradingview.com/widgetembed/?symbol=AMEX%3AQQQ...`. QQQ does not
   trade under the AMEX prefix on TradingView, so the widget returned
   `This symbol doesn't exist`. The exchange must be per symbol. Fixed.
3. **Mobile controls.** The fallback iframe was fixed at 520 px and its warning
   was long. The workspace gives the chart a responsive 420/560 px frame and
   keeps symbol switching, research, and assistant controls in single-column
   flow below the `xl` breakpoint.
4. **Deployment does not prove the chart works.** No deployment was performed
   on this branch. The fallback fix is covered by a pure unit test, and the
   workspace is compiled; live browser validation is still required after
   deployment.

## Public.com candle blocker

The candle diagnostic/fix work is on a separate draft branch and is **not**
included here:

- Branch: `fix/public-candle-diagnostics`
- Draft PR: `rooster51/AlphaOS#101`
- Validated workflow: run `43321193381` on commit `1cbff97`
- Result: SPY and QQQ at 1m/5m/15m returned 390/78/26 bars with
  `completeness=complete` and no errors. The run was after the regular close,
  so freshness was `stale`, which is expected.

The earlier `invalid_provider_response` result for all six combinations is
superseded by that successful run. This branch does not enable first-party
Public candles, does not alter validation, and does not synthesize bars.

## Implemented in this branch

- `web/src/app/workspace/page.tsx` — new unified read-only route.
- `web/src/components/workspace/TradingWorkspace.tsx` — responsive workspace
  composing the existing market bridge, external fallback chart, levels,
  WAIT assessment, research links, and evidence assistant.
- `web/src/lib/workspace-evidence.ts` — fail-closed snapshot normalization,
  WAIT assessment, and deterministic evidence-grounded answers.
- `web/src/lib/tradingview.ts` — explicit SPY/QQQ exchange mapping and embed URL.
- `web/src/components/market/chart/TradingViewFallback.tsx` — QQQ mapping fix,
  accessible title, responsive height.
- `web/src/components/shell/Sidebar.tsx` and `web/src/app/dashboard/page.tsx` —
  workspace navigation and dashboard entry.
- `web/tests/workspace-evidence.test.mjs` — unit coverage for mapping,
  normalization, unavailable states, WAIT behavior, and assistant grounding.

## Verification

- `npm test` in `web/` (existing Node test suite plus the new workspace tests).
- `npm run typecheck` in `web/`.
- `npm run build` in `web/`.
- Browser validation of `/workspace` on a 390 px viewport and desktop after
  deployment; not performed in this environment.

## Still blocked

- First-party Public candle display needs confirmed provider display
  authorization/entitlement. The flag remains unchanged.
- Pivot points, previous-day high/low, opening range, entry/invalidation,
  stop/target, early-exit warnings, and executable options quotes have no
  validated fields in the unified market payload. They remain explicitly
  unavailable rather than inferred.
- Production verification requires the owner session gate and a deployment,
  neither of which is authorized in this branch.

## Recommended next step

Merge the candle diagnostics PR only after owner review, then add a validated,
versioned structure endpoint that returns prior-session OHLC and explicit
pivot/opening-range evidence. Once those fields exist, the workspace can render
them and connect a verified entry/invalidation model without changing the
read-only guarantees.
