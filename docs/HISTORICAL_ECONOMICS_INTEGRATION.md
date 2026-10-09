# Historical economics integration: structures and shared comparisons

Status: draft, not merged or deployed. Comparison continuation stacked on PR #22 at
`8077d47689fbfd3c30eec549a1503d420dde6a4b`.

## Actual integration

`POST /v1/research/structure` and MCP `research_structure` now return an additive
`research.historical_economics` object. Inputs, existing deterministic fields,
tool names, authentication and all 17 research tools remain unchanged.
The shared ArchiveResearchService invokes `modules.structure_economics`, which
reuses the verified archive reader, Public daily history loader, existing
dataset builder/Phase 3 selector, trusted adapter and historical evaluator.
There is no alternate provider, analog selector, or options payoff engine.

`POST /v1/research/structures/compare` and MCP `compare_structures` share this
same workflow for up to 20 structures. Each `research.candidates` entry adds
`historical_economics`; the existing deterministic `comparison` remains intact.
`research.historical_comparison` supplies context groups, zero-based candidate
indices, fingerprints, availability and pairwise comparability with typed reasons.
Candidate order is unchanged. No scores, rankings, winners or recommendations
are introduced. `run_market` integration remains deferred.

Within each request, exact symbol, as_of date, expiration and spot define groups.
The validated NYSE calendar determines each group's cutoff and session horizon.
Archive verification, daily history loading, dataset construction, analog selection
and trusted adaptation occur once per group, including failed builds. Each candidate
uses its own strikes, quantities, signed premium and fees against the frozen shared
evidence. No cross-request cache bypasses freshness. Different contexts are explicitly
not directly comparable even if returns coincide; within a group only successful
historical results with identical fingerprints are directly comparable. Missing
samples never establish comparability. Shared samples establish descriptive expiration
comparability only, not executable pricing or investment suitability.

## Evidence semantics and gates

The date-only explicit `as_of` means the completed NYSE session on that date.
The server determines its exact calendar close, including early closes, and
requires it to be at or before the server clock. It reads archive evidence at
that historical cutoff using the existing 600-second default policy. The reader
still checks availability, checksum, provider/symbol, storage and observation
identity. This is explicitly historical research, NOT a claim the archive is
fresh now. Both archive age at cutoff and age at current request are returned,
along with observation, slot, collection-finish and cutoff timestamps. No quote
age is inferred. The existing live `run_market` freshness rule is untouched.

Daily history includes only completed bars through that session. Its full date
sequence is checked against NYSE sessions: missing bars, holidays masquerading
as sessions, or missing target closes fail closed. The explicit scenario spot
must match the completed target close; a supplied intraday spot is not silently
reanchored. Premium and fees remain caller-supplied scenario assumptions, never
verified historical option prices or fills.

Future sessions are independently checked against NYSE through the expiration.
Expiration must be a trading date and the horizon must be one of the existing
1/2/3/5/10-session outcomes. 0DTE and incomplete-session requests return null
historical metrics. No daily expiration EV is presented as intraday/early-exit EV.
The matching method remains the existing tolerance selector; samples below 30
are unavailable. This minimum is descriptive coverage, not statistical proof.

The adapter now independently validates future and historical session sequences,
actual close bounds for outcome maturity, and completion of the target session.
History's cutoff is distinct from the archive's earlier collection observation:
outcomes completed by the validated research cutoff may be used without changing
archive age. Canonical JSON selection metadata removes dictionary-order noise
from common-sample fingerprints. An adapter called alone still labels archive
IDs as caller-supplied assertions. Only the server integration labels evidence
as coming through its verified archive reader; public requests cannot supply
archive provenance or scenario bundles.

## Output and availability

The nested contract carries deterministic payoff/risk/breakevens, historical
dollar EV and EV/max expiration risk, positive historical payoff frequency,
profit factor, quantiles, sample size, ordered observations and fingerprint.
It retains explicit missing reasons when any gate fails. Existing deterministic
research still succeeds when archive/history is unavailable.

Execution/liquidity, current Greeks/IV, historical option marks, independent
subset robustness, broker buying power and early-exit economics remain
unavailable. All output is research-only; eligible_for_consideration stays false.
`capital_eligibility` states `not_assessed` when no budget is supplied (the legacy
explicit-structure input has no budget field). The shared evaluator still
enforces an explicitly supplied max-loss budget; no new API input is invented.

## Compatibility and operational limitations

Completed-date structure requests can now perform archive/history reads, adding
latency. Intraday, unsupported-horizon and invalid-calendar requests stop before
I/O. Comparison evidence is reused within a request without bypassing
freshness or changing the scenario fingerprint. Historical archive coverage and
provider history availability remain prerequisites, so production may return
typed missing evidence. Tests use fixture storage with real checksum verification
and synthetic daily bars; they are not live production verification.

No changes to OAuth, secrets, Supabase schemas, journal, frontend, research router,
collector schedule, broker integrations or production infrastructure. No merge,
deployment, paid service or order execution is authorized by this milestone.
