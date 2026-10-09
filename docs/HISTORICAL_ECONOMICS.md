# AlphaOS 3.0A: shared historical economics foundation

Status: bounded first slice, not API-integrated or deployed. This implements the
brief's fallback deliverable: a shared contract and reusable multi-leg scenario
evaluator with tests. It is not completion of universal discovery/economics.

## Inspection and reuse

- `alphaos_api/research2.py` exposes the existing three research interfaces;
  `mcp_server.py` forwards their requests to the same REST layer.
- `run_market.py` normalizes verified archive evidence, classifies opportunities
  and calls `opportunity_session.py`. The latter constructs routed candidates,
  calls position research and filters expiration max risk against capital.
- `position_research.py` dispatches long options and multi-leg structures;
  `structure_research.py` validates supported leg topology and cashflow signs.
- `premium_engine.payoff/analyze` supplies exact piecewise expiration economics.
- `historical_analogs.py` selects analogs; `market_outcomes.py` supplies session
  outcomes; `option_scenario_ev.py` already evaluates historical terminal returns
  and summarizes vertical economics. Its existing summary function is reused,
  including the 1e-10-dollar zero tolerance. Its legacy contract is unchanged.
- `phase6_sample.py` and `threshold_survival.py` provide maturity/path preparation;
  these should supply the future trusted analog adapter, not another selector.
- `supabase_archive.read_latest_option_snapshot` owns archive selection,
  integrity and freshness checks. This milestone does not alter that reader.
- `strategy_compare.py` remains a descriptive comparison with no winner/ranking.

## Internal contract

`modules.historical_economics.evaluate_historical_economics` accepts an explicit
same-expiration position and immutable `ScenarioEvidence`. Each observation has
a unique ID, a fractional terminal underlying return, and outcome completion time.
The sample is shared across structures: it is never selected by their payoffs.
Canonical evidence fingerprints and ordered observation IDs make differing
samples visible. Fingerprints identify inputs, not certify data authenticity.

The trusted caller must supply the existing selection provenance, exact symbol,
anchor spot, expiration, research cutoff, source observation time, freshness
policy, observed-session horizon and authoritative remaining expiration sessions.
This internal type must not be accepted directly as verified public market data.
No calendar/session count is inferred from calendar DTE. The upcoming adapter
must calculate session alignment and retain archive IDs/checksums, selection
configuration and complete source provenance before exposing this via API/MCP.

All supported families use the same evaluator: long calls/puts, debit and credit
call/put verticals, standard call/put butterflies, currently supported directional
broken-wing butterflies, and iron condors. Existing topology restrictions remain.
Stocks, short naked options, mixed expirations and mixed multipliers are rejected.

## Units and costs

Signed leg quantities represent actual contracts (positive long, negative short).
Package premium is the aggregate signed per-share cashflow for those quantities;
positive is received, negative paid. Multiplier is explicitly supplied (100 by
default). Nonstandard multipliers are arithmetic scenarios only, not validation
that a market contract exists. No additional position-unit scaling is implicit.
Fees and slippage are total dollar costs for the whole package, charged once.
Per-contract fees must be multiplied by total contracts by the caller. Do not
include a charge both in fees and slippage. Zero slippage is an explicit model
assumption, not evidence of frictionless execution.

The existing 100-share payoff engine is reused by normalizing costs to its units
and scaling results back to the supplied multiplier. Max risk includes those
costs. It is not brokerage buying power. Unlimited maximum profit is represented
by null plus an explicit unlimited flag, never by nonstandard JSON Infinity.

## Available fields and interpretation

When gates pass: dollar EV, EV/max expiration risk, positive-payoff frequency,
profit factor, median/P10/P90, average positive/negative payoff, sample size and
per-observation payoffs. Deterministic max profit/loss, breakevens and required
movement remain separate. Quantiles use existing linear interpolation; scenarios
are equally weighted. No losses means profit factor is null with an explicit
reason (legacy infinity is not emitted); no winners with losses gives zero.
Missing winning/losing averages are null. Descriptive frequency is not POP.

Samples below the default 30-observation coverage minimum are unavailable. That
threshold is configurable for research/testing and is NOT statistical validation.
Overlapping analogs can be dependent; no independence, robustness, significance,
forecast calibration or trading edge is claimed, regardless of sample count.

Stale/future observations, future-maturing outcomes, missing history, context or
expiration-session mismatches suppress all historical metrics. Source observation
age differs from archive slot, request time and quote age. Quote age is explicitly
unknown. No archive freshness policy is changed or stale input promoted.

Holding period is `intraday`, `swing`, `monthly` or `leaps`; valuation is separately
`expiration` or `early_exit`. Names do not infer horizon data or change models.
Early-exit economics always fail closed until actual option marks or a validated
repricing adapter exists. Intraday also fails closed, including 0DTE, until exact
intraday expiration alignment exists. Deterministic expiration payoffs remain
clearly labeled and are never substituted for early-exit EV.

## Eligibility and limitations

States currently emitted: ECONOMICS_INCOMPLETE, CAPITAL_INELIGIBLE, or
EXECUTION_EVIDENCE_INCOMPLETE. All results remain research-only and
eligible_for_consideration=false. Positive EV cannot bypass execution/robustness
requirements. Path touch/breach, robust subset comparisons, executable liquidity,
Greeks/IV sensitivity, early exits and broker margin remain unavailable.

No API fields/tools are changed in this first slice. No new public endpoint,
ranking, recommendation, analog selector or provider is introduced. Existing
credit-vertical economics remain byte-for-byte unchanged.

## Exact next implementation step

Add a trusted adapter from the existing maturity-safe analog outcomes to
ScenarioEvidence, deriving expiration-session alignment from the NYSE calendar
and carrying archive provenance. Then attach results to research_position/run_market
and compare_structures using one shared sample and explicit common cost/holding
assumptions. Test mismatched comparisons, missing evidence and all 17 tools before
exposing additive API fields. Do not add broad all-strategy scanning in that PR.

This branch is based on verified current main
6d6bb56193fed94db1daecf3078c0d8718322d81. No runtime/deployment configuration
was changed. PRs #18/#19 and the frontend are untouched.
