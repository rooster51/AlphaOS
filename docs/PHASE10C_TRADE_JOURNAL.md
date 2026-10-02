# Phase 10C — Trade Journal & Performance Analytics

## Purpose and release baseline

Review the user's recorded history without ranking setups, recommending trades,
executing orders, or treating historical frequencies as calibrated probabilities.
Entry evidence, monitoring observations and declared outcomes are separate layers.

Branch `phase10c-trade-journal` starts at the audited Phase 10B release candidate
`3e9455c8ba700b6f2359bad0041650ad6cd5de3f`, based on
`fff856b36c41b45806fe4bc12deccdc6d0a31d24`. Stage 1 verified PR #10, the 19-tool
surface, local-only mutations, consent disclosure, configurable SQLite storage and
absence of abandoned Phase 10A functionality. Fixed one garbled DTE dash and added
`docs/PHASE10B_RELEASE_CHECKLIST.md`. Focused release tests: 94 passed; full baseline:
486 passed + 40 subtests. Baseline GitHub CI run 37028644287 succeeded.
PR #9 remains unmerged. This is a release baseline, not a deployed production claim.

## Architecture and additive schema

`alphaos_api/positions.py` remains authoritative for identity, immutable entry,
monitoring and explicit closure. `alphaos_api/journal.py` reads the same database and
computes journal metrics; it makes no provider/research calls. UI helpers live in
`modules/trade_journal_workspace.py`, reached from the existing Active Trades page.

Existing `positions` columns and stored entry/closure JSON are not migrated or rewritten.
Opening the store idempotently creates one additional table:

| Field | Meaning |
| --- | --- |
| sequence | SQLite insertion sequence, tie-breaker for observations |
| event_id | Unique UUID |
| position_id | Foreign key to existing position ID |
| kind | `monitor` or `close` |
| observed_at | Observation capture time, or user-declared close time |
| recorded_at | Server recording time |
| payload_json | Current snapshot + descriptor, or explicit closure evidence |

An index supports position timelines. SQLite triggers reject UPDATE/DELETE on events;
application connections enforce foreign keys. Entry JSON retains its original insert-only
application path. No old monitoring events, entry events, or closure events are backfilled.
Legacy closed trades remain analytically available from their existing explicit closure.

Each successful monitor refresh appends its current snapshot and descriptor, excluding
the duplicated frozen research body. A transaction checks that the position remains
active; if closure won the race, monitoring returns 409 instead of inserting a post-close
event. Closing a position updates the existing close slot and inserts its close event in
one transaction. Identical closure retries add no events; conflicting closure still fails.
Failure to persist a required event fails the operation rather than pretending it was saved.
Journal/review reads use a single SQLite read transaction, so concurrent closure cannot
mix a pre-close position with a post-close event timeline in the same response.

Monitoring remains a read-only market operation with internal observation logging;
each refresh can produce a new sampled event. The three journal tools are read-only
database analytics and do not append events. Existing record/close mutation annotations
remain explicit. OAuth protocol, scope/security behavior and quant engines are unchanged.

## Evidence separation and compatibility

* **Entry:** original position and `entry_snapshot` are never recomputed or rewritten.
  New entries additionally capture the already-produced completed-session EMA structure
  and research-session date. Regime/VWAP remain null because the current workflow does
  not capture them. Existing records are not retroactively labeled. Captured context is
  dated at recording, not reconstructed at a backdated execution time.
* **Monitoring:** append-only raw snapshots preserve timestamp, underlying, quote estimates,
  optional Greeks, distances, descriptor, quote-quality limitations and structure context.
  Each row is a sampled request, not an independent market tick.
* **Outcome:** only explicit closure input sets outcome evidence. No mark is automatically
  promoted to a fill; no expiry/missing quote closes a position.

New optional close fields: `exit_basis` (`actual`, default; `estimated`; `unknown`),
`exit_reason` and `user_note` (max 2000 characters). `amount` is required for actual and
estimated exits; it must be omitted/null for unknown exits. Cashflow remains debit/credit,
and timestamp remains timezone-aware. Default legacy actual-close requests preserve their
response shape and retry equivalence, including against pre-migration records.

Exit reason values: `profit_target`, `risk_management`, `short_strike_pressure`,
`breakeven_pressure`, `thesis_changed`, `expiration`, `manual_discretionary`, `other`.
Reasons are optional user declarations, never inferred from state or P/L.

