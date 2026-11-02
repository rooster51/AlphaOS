# Intraday options paper validation — phase 1 (2026-11-02)

Status: internal deterministic simulation primitive; no routes, deployment,
orders, database writes, or demonstrated trading edge. Baseline: main 0c2a4b3.

## Existing infrastructure and scope

- `premium_engine.py`: 15 income strategies and exact signed-leg expiration
  payoff extrema. Reused for maximum loss; no model-derived option pricing.
- `options_archive.py`, `intraday_archive.py`, `supabase/market_archive.sql`:
  provider observations, contract identities, separate market/collection times,
  quality flags and immutable archive references. Collection time is not quote time.
- `alphaos_api/app.py`, `phase9_routes.py`: existing research endpoints; unchanged.
- `historical_economics.py`, `trusted_historical_adapter.py`: descriptive terminal
  scenarios, not intraday option executions. Remain separate.
- `alphaos2_trade_ledger.md` and SQL: proposed journal foundation, not a deployed
  paper execution service. `STATUS.md` and `RELEASE2_READINESS_AUDIT.md` record
  broader unresolved readiness; this primitive does not resolve those milestones.

## Contract

`Strategy(symbol, family, expiration, legs, shares=0)` accepts signed whole leg
quantities with OSI identifiers, Call/Put types and strikes, one expiration.
The interface is independent of family names: long calls/puts, debit/credit
verticals, butterflies (including broken wings), iron butterflies, condors and
ratio structures use the same exact payoff calculation. Existing stock-backed
families return explicit no-trade; unlimited loss or insufficient capital also
returns no-trade. A family label never substitutes for checking actual legs.
No new strategy discovery, scanners or family routing are introduced.

`simulate(strategy, frames, mode=..., policy=Policy())` replays one proposed
position. First frame is the requested entry; subsequent frames must be strictly
chronological. Each frame has an aware `at` and `quotes` array keyed by contract.
Each quote requires bid, ask, bid/ask timestamps, observed_at, bid/ask size in
contracts, SUCCESS outcome, no rejection reasons, source, source_ref and
`evidence_kind`. Reference identifiers must point to evidence verified by the
caller. These strings are not cryptographic authentication. Do not expose this
function directly to untrusted public requests as verified historical evidence.

Both market-side timestamps and collection timestamps must be same-session,
nonfuture and at most 30 seconds old by default. Positive uncrossed quotes,
maximum $0.10 quoted spread, and sufficient displayed size on the traded side
are required. Size is mandatory: current normalized archives may lack it and
must then produce no-trade. Never fill missing timestamps/size with defaults.

Execution is a **simulation conditional on displayed liquidity**, not proof an
order executed: buy at ask plus adverse slippage, sell at bid minus slippage.
Default slippage is $0.01/share/contract/side and fees $0.65/contract/side.
Entry, closing and liquidation marks retain the complete supporting quote rows.
Policy is frozen into the result. There are no underlying-candle option prices,
midpoint fills, interpolated observations or inferred settlement fills.

Default paper capital is $100 for this single position. Credit eligibility
requires at least $20 after both-side fees and closing slippage reserve, at most
$80 defined expiration loss including those costs. Debit outlay including both
fees and reserve is at most $50. All positions must fit available capital.
Maximum loss is a terminal payoff bound with modeled costs, not a guarantee
against assignment, liquidation failures or larger actual execution costs.

Profit target ($10) and stop loss ($20) use net liquidation P&L for the entire
position and are configurable. Trigger exits occur at the first eligible sampled
quote, not an interpolated threshold crossing. NYSE calendar controls holidays
and early closes. Mandatory exit begins five minutes before actual close; the
first fillable frame from then until (strictly before) close closes the position.
No overnight carry or fabricated forced exit is allowed. Missing closing data
leaves P&L unknown. Historical status is no_trade with attempted entry retained;
forward status is unresolved_exposure requiring operator action. These are
failed validation runs, not evidence that a real exposure vanished.

## Evidence modes and summaries

- historical_backtest: observed option quotes with historical timestamps.
- forward_paper: observed option quotes processed as paper simulations; this
  replay function does not authenticate that invocation happened in real time.
- scenario_analysis: explicitly synthetic option quote assumptions.
- hypothetical_example: synthetic instructional fixtures.

Historical/forward modes require `observed_option_quote`; scenario/example modes
require `synthetic_option_quote`. Synthetic fixtures must never be relabeled as
observations. All modes remain simulations; none asserts actual broker fills.

`summarize` separates mode, family and symbol. Net P&L, expectancy, win rate,
average winner/loser, realized-equity drawdown, profit factor and closed sample
size use closed trades only. Breakeven trades count in N and not in wins/losses.
Undefined averages/ratios are null (including no losing trades). Unresolved
attempted entries suppress group performance to prevent favorable selection by
silently dropping missing exits. No-trade and unresolved counts are explicit.
Drawdown is chronological realized equity, not portfolio intraday drawdown.

## Evidence coverage, limitations and next PR

Unit fixtures exercise risk/cost boundaries, missing/stale/future quotes, missing
legs, size, forced/early closing, target/stop exits, multi-leg structures, mode
separation and metrics. They establish mechanics only. No independent historical
quote dataset or historical fills were introduced or verified. No intraday edge
has been validated.

This phase evaluates one position per invocation; it does not manage a portfolio,
reuse realized capital, reserve concurrent risk, monitor a live position, persist
an event ledger, or model partial fills, atomic spread execution, assignment,
exercise, queue priority or market impact. Same-day closing is a required validated
outcome, not an execution guarantee. Sparse quotes can miss intraday stop events.

Next small PR: a read-only trusted archive adapter with source/checksum and
contract verification, displayed-size coverage diagnostics, and a replay report
that includes all attempted entries and unresolved exits. First audit actual
SPY/QQQ quote coverage; absent fields must remain no-trade. Portfolio scheduling
and persistent forward monitoring follow only after that evidence boundary.
