# Phase 10A capability gate

Baseline: 4ef8d5bb1487af1612d8be33cf53f2b2c3be7124, tested Phase 9 index support, deployed and pinned on Render; not merged.

## Confirmed chain-quality defect

October 1 production evidence includes bid timestamps of 2015-01-01T05:00:00Z on distant SPXW261001C09600000, SPXW261001C10000000 and XSP261001C00814000/816/817/818 contracts. Existing chain_quality.timing takes the oldest timestamp across all contracts; this produces roughly 370 million seconds despite fresh selected legs. The calculation reflects returned old values; the defect is ambiguous aggregation scope, not a timezone or epoch conversion error. Whether Public uses this 2015 date as a sentinel is unverified, so it is retained, never silently replaced or clamped.

The fix adds explicit entire-chain newest/oldest observation timestamps and ages, retrieval/evaluation times, fresh coverage counts/percentage and missing/future counts. It reports consumed-contract quality independently on vertical and scan evidence, using both bid and ask timestamps and the existing 900-second option warning policy. Chain coverage is informational, not an all-chain eligibility gate. Cache hits recompute age. The option timestamp parser now delegates to the existing shared epoch-seconds/milliseconds normalizer; this was a separate deterministic compatibility issue, not the cause of the observed 2015 values.

## Intraday gate

Public documentation exposes aggregation overrides and DAY/WEEK session toggles:
https://public.com/api/docs/resources/market-data/get-bars-v2-with-aggregation

A read-only runner audit tests actual returned intervals, depth, sessions, timestamps, missing/duplicate observations and volume for SPY/QQQ EQUITY and XSP/SPX INDEX. Requested aggregations alone are not capability evidence. Adjustments and bar start/end conventions must not be inferred solely from enum names. No intraday model may use daily bars as fabricated paths. Production stays pinned to Phase 9 while this gate is unresolved.
