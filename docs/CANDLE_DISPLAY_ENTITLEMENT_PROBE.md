# Candle display entitlement and private probe

## Status: blocked by provider licensing

The first-party SPY/QQQ candle chart is implemented but **native Public candle
display is disabled by default**. Private-research API permission is not treated
as permission to expose Public market data in the website chart.

Public's **Individual Trader API Program Terms and Conditions (June 2026)**
state:

- **§1(c) Own Use:** access is solely for the Developer's own personal use, and
  the developer may not make the Public Platform or API available through
  third-party software or systems.
- **§5(b) Data:** Account Data and Market Data may be used only through the
  developer's Applications and for purposes authorized by the agreement.
- **§14, final paragraph:** using the API to disseminate Market Data or other
  licensed information to third parties is strictly prohibited without Public's
  prior written approval.

An authenticated AlphaOS website currently has no recorded Public
authorization reference for browser display. Until written approval names that
use, the safe policy remains **deny**. The chart route therefore defaults to the
external TradingView fallback, and the same-origin candle bridge returns:

```json
{"status":"unavailable","code":"feature_disabled"}
```

`ALPHAOS_CANDLE_CHART_ENABLED=true` is not an authorization mechanism. It is a
deployment switch that must remain off unless the written approval is recorded
and reviewed. It does not change Public's data-use policy, and it must not be
used to infer permission from a successful provider request.

## What written approval must cover

Before enabling native display, retain a reviewable authorization that explicitly
covers:

1. Public market data displayed through the authenticated AlphaOS website.
2. The intended users (single account owner versus multiple authenticated users).
3. Whether the use is personal, non-commercial, or commercial.
4. Any caching, retention, export, redistribution, or derived-data rights.
5. The provider attribution and notice requirements.

If the approval is narrower than the intended website behavior, the feature
stays disabled or the website scope must be reduced to match it.

## Private authenticated probe

`scripts/candle_display_probe.py` measures the exact browser-facing path:
website session → authenticated Next.js bridge → AlphaOS API → Public provider.
It is read-only and bounded to SPY/QQQ at `1m`, `5m`, and `15m`, plus one quote
per symbol/interval.

It uses only the signed website session. It never accepts, prints, or stores
`ALPHAOS_API_TOKEN` or any backend bearer token.

### Configuration

Set these only in the private shell running the probe:

```sh
export ALPHAOS_SITE_URL="https://<authorized-alphaos-site>"
export ALPHAOS_WEBSITE_SESSION="<__Host-alphaos_session value>"
```

Do not put the session in source, a committed `.env`, command history, logs, or
the probe output. The probe refuses HTTP except for loopback development.

### Run

```sh
python -m scripts.candle_display_probe \
  --symbols SPY QQQ --intervals 1m 5m 15m
```

An optional `--output` path must be relative and inside the working tree.

### Measurements

For each symbol/interval the JSON report records:

- candle HTTP availability and safe error code;
- `data_age_seconds` from the newest candle timestamp;
- `snapshot_age_seconds` from `retrieved_at`;
- provider, snapshot ID, completeness, warnings, and last-bar state;
- returned/received/expected counts and missing-bar count;
- strictly increasing timestamps, interval alignment, latest-bar match, and
  retrieval-after-latest consistency;
- independent quote status, `ageSeconds`, and quote timestamps;
- `Cache-Control: private, no-store` on the website response.

Exit codes:

- `0`: all six symbol/interval requests are valid and all six quotes are fresh.
- `1`: partial availability, stale quotes, or invalid snapshots.
- `2`: configuration missing, authentication denied, or `feature_disabled`.

The probe intentionally cannot bypass the feature flag. While display is
unauthorized it will report `feature_disabled`; that is the correct gate result,
not a reason to enable the route. It must not be run against production until
the owner has approved a read-only staging check and the written display
authorization is recorded.

## Deployment boundary

- The AlphaOS API currently returns `private_research` entitlement evidence.
  The browser bridge does not convert it into display rights: it requires the
  per-response `use_context` to be `public_display`, an authorization reference
  to be present, and the provider capability to grant `public_display`.
  Otherwise it returns `data_use_denied`.
- The browser never receives the backend token or an unrestricted provider URL.
- The website bridge returns only validated `alphaos-candles-v1` snapshots with
  `private, no-store` and `Vary: Cookie`.
- No public, commercial, redistribution, or AI-analysis use is enabled.
