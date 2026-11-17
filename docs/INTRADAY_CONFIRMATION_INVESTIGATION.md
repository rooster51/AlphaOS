# November 17 intraday confirmation investigation

Production baseline: `53278420`. Fresh reproduction at 2026-11-17 16:52:57 UTC
(11:52:57 ET), not a recording of the reported 11:50 ET observation.

## Source and observations

Current-session trade intelligence uses CandleService / PublicMarketDataProvider,
native 5m candles. Public's DAY request uses FIVE_MINUTES aggregation and
`regular_market.bars`; it does not retrieve an intraday archive. Prior-session
OHLC/pivots use separate daily research evidence.

The adapter normalizes UTC timestamps; the gateway validates interval alignment,
ordering, duplicates and session boundaries. The established off-grid-tail rule
excludes an extra live observation while retaining the contiguous interval grid.

Authenticated production SPY and QQQ candle requests returned HTTP 200 with
29 accepted/returned bars each, 14:30 through 16:50 UTC, freshness `fresh`,
completeness and last-bar status `unknown`, and `provider_live_tail_excluded`.
Authorized independent Public probe [44130814843](https://github.com/rooster51/AlphaOS/actions/runs/44130814843)
at 16:53:29-30 UTC likewise retained 29 bars each. The exclusion rule implies
one extra raw observation; the revised probe reports raw count directly.

SPY trade intelligence returned HTTP 200 in 2.623s, zero confirmed bars, reason
`provider_live_tail_excluded`. The concurrent QQQ direct request returned HTTP
504 (`trade_intelligence_timeout`) in 3.739s, a separate bounded failure.

## Cause and correction

`confirmed_session` rejected the entire snapshot solely because its extra live
observation had been excluded. Removing that guard alone would rely on later
timestamps to infer historical finality. Public SDK 0.1.17's Bar model and the
published bars contract expose no explicit completion flag. Public candles
therefore remain unverified; this change does not manufacture confirmation.

Retained bars now require explicit provider completion evidence and a closed
interval. Only a contiguous confirmed session prefix feeds opening range, VWAP
and EMA 9. Internal completion evidence is bound into the snapshot hash but
excluded from the candle HTTP payload. Public does not populate this evidence.
Trade intelligence reports sanitized raw/accepted/returned/session/elapsed/
confirmed counts and a missing-finality reason. Elapsed counts are diagnostics
only; unverified evidence still requires WAIT.

Traditional S1/S2 labels remain pivot references with above/below spot labels.
Levels on the wrong side of spot are excluded from nearby downside support,
upside resistance and workspace question answers.

## Verification and remaining evidence

SPY/QQQ fixtures with explicit completion evidence show ten historical bars
populate opening range, VWAP and EMA 9 while the open tail is excluded and
setups remain WAIT. Unknown finality yields zero confirmed bars even after
intervals elapse. Tests cover EST/EDT boundaries and existing strict validation.

Before claiming production restoration, obtain provider-supported finality
(an explicit flag or documented final-history guarantee), verify the adapter
against it, merge/deploy through owner review, and repeat authenticated SPY/QQQ
requests. Check raw/accepted/confirmed counts, session date, features and WAIT
reasons. First-party candle display remains disabled. No archive backfill,
entitlement, timestamp rounding or trading permission changes are included.
