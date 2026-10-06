# Read-only archive research contract

The collector and scheduler on main own collection/persistence. AlphaOS 2.0 reads
that same intraday-archive-v1 / options-archive-v1 payload without changing it.

## Supplied snapshot (deterministic historical research)

`run_market(payload, expiration=..., history=..., available_capital=...)` validates
archive identity and original timestamps, resolves the observation's NYSE session
using `market_session_gate.regular_session_bounds`, builds completed-history
features, classifies, routes, constructs, researches, filters capital eligibility
and compares without ranking. Its `as_of` is the original collection start, not a
new live quote. Optional supplied session bounds must match the archive calendar.

## Latest persisted snapshot (read-only I/O boundary)

```python
from functools import partial
from modules.supabase_archive import read_latest_option_snapshot
from modules.run_market import run_latest_market

# client is injected by trusted application infrastructure, not constructed by
# the research engine. freshness_seconds is an explicit caller policy.
reader = partial(read_latest_option_snapshot, client,
                 max_age_seconds=freshness_seconds)
result = run_latest_market('QQQ', as_of=request_timestamp,
                           read_snapshot=reader,
                           history=completed_daily_ohlc,
                           available_capital=200)
```

The existing Supabase module queries option_snapshots at/before the request time,
orders by observation timestamp then id, and reads the matching private archive
object. It verifies SHA-256, provider/symbol/session/observation/slot identity,
quality and availability. Missing, stale or inconsistent evidence fails closed;
there is no direct Public fallback, archive repair or write. A partial latest
snapshot remains visibly partial rather than being replaced with older evidence.

`requested_as_of` is separate from archive `as_of`, `slot_time`, collection finish,
per-chain response times and provider quote timestamps. Freshness age is measured
conservatively from collection start. No quote timestamp is invented when only
collection time exists. Requested-expiration failures cannot supply candidates.
Rejected contracts remain excluded; questionable contracts retain quality warnings
and still must pass existing research quote validation.

History remains supplied/injected using existing completed-daily research helpers;
current/future sessions are excluded. No daily bars are manufactured from partial
minute archives. Missing history leaves direction unknown. Same-day economics use
zero years, not artificial time or fabricated POP. AlphaOS construction explicitly
passes min_net_credit=0; legacy premium callers retain their existing default.

The read path does not call a broker, write the journal, apply the ledger SQL,
change OAuth, or introduce API/MCP endpoints. Client authorization and production
interface wiring are separate work. Live storage integration is fixture-tested,
not credential-verified in this pass.
