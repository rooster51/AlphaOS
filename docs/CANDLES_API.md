# Native Candle API (Phase B)

`GET /v1/candles/{symbol}` is the authenticated, read-only candle surface. It
returns normalized AlphaOS data rather than Public SDK objects.

> **Display gate:** public display, commercial use, redistribution and AI use are
> not authorized. A separate `owner_private_display` entitlement exists only for
> the authenticated repository owner; it is not public display. The website
> bridge and native chart remain disabled by default. See
> [owner-private candle display and probe](CANDLE_DISPLAY_ENTITLEMENT_PROBE.md).

## Request

```text
GET /v1/candles/SPY?interval=1m&session=regular&limit=390
Authorization: Bearer <ALPHAOS_API_TOKEN>
X-AlphaOS-Data-Use: private_research
```

| Parameter | Values | Default | Notes |
| --- | --- | --- | --- |
| `symbol` | `SPY`, `QQQ` | required | Case-insensitive at the service boundary. |
| `interval` | `1m`, `5m`, `15m` | `1m` | Native provider intervals only; no resampling. |
| `session` | `regular` | `regular` | Extended-hours data is not converted into regular-session data. |
| `limit` | 1–390 | `390` | Returns the newest N native bars from the provider response. |
| `X-AlphaOS-Data-Use` | `private_research`, `owner_private_display` | `private_research` | Server-to-server only. The owner website bridge sends `owner_private_display` after verifying the signed owner session. Other values are rejected with `400 invalid_data_use`. |

Authentication uses the existing `/v1` bearer dependency. Every response is
`Cache-Control: no-store` at the HTTP boundary; the server-side snapshot cache is
separate and private to the process.

The website bridge is the only caller that sets `owner_private_display`. It does
so after a server-side owner-role check, and it requires the response decision
and provider capability to confirm that exact context. It never accepts a
`public_display` snapshot.

## Response contract

The response is an `alphaos-candles-v1` snapshot:

- `symbol`, `interval`, `provider`, `session`
- `retrieved_at`, `latest_candle_at`, `snapshot_id`
- `expected_bars`, `received_bars`, `returned_bars`
- `completeness`: `complete`, `incomplete`, or `unknown`
- `last_bar_status`: `complete`, `partial`, or `unknown`
- `freshness`: `fresh`, `stale`, `latest_available`, or `unknown`
- `warnings`: explicit quality/gap/session notices
- `candles`: native OHLCV rows with ISO-8601 UTC timestamps
- `provider_capabilities` and `entitlement`: provenance and policy decisions

`last_bar_status` is derived only from provider completion evidence. The local
clock does not turn an unconfirmed last bar into `partial`; an open interval is
reported separately as `last_bar_window_open`, and absent provider evidence is
reported as `last_bar_completion_unverified` with status `unknown`.

`completeness` describes the whole regular session. While that session is still
open, it is `unknown` with `session_in_progress`, even when the provider's
full-session expected count is larger than the bars received so far. A completed
session is `incomplete` when its validated row count is below the provider's
expected count or when internal gaps/provider-skipped rows are present. A
narrowed `limit` never changes `received_bars` or completeness.

`received_bars` describes the provider response before `limit`; `returned_bars`
describes the bars in this response. A narrowed `limit` does not turn an
incomplete provider session into a complete one.

### Synthetic example

This is contract evidence only, not a live market observation or a latency
measurement.