For actual fills, the existing `declared_pl` is realized gross P/L. Estimated exits have
`declared_pl=null`, explicit `exit_basis=estimated` and `estimated_pl`. Unknown exits
have no amount or P/L. Legacy 10B closure required an explicit amount and is treated as
actual user-declared evidence, not broker verification. Initial version does not support
editing a closed fill, later filling in an unknown exit, partial closes or reopening;
conflicts fail instead of rewriting history. Entry quantity applies to the whole closure.

## Metrics and sample sizes

Actual realized P/L = (entry credit − signed close debit) × multiplier × quantity.
Credit closure means negative signed debit. Fees/commissions are not included.
Per-spread result divides by known quantity; unknown quantity produces null, not one.
Percent max profit captured divides actual P/L by entry max profit; percent defined risk
realized divides by entry max loss. Positive risk percentage is profit, negative is loss.
Holding duration uses declared entry/closure timestamps. Entry calendar DTE and time
buckets use America/New_York, not UTC dates or observed-session research horizons.

Time buckets: 09:30–10:30, 10:30–14:00, 14:00–16:00, outside those hours (New York).
They are descriptive clock buckets, not a new session/calendar or intraday engine.

**Realized Expectancy Per Recorded Trade** is arithmetic mean actual recorded P/L.
It is completely separate from Phase 5 **Historical Scenario EV**, which remains in
frozen research only. Win rate is positive actual outcomes divided by all actual outcomes,
including flats. Payoff ratio = average winner / absolute average loser; unavailable
without both winners and losers. No infinite ratios or zero-valued missing metrics.

Each aggregate metric supplies its denominator `n`. Summary also returns `n_closed`,
`n_realized`, `n_estimated`, `n_missing_actual`, wins/losses/flats, cumulative/mean/median
actual P/L, average winner/loser, payoff ratio, expectancy, mean/median hold time,
average entry credit and average max-profit capture. Actual-only metrics exclude all
estimated and missing fills. Holding/credit summaries use available closed-trade values.
Fewer than 30 actual outcomes receives a visible small-sample flag; 30 is not a claim
of statistical adequacy. No confidence/predictive probabilities or independence claims.

Recorded-history metrics include eligible/total observation counts, quality-valid P/L
count, state counts/transitions, last recorded state, observed breaches, best/worst
estimated P/L and recorded MFE/MAE. Eligible observations lie within the declared holding
period; backdated closure can exclude previously stored later observations, which remain
visible in the audit timeline. Missing assessments break transition chains.

MFE is the positive component of best valid recorded P/L; MAE is the negative component
of worst valid recorded P/L. No valid samples means null. These are **recorded monitoring
observations**, not continuous/tick-level excursions. Stale/invalid valuations are excluded.
Fresh underlying boundaries may remain observable even when option valuations are not.
Breach frequencies use trades with usable boundary observations as denominator; pressure
frequency uses trades with recorded states. No observations means unknown, never false.
Repeated events are not treated as independent evidence or as additional trades.

The recorded-50%-capture summary conditions on at least one valid sampled estimate ≥50%
of entry max profit and an actual close result. It reports signed best recorded estimate
minus realized result and its sample size. Negative differences are retained. This compares
estimates to actual declared outcomes and does not establish continuous profit giveback or
that holding longer caused the result. Full timelines allow inspection of later observations.

## REST/MCP interfaces

Existing 19 tools remain; three read-only tools bring the total to **22**:

| MCP tool | REST route | Inputs |
| --- | --- | --- |
| `get_trade_journal` | GET `/v1/journal` | filters, limit (1–100, default 20), offset (default 0) |
| `get_trade_review` | GET `/v1/journal/{position_id}` | position UUID, event_limit (1–500, default 100), event_offset |
| `get_trade_performance` | GET `/v1/journal/performance` | filters, optional group_by |

MCP accepts a `filters` object; REST uses its flattened query parameters. Supported:
symbol, PCS/CCS strategy, expiration, dte_min/max, date_from/to, date_basis (close default
or entry), entry_regime, entry_structure, exit_reason, monitor_state, short_breached,
breakeven_breached and exit_basis. Date endpoints are inclusive New York dates.
Unknown context filters return no matches rather than derive a missing regime/VWAP.
Entry structure filter means captured completed-session EMA category, not a fabricated
execution-time label; raw price levels remain in frozen entry evidence.

Group by symbol, strategy, entry_dte, dte_bucket (0DTE/1DTE+), entry_time_bucket,
hold_bucket, exit_reason, entry_regime, entry_structure, last_monitor_state or
recorded_short_breach. Unknown groups have null values. Group order is alphabetical
label order, never a performance ranking. Monitor-state filtering matches any recorded
eligible state; last_monitor_state grouping uses the last available eligible descriptor.

