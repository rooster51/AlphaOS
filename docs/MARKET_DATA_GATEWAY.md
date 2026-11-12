# Provider-independent market-data gateway (Phase A)

This layer separates AlphaOS contracts from the current Public adapter. It is
server-side only and does not add a chart or expose new data to an unauthenticated
client.

## Interface

`modules/market_data_gateway.py` defines a small `MarketDataProvider` protocol:

- `quote(symbol)` returns a normalized last/bid/ask observation with provider,
  quote time, retrieval time, session classification, freshness and warnings.
- `candles(symbol, interval, session, limit)` returns native OHLCV bars for
  `1m`, `5m` or `15m`, with provider expected/received counts and quality flags.

The external contracts live in `modules/market_data_contracts.py`. They contain
no Public SDK objects, account identifiers or provider-specific field names.
`PublicMarketDataProvider` is the first implementation; a licensed feed can
implement the same protocol without changing the API or frontend.

## Initial scope

- Symbols: `SPY`, `QQQ`
- Intervals: `1m`, `5m`, `15m`
- Session: regular only
- Provider-native bars only: no quote-to-candle synthesis, resampling,
  forward filling or gap repair
- The current Public collector is unchanged; its existing 1-minute archive path
  and five-minute schedule continue to operate

## Validation

The gateway rejects provider responses with:

- wrong symbol or aggregation
- non-regular-session timestamps
- non-monotonic or duplicate timestamps
- nonpositive prices, negative volume or invalid high/low relationships
- no usable bars
- unparseable or future timestamps

Public returns a native closing-auction bar stamped exactly at the regular
session close. That final boundary bar is outside the half-open regular-session
range and is excluded with `provider_closing_bar_excluded`; any other
out-of-session bar still fails closed. No bar is fabricated or repaired.

Missing internal bars are reported as warnings, not filled. When the provider
supplies an expected count, a completed session is `complete` or `incomplete`.
A session that is still open has `completeness: unknown` and a
`session_in_progress` warning: a full-session expected count is not a failure
while bars are still accumulating. A narrowed `limit` changes `returned_bars`,
not `received_bars` or completeness. Provider-skipped rows add
`provider_incomplete_bars_skipped` and make a completed session incomplete.

Validation failures carry stable, payload-free codes. Provider retrieval codes
include `provider_bars_authentication_failed`, `provider_bars_rate_limited`,
`provider_bars_timeout`, `provider_bars_fetch_failed`, the `provider_bars_*`
response-shape codes and timestamp-shape codes. Gateway codes include
`candle_symbol_mismatch`, `candle_aggregation_mismatch`, `candle_timestamp_*`,
`candle_outside_regular_session`, `candle_interval_misaligned`,
`candle_timestamp_out_of_order`, `duplicate_candle_timestamp`,
`candle_ohlc_*`, `candle_expected_bars_conflict` and
`provider_closing_bar_excluded`. These codes never include credentials, headers,
account identifiers or raw provider payloads.

The newest bar is never called complete or partial merely because it is the last
bar returned or because the local clock says its interval is open.
`last_bar_status` is `complete` or `partial` only when the provider supplied
explicit completion evidence; otherwise it is `unknown` with
`last_bar_completion_unverified`. An open interval is reported separately as
`last_bar_window_open`.

## Data-use policy

`modules/data_entitlements.py` defaults to deny. The registered Public entitlement
allows authenticated private research and the separate `owner_private_display`
context for a single-owner Application. It does not grant:

- public display
- commercial use
- redistribution
- access by other users
- AI analysis

Public's Individual API is documented for personal, non-commercial use and says
third-party dissemination requires prior written approval. The owner-private
context is not relabelled as public display; it is available only through the
server-side owner session boundary. The policy therefore also blocks Public data
from future public exports, other-user access and AI evidence paths until a
documented authorization is added. The archive write path validates the provider
identity on every row and rejects a mixed-provider batch before touching
Supabase; a single provider batch is then checked against its entitlement. A
future licensed feed must be registered with its documented basis and
authorization reference; it must not inherit Public's permissions by name or by
cache reuse.

## Read-only probe

With existing Public credentials configured, run a bounded sample during a
regular session:

```bash
python -m scripts.market_data_probe --symbols SPY QQQ --intervals 1m 5m 15m --samples 1
```

The probe bypasses the API cache, makes one quote and one native-bar request per
symbol/interval, and reports request latency, newest candle time, quote-to-candle
lag, expected/received counts, completeness, partial status, freshness, warning
codes and safe provider errors. It does not intentionally trigger rate limits,
write archives or alter credentials. Without `PUBLIC_API_SECRET` it reports
`public_not_configured` and does not invent latency measurements.

## Boundaries

This phase intentionally does not add a candle endpoint, cache, frontend chart
or Gemini context. Those belong in the dependent Phase B PR and later phases.
