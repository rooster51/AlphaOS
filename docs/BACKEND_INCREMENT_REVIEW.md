# Backend increment audit — 2026-10-10

Baseline main: 7f7ef53 (owner-reported production baseline; no deployment performed).
PR #29 head b9c4f3be36e929e0052b1d118093d84243bde9e4 passed the full local
suite: 725 tests + 40 subtests, and GitHub run 38065194323 passed. The additional
three tests preserve authenticated POST JSON /v1/research/market. GET currently
returns 404 through existing route matching; missing token is 401, invalid is 403.
Website PR #28 assumes GET and is therefore incompatible; no backend compatibility
alias or frontend change was added. PRs #19/#26 still have documented fixture and
trust-boundary review gates. Website integration remains paused.

PR #30 helper/config tests are reused rather than rewritten. The new collector
wiring leaves production settings and SPY/QQQ defaults unchanged. Live Supabase
metadata inspection was SELECT-only. No raw history was committed to Git.

The existing intraday branch is reused in a separate session-integrity increment;
its checksum claim remains explicitly caller-verified until an actual immutable
object has been read through the verified reader. Available connectors expose DB
metadata, not private object bytes, and supported local credentials were absent.
No calibrated POP/EV, optimized stops or continuous-path claims are introduced.

PR #11 implements an older persistent SQLite journal with declared actual versus
estimated/unknown outcomes and append-only events. It is not the current Supabase
owner-scoped ledger and cannot be merged wholesale. PR #18 contains isolated
identity, Supabase verification and linking/tenancy foundations but no trusted
MCP-to-ledger authorization route. Shared API credentials and literal OAuth owner
remain insufficient to authorize journal writes. Existing ledger SQL is not applied.
Journal integration needs approved enrollment/configuration and verified ownership
propagation; no fictional positions or production writes were created.

The router already names calendars, diagonals, long straddles and strangles, while
construction/research support is narrower. Existing long/debit/credit/BWB/condor
implementations are retained. A separate explicit long-straddle/strangle increment
uses the existing payoff and trusted historical adapter. Multi-expiration calendars,
diagonals and poor-man's covered structures require a validated multi-expiration
valuation contract. Monthly/LEAPS expirations are not evidence of supported
historical horizons. Capital ceilings remain opt-in only.

Coverage detail from the same read-only audit: each symbol has 78 distinct slots
on October 6, 8 and 9; 74 on October 7 (four fewer than a full 78-slot session).
October 5 has only four snapshots and three distinct non-null slots. A complete
snapshot status does not mean complete session coverage. These gaps must remain
explicit in historical path analysis; no interpolation/backfill was performed.