Schema version: `alphaos-journal-v1`. Journal returns total matched closed count,
newest-first trades, offset/limit/next_offset and caveats. Stable position-ID tie-breaker
resolves equal closure times. Offset pagination can shift if new trades close concurrently.
Review returns separate `entry_record`, `monitoring_timeline`, `outcome`, `metrics` and
event pagination. Metrics cover the complete eligible history even when timeline is paged.
Performance returns overall and per-group summaries plus actual-only cumulative series.
Original Phase 9 schemas, snapshots/candidate IDs and position IDs are unchanged.

## Streamlit workflow

Open Active Trades and select **Trade journal / performance**. Filter symbol/strategy/DTE
or expand additional filters; page through completed trades. Click a table row to open
Trade Review with frozen entry research, sampled timeline, explicit outcome, notes,
boundary events and excursion details. Performance shows sample counts, actual P/L,
win rate and realized expectancy, with optional groups. Definitions stay in expanders.
The existing close form now explicitly selects actual/estimated/unavailable evidence,
optional exit reason and note. The same server-side API credentials/storage are reused.

## Persistence, release and smoke testing

Unchanged `ALPHAOS_POSITIONS_DB` requirement: one durable SQLite file on a persistent
Render disk, e.g. `/var/data/alphaos/active-positions.sqlite3`; local default continues
to work without Render. No infrastructure or secrets are changed by this implementation.
Take a consistent SQLite backup before upgrade. The migration creates only event table,
index and triggers; it must preserve exact legacy entry/closure bytes. Rollback to 10B
can still read positions but would stop event recording; keep the database backup/history.
Single-owner/single-instance deployment remains the supported operating model.

After review/approval, release 10B before 10C (or a reviewed combined descendant), run CI
on the intended release SHA and deploy that exact SHA manually. **Do not auto-merge or
auto-deploy.** Stage 1 production checklist still applies, with 22 tools for 10C. Add:

1. Back up database; compare a legacy entry/close before and after upgrade byte-for-byte.
2. Record an explicitly labeled test position and two fresh monitor observations. Verify
   distinct event IDs, dated quality, unchanged entry and a two-observation timeline.
3. Restart the service with the same persistent disk; verify identity/entry/events survive.
4. Explicitly close with actual test fill, reason and note; verify one close event, realized
   math and actual n=1. Retry identically: no duplicate close/event. Retrieve closed record
   and confirm it is absent from the active list.
5. Use separate labeled records for estimated and unknown closure; verify they appear in
   the journal but do not increase realized n or become actual P/L.
6. Test symbol/strategy/DTE/date/history filters, next-page behavior, trade review,
   sample-size disclosures and grouped performance via REST, Streamlit and ChatGPT.
7. Confirm legacy trades have unknown missing histories, not invented zero breaches/MFE;
   stale monitored estimates do not contribute to excursions. Compare full-history metric
   counts against paged timeline totals. Retain test labels; no silent deletion.
8. Verify OAuth metadata/authentication, original research tools and all 22 definitions;
   no brokerage calls, no token exposure and no infrastructure/secret changes.

## Known limitations and validation scope

No continuous intraday path, automatic monitoring, broker fill verification, commissions,
partial closure or outcome edits. No backfilled VWAP/regime/monitor history. Context can
be unavailable. Existing current structure still depends on cached completed history.
Analytics scans local closed records/events in memory; pagination bounds returned rows,
not computation. Event retention is append-only with no automatic purge, so disk usage
and SQLite backups require operational monitoring for large journals. Cumulative series
covers the filtered actual cohort, not the entire account or a cash-adjusted equity curve.

Deterministic tests cover legacy migration/restart, actual/estimated/unknown closure,
quantity/time/economics, sampled MFE/MAE, boundaries/transitions, missing data, cohorts,
pagination, grouping, API/MCP auth compatibility, Streamlit helpers/rendering, append-only
triggers, close-event atomic rollback and no provider calls from analytics.
Focused position/journal/UI checks: 75 passed; the additional concurrent-read snapshot
regression passed (76 focused checks combined). Final complete local regression:
**528 passed, 40 subtests passed**, 247.57 seconds. This adds 42 deterministic tests
to the audited 486-test Phase 10B baseline. GitHub CI status/link is recorded in the draft PR.
Local fixture timings, if reported, are not Render/live-provider latency measurements.
