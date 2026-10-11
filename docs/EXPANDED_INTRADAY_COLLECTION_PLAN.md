# Expanded intraday archive: NVDA and IWM (proposal)

Status: **opt-in collector wiring implemented for review; not enabled in production**. Original rollout plan from PR #30 is retained below. No production configuration or Supabase schema is changed.

## Baseline

SPY and QQQ collection remains unchanged. On 2026-10-10 Supabase contained 312 complete option snapshots per symbol over five sessions and 2,230/2,233 one-minute bars respectively. New symbols have no verified archive coverage yet.

## First rollout

1. Add NVDA and IWM to a separately versioned, opt-in collection configuration. Do not silently broaden the frozen daily-quant research defaults.
2. Refactor explicit SPY/QQQ guards in `modules/options_archive.py`, `modules/daily_quant.py`, archive readers, and related tests to use an audited allowlist. Confirm Public provider supports both equity chains and contract identifiers before enabling.
3. Validate quote timestamps, bid/ask quality, expiration availability, per-symbol contract counts, rate limits, collection runtime, storage footprint, and complete/partial status. Keep provenance and immutable storage guarantees.
4. Start with a bounded canary; monitor two full sessions and compare missed slots, request failures, quote staleness and storage use to SPY/QQQ. Roll back only the new-symbol schedule on failure.
5. Enable regular five-minute intraday snapshots after checks pass; maintain distinct, slower long-dated sampling for monthly/LEAPS research. Do not claim calibrated POP or intraday EV from a short sample.

## Explicit non-goals

No live order routing, provider secret changes, schema migration, production deployment, new symbol research eligibility, or website work in this PR. AAPL/TSLA and later symbols require separate evidence-based expansion.

## Acceptance tests

- Existing SPY/QQQ output and tests unchanged.
- NVDA/IWM mock contracts accepted with valid OSI roots; mismatched roots and stale/missing quotes fail closed.
- Provider failures produce partial/failed status, never fabricated chains.
- Repeated collection slot is idempotent and immutable.
- Research endpoints reject new symbols until their read paths are explicitly validated.
- Collection budgets and timeouts tested before scheduling.

## Collector wiring increment (not deployed)

`ALPHAOS_INTRADAY_CANARY=NVDA` or `IWM` explicitly opts one extra equity into
`scripts/run_intraday_snapshot.py`; unset/empty/none preserves SPY then QQQ.
Invalid/multiple symbols fail before authentication. Core symbols run first.
The existing daily research universe and archive research API remain SPY/QQQ.
No scheduler, environment setting or provider entitlement has been changed.

The existing archive constructor accepts only the selected canary and validates
Public EQUITY identity and OSI option roots/terms using its existing normalization.
Canary underlying quotes must pass the shared live freshness gate before strike
selection. Raw option quality/missing timestamps remain archived with their existing
flags; completeness is not an executable-price claim. Default SPY/QQQ payload
shape remains unchanged. Candle/snapshot writes use existing idempotent persistence.

Each symbol performs one bars request, two underlying requests (existing design),
one expiration-list request, and one chain request per selected expiration. A retry
can double these; the runner retains two attempts and ten-second backoff, serial
processing, current-slot/session gates and partial/empty failure reporting. No
provider rate quota is guessed. Canary approval requires observed rate-limit,
runtime and missing-slot measurements before changing production configuration.

Live read-only metadata on 2026-10-10 confirms 312 complete snapshots each for SPY
and QQQ (October 5-9); no canary coverage exists. Provider transport compatibility
is fixture-tested, not a claim of live NVDA/IWM entitlement. Remove the optional
canary setting to roll back collection scope; never delete old immutable archives.