```json
{
  "schema_version": "alphaos-candles-v1",
  "symbol": "SPY",
  "interval": "1m",
  "provider": "Public",
  "session": "regular",
  "retrieved_at": "2026-10-02T20:00:30+00:00",
  "latest_candle_at": "2026-10-02T19:59:00+00:00",
  "snapshot_id": "4f6d9b9b1e2a7d4a9f0d6c1b8e3a5c7d2f4a6b8c0d1e3f5a7b9c1d2e3f4a5b6c",
  "expected_bars": 390,
  "received_bars": 390,
  "returned_bars": 3,
  "completeness": "complete",
  "last_bar_status": "complete",
  "freshness": "fresh",
  "warnings": [],
  "candles": [
    {
      "time": "2026-10-02T19:57:00+00:00",
      "open": 600.0,
      "high": 601.0,
      "low": 599.5,
      "close": 600.5,
      "volume": 12500.0
    },
    {
      "time": "2026-10-02T19:58:00+00:00",
      "open": 600.5,
      "high": 601.2,
      "low": 600.1,
      "close": 600.9,
      "volume": 9800.0
    },
    {
      "time": "2026-10-02T19:59:00+00:00",
      "open": 600.9,
      "high": 601.4,
      "low": 600.4,
      "close": 601.1,
      "volume": 11200.0
    }
  ],
  "provider_capabilities": {
    "provider": "Public",
    "symbols": ["SPY", "QQQ"],
    "intervals": ["1m", "5m", "15m"],
    "sessions": ["regular"],
    "latest_quotes": true,
    "native_candles": true,
    "provider_native_intervals": true,
    "expected_bar_metadata": true,
    "entitlement": {
      "provider": "Public",
      "private_research": true,
      "owner_private_display": true,
      "public_display": false,
      "commercial_use": false,
      "redistribution": false,
      "ai_analysis": false,
      "basis": "Public Individual API terms: personal, non-commercial use; dissemination of market data to third parties requires prior written approval.",
      "authorization_reference": null
    }
  },
  "entitlement": {
    "provider": "Public",
    "use_context": "private_research",
    "allowed": true,
    "code": "allowed",
    "reason": "Public permits private_research under the recorded policy.",
    "basis": "Public Individual API terms: personal, non-commercial use; dissemination of market data to third parties requires prior written approval.",
    "policy_version": "alphaos-data-use-v1",
    "authorization_required": false,
    "authorization_reference_present": false
  }
}
```

## Cache

`CandleService` keeps a bounded in-process cache (default TTL **20 seconds**,
bounded to 15–30 seconds; 16 entries). A hit returns the same snapshot ID and
retrieval timestamp, so a client can distinguish a cached observation from a new
provider retrieval. Entitlement is re-checked on every read; a snapshot cached
for private research can never be served as public display. Cache entries are
keyed by provider, normalized symbol, interval, session, and limit. There is no
cross-process or persistent candle cache.

## Failure states

| HTTP | Code examples | Meaning |
| --- | --- | --- |
| 400 | `unsupported_symbol`, `invalid_data_use` | Symbol or requested data-use context is outside the v1 surface. |
| 401/403 | `authentication_required`, `forbidden`, `data_use_denied` | Authentication or policy failure. |
| 422 | `invalid_request` | Query validation failure for `interval`, `session`, or `limit`. |
| 429 | `public_rate_limit` | Provider throttling; do not retry aggressively. |
| 503 | `public_not_configured`, `provider_unavailable`, `no_candles`, `invalid_provider_response` | Provider is unavailable or returned unusable data. |
| 504 | `provider_timeout` | Provider timed out. |

Stale and incomplete data are successful snapshots with `freshness`,
`completeness`, `last_bar_status`, and `warnings` populated. They are not
silently repaired.

## Archive schema review

`public.market_candles` currently stores provider, symbol, aggregation, bar time,
OHLCV, and retrieval time. The additive migration
`supabase/migrations/202611100001_market_candles_quality.sql` adds nullable
`session`, `is_partial`, `expected_bars`, `received_bars`, and `completeness`
columns plus a session lookup index. It does **not** rewrite historical rows or
backfill synthetic metadata; NULL means unknown/legacy. Existing collectors keep
writing the existing columns unchanged. A later collector change can populate the
new metadata after the migration is reviewed and applied.

The archive write boundary validates every row's provider before any Supabase
call and rejects mixed-provider batches. A batch therefore cannot use one
provider's entitlement to persist another provider's observations.

## Deliberate non-goals

No quote-to-candle synthesis, gap filling, extended-hours relabeling, provider
resampling, public display, commercial redistribution, or AI evidence path is
implemented here. Public observations remain private research or the separate
owner-private display path; neither is public display. See
`docs/PHASE_C_CHART_SPEC.md` and `docs/PHASE_D_GEMINI_CONTRACT.md` for the
separate frontend and assistant contracts.
