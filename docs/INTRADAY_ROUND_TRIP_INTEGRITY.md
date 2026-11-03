# Intraday round-trip session integrity

Continuation of `research/verified-intraday-round-trip-v1`, reusing its existing
multi-leg bid/ask cashflow evaluator. Entry buys at ask/sells at bid; exit reverses
those sides and deducts configured per-contract per-side fees. These remain
hypothetical conservative quotes, not actual fills or calibrated POP/EV.

Added fail-closed NYSE checks for weekends, holidays, early closes, extended hours,
and cross-session round trips; quote rows must lie within their snapshot collection
and same regular session. Insert time cannot precede collection completion. Both
bid and ask timestamps must advance, preventing one frozen side from being hidden
by the other. Expiration checks use America/New_York dates.

No API/storage integration is enabled. Live Supabase metadata columns match the
reader envelope, and metadata shows 312 SPY and 312 QQQ complete snapshots over
October 5-9. Compressed-object payload verification could not be performed with
available local configuration. Current tests are explicitly synthetic. A checksum
string supplied by a caller is NOT proof of storage verification; the preexisting
caller-verification requirement remains. Verify at least one real object through
the existing checksum reader before wiring a trusted storage entry point.

Profit targets, stops, time exits and observed MFE/MAE require a verified ordered
series and an entry policy fixed before future observations are accessed. Five-minute
snapshots cannot establish intrabar touches or executable fills. Those additions
remain deferred until payload and quote-timestamp availability are verified.
