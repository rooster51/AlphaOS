# Unified Trading Workspace integration audit

Date: 2026-11-17
Base: `origin/main` at `53278420` (includes PR #109, PR #111 and PR #113)
Focused branch: `fix/after-hours-workspace-research` (PR #110), merged with that base

This audit covers the production workspace, native chart, options/strategy
research, after-hours research, and the evidence assistant. It does not
authorize a production deploy, a candle-display switch, or trading execution.

## Confirmed repository and production state

| Item | Evidence | Status |
| --- | --- | --- |
| PR #101 closing-auction normalization | Merged before the audited base | Merged |
| PR #108 trade-intelligence diagnostics | `c38ef3a` | Merged |
| PR #109 candle timestamp handling | `73a5624`; PR merged 2026-11-17 02:00:57Z | Merged |
| PR #110 after-hours workspace research | Branch `fix/after-hours-workspace-research`; first fix `4e3fa08`, plus audit and Next.js security update | Open, not merged |
| Render production process | `GET https://alphaos.onrender.com/health` returned `200` with `authentication_configured:true` | Reachable |
| Render market route | `GET /v1/market/SPY?horizon=3` returned `401 authentication_required` | Route registered |
| Render trade-intelligence route | `GET /v1/research/trade-intelligence/SPY` returned `401 authentication_required` | Route registered, not a 404 |
| Netlify production site | `/`, `/workspace`, and `/api/health` returned `401` with the Netlify Edge Access login redirect | Public access blocked |
| Netlify deployed frontend revision | No GitHub deployment records; production HTML/API is Edge Access protected | Not independently verifiable |
| Production `backend_target` | `/api/health` requires the owner's Edge Access session | Not verifiable without owner authorization |

The Render 401 responses prove the routes exist and the bearer boundary is
active. They do not prove that Netlify production points at
`https://alphaos.onrender.com`, nor which frontend/backend commits are live.
Those remain configuration and deployment checks, not code conclusions.

## Capability matrix

| Capability | Existing implementation | Workspace surface | Status and boundary |
| --- | --- | --- | --- |
| Verified market evidence | `/v1/market/{symbol}` via `/api/market` | Spot, direction, ATR, caveats | Integrated. PR #110 accepts a verified `latest_available` closing observation outside hours. |
| Structure / support / resistance | `/v1/structure/{symbol}` | Level lists and ATR/metrics | Integrated. Snapshot ID is shared with market evidence. |
| Trade intelligence | `/v1/research/trade-intelligence/{symbol}` | Pivots, prior/current session, opening range, VWAP, EMA 9, data status | Integrated as an optional contract. Failure cannot discard market/structure evidence. |
| Three setup models | Existing trade-intelligence setup contract | Three setup cards and missing conditions | Integrated. Closed-session setups are forced to WAIT and labelled historical observations. |
| Options research | Existing `/options` page and `/api/options` bridge | Workspace links to `/options?symbol=SYMBOL` | Integrated; symbol is preselected. No request is sent until the user acts. |
| Strategy research | Existing `/strategies` page and `/api/research/market` | Workspace link to `/strategies?symbol=SYMBOL` | Integrated. Archive evidence remains historical and non-executable. |
| Evidence assistant | Deterministic `answerWorkspaceQuestion` | Grounded answers from the selected snapshot | Integrated; no external AI provider or invented fields. PR #110 adds historical wording. |
| Native candle chart | `LightweightCandleChart` and `/market/chart` | Separate full chart route | Implemented, but not embedded in the workspace. Native display is disabled by default. |
| Candle contract consumption | `alphaos-candles-v1` parser and bridge | SPY/QQQ, 1m/5m/15m, regular session | Verified with a mocked browser fixture. No fabricated bars or gaps. |
| Historical candle-session selection | Candle API accepts only `interval`, `session=regular`, and `limit` | None | Not available. The API returns the newest N bars; there is no date/session selector. |
| TradingView fallback | `TradingViewFallback` | Workspace and `/market/chart` when the native switch is off | Integrated and verified locally. It is explicitly labelled as external, non-AlphaOS evidence. |
| Owner-private display entitlement | Owner session -> bridge header -> provider `owner_private_display` | `/api/candles` and `/api/current-quote` | Gated. Public display, redistribution, other users, and AI processing remain denied. |
| Historical options archive | `/market?symbol=...` with explicit historical mode | Archive research page | Integrated. Historical and current-market research are explicitly distinguished. |
| Backend target diagnostics | `/api/health` -> `research_configuration.backend_target` | Not shown in workspace UI | Available through the health endpoint, subject to production authentication. |

## Verified integration defects and fixes

1. **After-hours rejection at the live-only gate.** `/api/market` discarded a
   valid `latest_available` market/structure pair as `market_closed`. PR #110
   adds a distinct `last_verified_session` path, forces the current stance to
   WAIT, and labels historical setup observations. Live validation is unchanged.
2. **No workspace browser regression.** The workspace had unit/bridge coverage
   but no browser-level live/closed workflow test. Added
   `web/tests/browser/workspace.spec.ts` covering SPY/QQQ switching, historical
   labelling, WAIT, assistant grounding, and options-link symbol propagation.
3. **Merged live gate nullified verified historical setups.** PR #113 requires a
   directional trade-intelligence state to be open, fresh, and complete. That is
   correct for live evidence but also rejected a verified closed-session
   `latest_available` observation, leaving the workspace with no historical setup
   cards. The guard now keeps the live checks unchanged and allows a directional
   historical observation only when the session is closed, data is verified, and
   completeness is not incomplete. The workspace still forces the actionable
   stance to WAIT and labels the observation historical.

No other runtime integration defect was found in the audited paths.

## Deliberately missing connection

The workspace embeds `TradingViewFallback`, not `CandleChartPanel`. This is
intentional while the Public browser-display interpretation remains unresolved.
The native chart is available on `/market/chart` behind
`ALPHAOS_CANDLE_CHART_ENABLED=true`, an owner session, and the provider
`owner_private_display` decision.

If Public later confirms browser display and the owner enables the switch, the
workspace would still need a small conditional integration to embed the native
chart. That should be a separate, explicitly authorized change. It must not be
enabled by default or exposed to anonymous/viewer sessions.

## Verification record

### Automated and static checks

- Next.js installed and locked at `16.4.6`.
- `npm ci`: 0 vulnerabilities.
- `npm audit --omit=dev --audit-level=moderate`: 0 vulnerabilities.
- `npm audit --audit-level=moderate`: 0 vulnerabilities.
- Web unit/integration suite: 303 passed.
- TypeScript typecheck: passed.
- Production build: passed.
- Playwright Chromium suite: 70 passed.
- Deployment-boundary check: passed (494 tracked files).
- Full Python suite: 1,693 passed, 1 skipped, 64 subtests passed.

### Browser verification (mocked bridge)

A cloud browser was run against the local production build with intercepted
AlphaOS bridge responses. This verifies rendering and interaction, not real
production market data:

- Workspace SPY closed state showed `LAST VERIFIED SESSION`, the historical-only
  notice, `WAIT / RESEARCH STATE`, `HISTORICAL BUY`, and the verified closing
  spot.
- Switching to QQQ showed `LIVE OBSERVATION`, the live spot, and updated
  `/options?symbol=QQQ`.
- The evidence assistant returned the setup-specific invalidation.
- Native chart rendered SPY 1m, 5m, and 15m snapshots and switched snapshots.
- The legacy TradingView fallback rendered when the native switch was off.
- `/options?symbol=QQQ` preselected QQQ and sent no options request.
- Historical archive research showed the historical banner and stale-archive
  message with a mocked archive response.

The Playwright suite was also run locally against the production build using an
isolated Chromium library prefix because this VM has no writable system package
manager. All 70 Chromium tests passed, including the workspace live/closed
symbol-switch regression.

### Real production responses

- Netlify production returned the Edge Access login redirect (401) for
  unauthenticated HTML and `/api/health` requests.
- Render `/health` returned 200.
- Render `/v1/market/SPY` and `/v1/research/trade-intelligence/SPY` returned
  authenticated 401 responses, confirming route registration.

No authenticated production market response, workspace render, or candle
response was obtained.

## Remaining blockers

1. Netlify Edge Access prevents reading `research_configuration.backend_target`
   and deployed revisions without the owner session.
2. Public has not confirmed that an authenticated hosted browser is authorized
   under its terms; the provider's `owner_private_display` interpretation remains
   unresolved and the deployment switch must stay off.
3. The candle API has no historical-session/date parameter, so a historical
   candle selector cannot be implemented without a backend contract change.

## Owner production checklist

1. Sign in to `https://alphaostrading.netlify.app/api/health` and confirm
   `research_configuration.backend_target` is `production`.
2. Confirm the deployed frontend commit matches the merge commit and the Render
   service runs the corresponding backend commit.
3. Open `/workspace` after the close and repeat the SPY/QQQ historical checks.
4. Confirm the native chart remains on the TradingView fallback unless the
   browser-display authorization question is resolved and the owner explicitly
   enables `ALPHAOS_CANDLE_CHART_ENABLED`.
5. Do not expose the bearer token, Edge Access session, or provider entitlement
   headers while collecting evidence.
