# Release 1 candidate-generation diagnosis

## Confirmed production reproduction

Base: `main` at `f9b19d35225a3397578ee77f61e687550c42e16a`
(merged PR #43). On October 16, 2026, authenticated OAuth MCP `run_market`,
REST `/v1/research/market`, and the website `/api/research/market` reproduced zero
generated candidates for SPY and QQQ with expiration `2026-10-19` and $1,000
available capital. These were successful HTTP research responses, not stale,
authentication, missing-archive or response-validation errors.

| Symbol | Archive observation (UTC) | Snapshot contracts (all expirations) | Clean calls/puts for October 19 | Matched routes | Generated | Capital rejected |
|---|---|---:|---:|---:|---:|---:|
| SPY | 2026-10-16T15:11:11.206869+00:00 | 2,004 | 77 / 77 | 0 | 0 | 0 |
| QQQ | 2026-10-16T15:11:15.363471+00:00 | 2,134 | 57 / 57 | 0 | 0 | 0 |

The same result occurred in all 36 REST probes: both symbols, all six available
expirations (October 16, 19, 20, 21, 22 and 23), and $150/$1,000/$5,000 capital.
SPY retained 77 calls and 77 puts per selected expiration. QQQ retained 71/71,
57/57, 49/49, 57/57, 49/49 and 71/71 respectively. Website and direct REST
October 19/$1,000 responses matched diagnostics and archive checksum for each
symbol; authenticated MCP showed the same archive and diagnostic result.
Local response captures are under ignored `diagnostics/candidate-generation/`;
production observations and credentials are not committed as test fixtures.

## Root cause

Completed daily history was loaded. The current strict ordering rule correctly
left direction and movement unknown for mixed completed close/EMA evidence.
Premium and volatility also remained unknown because there is no calibrated
classification rule for them. The time state was standard. None of those values
matched an evidence-based route.

`research_market_opportunities` used routed families as the entire construction
allowlist. With no routes it never called any constructor, so economics and
capital checks were never reached. Increasing capital could not change that.
Snapshot contract count also covers every expiration, not the selected chain.

The production response establishes this pre-construction gate. It does not
establish whether particular live contracts would pass delta, geometry and
economics gates after the change: private raw contract values were not available
through the deployed response, and no modified backend was deployed for this
investigation. Positive construction results below are fixture-backed evidence,
not claims about currently available trading opportunities.

## Focused behavior change

Classification and `route_strategies` rules are unchanged. When automatic research
has **no matched route**, both existing call- and put-debit constructors may test
quote-supported hypotheses. They retain the existing observed-delta selector,
valid unique bid/ask requirements, protection-leg selection, pricing assumption,
positive debit below actual width, shared payoff economics and capital ceiling.
Missing delta is not imputed. Both directions are considered without selecting a
market thesis. No new family, quote/pricing engine, probability, score or ranking
is introduced. An explicitly supplied candidate still requires its existing route;
nonempty unsupported routes do not silently broaden discovery.

Returned hypotheses carry `generation_basis: unclassified_quote_research` and
`classification_supported: false`, including capital exclusions. Evidence-based
routes stay empty when evidence is unknown. The website displays this distinction
on the diagnostic panel and the candidate itself. Historical evidence eligibility
remains separate from capital eligibility; archive-entry economics still fail
closed when required entry-aligned evidence is unavailable.

Existing evidence-routed discovery is unchanged. The five preexisting parity
fixtures were regenerated for diagnostics only, with an explicit check that all
prior economics, quote evidence and other fields remained identical.

## Diagnostic contract

`research.archive.diagnostics` and
`research.research_session.market.archive_diagnostics` report raw bucket counts,
total contracts, selected/other-expiration counts, normalized rows and archive
rejection reasons/details. `research_session.diagnostics.pipeline` reports:

1. Archive selection: snapshot rows versus selected-expiration rows.
2. Archive quality: selected rows versus normalized chain rows.
3. Chain validation: normalized quotes versus valid unique contracts, with invalid
   bid/ask/strike, duplicate, type, expiration, symbol and boolean-value details.
4. Classification: total dimensions versus known dimensions; unknowns stay named.
5. Routing: matched routes versus resolved supported families, separately listing
   quote-research families. Zero routes is not counted as invalid structures.
6. Construction: constructor families versus generated structures, with per-family
   quote/delta counts and selector/geometry failures. Existing premium constructors
   expose attempted counts and missing-leg, duplicate-leg, distance, bid, fee,
   credit and payoff rejection counts without changing their selection rules.
7. Economics: supplied/generated structures versus valid researched payoffs.
8. Candidate routing: researched structures versus allowed structure families.
9. Capital eligibility: allowed structures versus accepted structures, with unknown
   risk and excessive capital distinguished.
10. Historical evidence: accepted structures versus evidence-eligible structures,
    retaining missing-evidence reasons rather than inventing POP/EV.

Each stage has status, input/output counts and explicit units. Inputs and outputs
with different units (families to structures, for example) must not be subtracted
as rejection counts. `not_attempted` is distinct from a completed stage producing
zero. Detail counts may overlap when one contract has multiple defects. Per-family
premium attempt/rejection counts precede the existing duplicate-signature removal;
the session generated count counts the actual returned constructor output.

`zero_candidate_reason` distinguishes no constructible structure, invalid
economics, all structures exceeding capital, context failure and other exclusions.
`classification_limitations` separately preserves missing-route evidence. The
website renders the backend pipeline and constructor diagnostics; it computes no
prices, classifications or candidate rankings. REST and MCP use the same result.

## Regression and delivery scope

SPY/QQQ tests use controlled archive quotes and mixed completed history with the
October 19, 2026 expiration and $1,000 capital. They verify both modes, both debit
hypotheses, unchanged unknown classifications, zero evidence eligibility, positive
evidence-routed fixtures, honest zeros for missing delta/crossed quotes/no
protection/nonpositive debit, and capital levels $1/$150/$500/$1,000/$5,000.
Shared REST-generated fixtures are compared exactly through OAuth MCP and the
website bridge; browser tests cover stage counts and unclassified labels.

Current/historical freshness, archive integrity, expiration selection, OAuth/API
authentication and read-only behavior are unchanged. No collection, database,
Render configuration, secret, merge or deployment change is part of this PR.
Production verification of the added counts and actual constructor outcomes
remains a post-review/post-deployment step.
