# Expanded intraday archive: NVDA and IWM (proposal)

Status: **planning only**. This branch does not enable collection, change production configuration, or migrate Supabase.

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
