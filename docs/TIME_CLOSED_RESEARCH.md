# Time-closed 5-minute research (draft PR #118)

This feature is **disabled by default**. Set `ALPHAOS_TIME_CLOSED_RESEARCH=true` on the authenticated backend only to opt in. Do not enable in production until review and measured API latency tests.

The authenticated `GET /research/trade-intelligence/{symbol}` route (SPY/QQQ) performs **two uncached authorized Public 5-minute candle fetches** when enabled. Both snapshots must agree on the eligible regular-session prefix and pass source, freshness, entitlement, ordering, OHLCV and time checks. A bar is eligible only after its interval end plus five seconds. An open tail is excluded. If any required bar is missing or revised, the projection fails closed.

The existing `data`, `levels`, `state`, `setups`, and `exit_early` fields are unchanged and remain gated on **explicit provider finality**. A separate `provisional_research` object contains `evidence`, `reason`, `actionable=false`, `bar_count`, `latest_bar_at`, `opening_range`, `vwap`, `ema9`, `directional_context`, and a warning. These are **not verified BUY/SELL signals** and cannot authorize trading. Public does not attest that time-closed bars are immutable; two matching fetches do not prove finality.

The route currently has a three-second total budget, including daily research. Two extra provider requests can exhaust that budget and cause a 504; the default-off flag avoids changing live behavior. Before enabling in production, benchmark latency, provider rate limits, owner-only display permissions, DST/holidays, partial sessions, gaps, revisions and concurrency. Do not publish these private Public-derived values in a public website. Netlify auto-build remains disabled.

Security issue #119 separately tracks the unpatched picomatch development dependency. Full npm audit remains a blocking CI gate.
