# Charting & AI (standalone research page)

`/charts` combines the official TradingView Advanced Chart widget with an
AlphaOS research assistant. It is read-only research: it does not execute, modify
or cancel orders and it does not change the November paper-trading pilot, the
Public provider, the existing research engines or any existing route.

## Page and navigation

- Route: `web/src/app/charts/page.tsx` (`force-dynamic`). Query parameter
  `?symbol=SPY|QQQ`; anything else falls back to SPY.
- Navigation: "Charting & AI" is added to the existing sidebar immediately above
  "Market Research"; authentication, layout, branding and the mobile drawer are
  unchanged.
- The page uses the existing `Header` / `StatusPill` shell components and the
  terminal colour tokens.

## TradingView integration

- Official widget only: `https://s3.tradingview.com/tv.js` creates the Advanced
  Chart inside the page. Nothing is scraped, mirrored or proxied.
- Mapping: SPY → `AMEX:SPY`, QQQ → `NASDAQ:QQQ`.
- Defaults: dark theme, candlestick style (`style: "1"`), 15-minute interval,
  New York timezone, volume and RSI studies loaded, side toolbar (drawing tools)
  enabled, `allow_symbol_change: false`.
- Timeframes: 1m, 5m, 15m, 1h, 1D, 1W. Changing a timeframe recreates the widget
  with the new interval.
- Symbol changes happen only through the AlphaOS SPY/QQQ selector, so the widget
  and the assistant cannot disagree about the symbol. The selector also updates
  the page URL.
- The page states that TradingView data may be delayed, is governed by
  TradingView's terms, and is **not** an authorized AlphaOS market-data API.
- If `tv.js` fails to load (network policy, extension, CSP) the chart panel shows
  an explicit unavailable state with a retry button and a link to TradingView.
  It never draws a substitute chart.

## What the assistant is allowed to use

The assistant's only market context is the AlphaOS evidence record assembled
server-side by `web/src/lib/chart-evidence.ts` from the existing authenticated
research API:

| Field | Source |
| --- | --- |
| Underlying price, quote timestamp, freshness, market session | `GET /v1/market/{symbol}?horizon=3` |
| ATR(14) and backend price levels | `GET /v1/structure/{symbol}?horizon=3&levels=5` |
| Direction / regime labels | `evidence.market_state` from the market envelope |

Both envelopes must be `alphaos-research-v1`, `source: "Public"`, for the selected
symbol and the **same** `snapshot_id`. Anything else fails closed. Evidence that
is not currently fresh is returned as `point_in_time` with its original
`quote_as_of` and age; it is never relabelled as current. No candle, indicator,
level or quote is computed by the web app.

The chart page never reads TradingView state. The assistant receives the symbol
and the evidence block only.

## Assistant backend

`POST /api/charts/chat` is a real server-side chat route:

1. Rejects cross-origin browser calls (403) and throttles per client (30/min).
2. Validates the payload: SPY/QQQ, at most 12 turns, 2,000 chars per turn,
   12,000 chars total, last turn `user`, no unknown keys.
3. Fails closed with `503 chat_not_configured` when no model is configured.
4. Re-fetches the verified evidence pair for the selected symbol; if evidence is
   unavailable it returns 503 and never calls the model.
5. Calls an OpenAI-compatible chat-completions endpoint with a server-built
   system prompt containing the evidence and hard prohibitions.
6. Scans the reply for claims of direct chart access. A matching reply is
   **replaced** with a disclosure that AlphaOS cannot read the chart, and the
   response carries `chart_claim_blocked: true` plus `chart_access: "none"`.
7. Returns the reply, an evidence summary (symbol, mode, timestamp, age, spot,
   ATR, levels), and disclosures. Provider errors and credentials are never
   forwarded.

`GET /api/charts/evidence?symbol=SPY` exposes only the sanitized evidence summary
used by the page; credentials stay server-side.

### Configuration

Set these on the web service (never with a `NEXT_PUBLIC_` prefix, never in the
browser):

| Variable | Requirement |
| --- | --- |
| `ALPHAOS_CHAT_API_KEY` | Required secret API key for the chat provider. |
| `ALPHAOS_CHAT_MODEL` | Required model name accepted by that provider. |
| `ALPHAOS_CHAT_API_URL` | Optional HTTPS chat-completions URL. Default `https://api.openai.com/v1/chat/completions`. |

`ALPHAOS_API_URL` / `ALPHAOS_API_TOKEN` are the existing research backend
credentials and are also required for evidence.

Until the assistant variables are set, the page and the chat panel show an
explicit "not configured" state naming the missing variables. That is the
expected behaviour, not a bug, and no answer is fabricated.

## Candle archive audit (`market_candles`)

Reviewed code path:

- `modules/public_intraday.py` requests Public 1-minute OHLCV bars and normalizes
  complete bars only.
