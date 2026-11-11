# Phase C — First-party chart implementation specification

Status: implementation complete, **native display disabled by default** pending
written Public authorization for authenticated website display. The chart route,
typed client, chart adapter, presentation state, and route-level fallback are in
`web/`. With the feature switch off, `/market/chart` serves the legacy external
TradingView fallback and `/api/candles/{symbol}` fails closed with
`feature_disabled`.

See [candle display entitlement and probe](CANDLE_DISPLAY_ENTITLEMENT_PROBE.md)
for the exact licensing blocker, approval requirements, and private
end-to-end probe.

## Goal

Render AlphaOS-owned, provider-independent SPY/QQQ candlesticks from
`GET /v1/candles/{symbol}` for `1m`, `5m`, and `15m`, with volume, session and
quality state visible to the user.

## Data source

- Use only the server response `alphaos-candles-v1`. Never read Public SDK
  fields, raw provider payloads, or quote observations to construct candles.
- Request `session=regular` for v1. Do not send extended-hours bars into the
  regular chart.
- Treat `snapshot_id` as the identity of the displayed server snapshot.
- Use `latest_candle_at` and `retrieved_at` for the freshness label.
- Use `expected_bars`, `received_bars`, `returned_bars`, `completeness`,
  `last_bar_status`, `freshness`, and `warnings` for user-visible quality state.
- Do not fill, interpolate, synthesize, or relabel a candle in the browser.
  Missing bars remain a visible gap/warning.

## Chart surface

Use TradingView Lightweight Charts as a new first-party component, separate from
the existing widget. It must:

1. Render native AlphaOS OHLCV candles with a UTC time scale.
2. Render volume in a lower pane with a readable price/volume divider.
3. Support `1m`, `5m`, and `15m` switching and preserve the user's selected
   timeframe while refreshing.
4. Support optional EMA overlays computed client-side from the returned native
   closes only. Label the periods and state that EMAs are derived indicators,
   not provider observations.
5. Show a separate current-price marker sourced from the authenticated quote
   surface, labeled with its own timestamp and freshness. Do not merge the quote
   into the last candle.
6. Show a compact status row: provider, snapshot time, freshness age, whether the
   last bar is complete/partial/unknown, and completeness.
7. Show warning chips for `missing_bars`, `incomplete_session`,
   `provider_incomplete_bars_skipped`, `session_in_progress`,
   `last_bar_completion_unverified`, `last_bar_window_open`, `stale_candles`,
   and `latest_available_session`; do not hide warnings behind a tooltip only.
   `last_bar_window_open` is a time-based warning, not a claim that the provider
   marked the bar partial.
8. Include TradingView attribution and the required Lightweight Charts license
   notices.
9. Be mobile-responsive: touch pan/zoom, readable price/volume labels, a
   timeframe control that wraps or scrolls, and no horizontal page overflow.
10. Render explicit loading, empty, unavailable, unauthorized, throttled, and
    provider-error states. A 429 must not auto-retry in a tight loop.

## Refresh behavior

- Poll no faster than the server cache window; start at 20 seconds and back off
  on 429/503.
- Abort superseded requests with `AbortController` and ignore stale responses by
  `snapshot_id`.
- Keep the last successful snapshot visible while refreshing, clearly labelled as
  cached/stale when appropriate.
- Do not calculate a new snapshot ID locally.

## Component and state boundaries

- A typed candle client owns fetch, auth header propagation, abort, and error
  mapping.
- A chart adapter owns conversion from the AlphaOS response to the charting
  library's series format. It must preserve `snapshot_id` alongside the series.
- A presentation component owns timeframe controls, overlays, status, warnings,
  and accessibility labels.
- A feature flag or route-level switch must allow rollback to the current
  TradingView widget. Do not remove the widget in the first implementation.

## Acceptance tests

- SPY and QQQ at all three intervals render with volume.
- Timeframe switching cancels in-flight requests and never mixes series.
- A missing bar produces a gap and a visible warning; no synthetic bar appears.
- An incomplete or stale snapshot is visibly labelled, not treated as healthy.
- A partial last bar is visibly labelled and has no completion claim.
- The current-price marker uses quote freshness independently of candle
  freshness.
- A 401/403, 429, 503, and timeout each produce a distinct usable state.
- Mobile viewport has no horizontal overflow and controls remain reachable.
- The old widget remains available when the feature flag is off.
- No Public data is rendered in a public/commercial context without an explicit,
  documented entitlement change.

## Out of scope for Phase C

Server-side indicator calculation, Gemini synchronization, extended-hours
rendering, order execution, and any public redistribution of Public data.

## Implementation

- Route: `/market/chart?symbol=SPY|QQQ&interval=1m|5m|15m`.
- Browser bridge: `/api/candles/{symbol}` verifies the website session, forwards
the provider request with the server-side bearer token, validates the complete
`alphaos-candles-v1` body, and never returns partial or malformed snapshots.
- Typed client and contract: `web/src/lib/candles.ts`.
- Chart adapter, EMA calculation and native gap preservation:
  `web/src/lib/candle-chart.ts`.
- Presentation, polling/backoff, warning chips, status row and independent quote
  marker: `web/src/components/market/chart/CandleChartPanel.tsx`.
- Lightweight Charts renderer with UTC scale, volume pane and quote price line:
  `web/src/components/market/chart/LightweightCandleChart.tsx`.
- Fail-closed switch: `ALPHAOS_CANDLE_CHART_ENABLED` defaults to off. The route
  serves the external TradingView fallback and the bridge returns
  `feature_disabled`. Even with the switch on, the bridge requires a
  `public_display` entitlement decision, a present authorization reference, and
  the provider `public_display` capability; a `private_research` snapshot is
  rejected as `data_use_denied`. Use `/market/chart?symbol=SPY&view=legacy` for
  the rollback path while the switch is on. The archive research page is
  unchanged and links to the chart.
- Attribution and the Apache-2.0 license are shown on the chart route and
  served from `/licenses/lightweight-charts.txt`.

Validation for this implementation:

- Web typecheck and production build pass.
- The full web unit suite passes, including new candle contract, gap, EMA,
  client-error and authenticated-route tests.
- The Chromium browser tests pass with the switch enabled only in the isolated
  test server and mocked capabilities. They cover native candles, volume,
  warnings, interval switching, snapshot identity, the independent quote marker,
  mobile overflow and the feature-flagged fallback. CI installs Playwright's
  browser dependencies before the web job. These tests do not establish provider
  display rights or live availability.