- `scripts/run_intraday_snapshot.py` upserts them through
  `modules/supabase_archive.persist_candles`.
- `supabase/market_archive.sql` defines
  `unique(provider, symbol, aggregation, bar_time)`.

The unique key is the **exact** `bar_time`, not the minute bucket. Two observations
of the same minute with different seconds (for example 14:31:12 and 14:31:47)
therefore both persist and read back as duplicate minute buckets. `persist_candles`
verifies that rows exist, not that a minute bucket is unique or that values agree.
The live table could not be queried for this change (no credentials in this
environment), so the contents remain unverified.

`modules/candle_integrity.py` is the read-only audit used instead of silently
deduplicating:

- groups raw rows into UTC minute buckets;
- preserves every raw row in the report (nothing is rewritten or deleted);
- distinguishes identical duplicates from conflicting duplicates;
- rejects inconsistent OHLC (`high < low`, `high < max(open, close)`,
  `low > min(open, close)`), negative volume, non-finite prices, non-object rows,
  missing identity fields and naive/invalid timestamps;
- exposes `validated_bars()` for buckets that are safe to use and
  `summarize_report()` for log-safe counts;
- reports informational gap statistics only, explicitly not a claim that bars are
  missing (session boundaries are not modelled).

`scripts/audit_market_candles.py` pages through Supabase with read-only GETs and
prints that report; `--output` writes the full report (including raw rows). It
requires the server-side `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` and never
prints them.

The chart assistant does **not** read `market_candles` directly. Service-role
credentials must not reach the browser, and the web service has no authorized
candle read path; candle-level answers would require the archive audit to be
resolved first. Until then the assistant states that candle and indicator values
are unavailable.

## Local verification captures

Screenshots were captured from the built app (`next start`) with Chromium. The
TradingView widget loaded real TradingView content. The AlphaOS evidence came
from a **local synthetic fixture backend** serving the real research envelope
schema, because this environment has no production API token or model
credentials. The quoted prices, levels, timestamps and assistant answer in these
captures are fixtures, not live AlphaOS research or a real model response.

| Capture | What it shows |
| --- | --- |
| [desktop](screenshots/charting-ai-desktop.png) | Charting & AI in the existing navigation, candlestick TradingView widget, evidence timestamp, assistant panel |
| [conversation](screenshots/charting-ai-conversation.png) | A grounded answer with the evidence timestamp, source and disclosures |
| [guardrail](screenshots/charting-ai-guardrail.png) | A provider reply claiming chart access replaced by the server guardrail |
| [point-in-time](screenshots/charting-ai-point-in-time.png) | QQQ evidence labelled point-in-time instead of current |
| [mobile](screenshots/charting-ai-mobile.png) | 390 px layout: chart, evidence and assistant in one column, no horizontal overflow |

## Tests

- `web/tests/charts.test.mjs`: evidence verification, point-in-time labelling,
  failure codes, timeout handling, prompt contents, chart-claim guard,
  request parsing, configuration fail-closed behaviour, grounded route responses,
  cross-origin rejection and credential non-disclosure.
- `web/tests/browser/charts.spec.ts`: navigation, SPY/QQQ widget + assistant
  synchronization, retained history, stale labelling, unavailable/timeout states,
  TradingView failure isolation, guardrail display, mobile layout.
- `tests/test_candle_integrity.py`: duplicate/conflicting/invalid bucket
  classification, raw preservation, minute bucketing, gap statistics and summary
  shape.

## Deployment steps

1. `cd web && npm ci && npm run build` (server-rendered service; no static export).
2. Configure the existing `ALPHAOS_API_URL` / `ALPHAOS_API_TOKEN`.
3. Configure `ALPHAOS_CHAT_API_KEY`, `ALPHAOS_CHAT_MODEL` and, if needed,
   `ALPHAOS_CHAT_API_URL`.
4. Deploy the web service, then verify in a live session: `/charts` loads from the
   sidebar, SPY and QQQ render in TradingView, symbol changes reach the chat
   request, a grounded answer returns with its timestamp, and the assistant
   refuses to describe the chart.
5. No backend deployment, collector change, migration or new market-data service
   is required for this page.

## Limitations and remaining blockers

- **Live archive contents are unverified.** No Supabase query was made for this
  change; duplicate and integrity findings come from the schema and writer code.
- **The assistant is unverified end-to-end in production.** No model credentials
  are configured here, so the deployed page will show the explicit
  "not configured" state until an operator sets the variables above.
- TradingView availability depends on the user's network/CSP and is outside
  AlphaOS's control; the widget is visual only.
- The web app has no user authentication layer, so the assistant endpoint is
  protected only by same-origin enforcement and an in-process rate limit.
- Historical analysis is limited to the archive evidence the backend already
  exposes; the page does not enable historical replay or candle series.
- Point-in-time evidence can be old; the page and assistant always show the
  timestamp and label it as not current.
