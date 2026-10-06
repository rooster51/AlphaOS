# AlphaOS 2.0 Build Status

> Living implementation tracker. Update this file with every AlphaOS 2.0 code change.
> Candidate generation and strategy routing are research workflows, not recommendations or rankings.

## Current milestone

**Pre-merge market archive / AlphaOS 2.0 reconciliation**

Goal: evolve `Run QQQ` / `Run SPY` from a credit-spread-oriented workflow into an interface-agnostic options research workflow:

`Public market data -> AlphaOS market research -> opportunity classification -> strategy routing -> candidate construction -> research/compare -> position lifecycle -> journal/calibration`

## Status dashboard

| Area | Status | Notes |
|---|---|---|
| Existing Quant Lab / market research | COMPLETE | Preserve existing market state, structure, distributions, analogs and vertical research |
| Public market-data layer | COMPLETE + OBSERVATION GATE v1 | Canonical provider; live quote/chain snapshots now carry provenance and fail-closed freshness validation before research |
| Trade ledger schema | FOUNDATION COMPLETE | Additive position/event/snapshot schema; not deployed to production |
| Long call / put research | COMPLETE v1 | Risk, breakeven, required move, DTE, expected-move and structure context |
| Public long-option discovery | COMPLETE v1 | Unranked candidates from normalized Public chain; ask-based entry assumption |
| Opportunity Engine | FOUNDATION COMPLETE v1 | Validated simultaneous direction, premium, movement, time and volatility state envelope; unknown evidence remains unknown |
| Strategy Router | FOUNDATION COMPLETE v1 | Deterministic overlapping research routes; no ranking/winner; insufficient-evidence output supported |
| Debit-spread research/discovery | COMPLETE ADAPTER v1 | Reuses existing constructor; observed delta and valid quotes required; midpoint assumption explicit; no ranking |
| Butterfly / BWB research | COMPLETE ADAPTER v1 | Symmetric long call/put and iron butterflies; bullish put / bearish call BWBs; shared deterministic payoff |
| Iron condor research | COMPLETE ADAPTER v1 | Normalizes existing selector/premium-engine candidates, including asymmetric wings; construction unchanged |
| Generic position normalization | COMPLETE v1 | Existing same-expiration strategies; signed legs, observed quotes/Greeks/timestamps and shared economics |
| Research-session orchestration | COMPLETE v1 | Supplied normalized market/chain evidence through routing, existing constructors, research and descriptive comparison; no provider/API calls |
| Generic multi-leg Strategy Factory | PLANNED | Likely Codex handoff when repo-wide integration becomes worthwhile |
| Run Market / archive read path | COMPLETE v1 | Verified injected archive reads, authoritative NYSE session context, read-only research and JSON-safe response |
| Universal Analyze | PLANNED | Broader common research envelope plus strategy-specific evidence |
| Cross-strategy Compare | COMPLETE v1 | Shared descriptive evidence matrix across researched strategy families; preserves input order; no score, winner or recommendation |
| Account-aware filtering | COMPLETE v1 | Optional max-loss capital ceiling; explicit exclusions; no ranking or broker-margin claim |
| Position Monitor | PLANNED | Refresh original thesis/evidence against current state |
| Scenario Engine | PLANNED | Price/time/IV scenarios with explicit assumptions |
| Conversational journal writes | FOUNDATION ONLY | Ledger exists; service/API/MCP persistence not wired |
| Performance analytics | PLANNED | P&L, win rate, expectancy by strategy after durable journal |
| Calibration | PLANNED | Compare frozen entry classifications with realized outcomes |
| API/MCP AlphaOS 2.0 integration | LATER / CODEX CANDIDATE | Existing Phase 7-10 work lives on later branches; reconcile deliberately |
| Production deployment | BLOCKED BY APPROVAL | No production DB migration or deployment without explicit approval |

## Completed in current AlphaOS 2.0 branch

Branch: `alphaos2/trade-ledger-foundation`

Draft PR: #12

Implemented:

- Additive Supabase trade-ledger foundation:
  - positions
  - normalized initial legs
  - immutable lifecycle events
  - frozen research snapshots
  - RLS/index foundation
- Trade-ledger architecture documentation.
- Long call / long put research module using the existing generalized payoff engine.
- Long-option tests for calls, puts, scaling/fees, structure context and invalid inputs.
- Public-backed long-option discovery:
  - calls and puts
  - bid / ask / mid
  - conservative ask-based long-entry research assumption
  - delta / gamma / theta / vega / rho when Public supplies them
  - implied volatility when Public supplies it
  - volume / open interest when Public supplies them
  - bid/ask spread context
  - capital, breakeven, required move and expected-move context
  - eligibility filters without scoring/ranking
- Tests for normalized Public-chain discovery.
- AlphaOS 2.0 opportunity-state envelope with validated simultaneous dimensions and evidence sufficiency.
- Strategy Router v1 covering directional/premium, range, pin, large-move, volatility and late-0DTE routes.
- Router tests verifying overlapping routes, deterministic non-ranking behavior, no-route/insufficient-evidence behavior and fail-closed invalid states.
- Confirmed existing Strategy Selector already constructs call/put debit spreads, so AlphaOS 2.0 will integrate rather than duplicate that capability.
- Confirmed the shared payoff engine already analyzes symmetric butterflies and BWBs, and the premium engine already constructs iron butterflies plus put/call BWBs; AlphaOS 2.0 can normalize these existing capabilities rather than rebuilding payoff math.
- Cross-strategy comparison v1 normalizes capital at risk, profit/loss shape, breakevens, DTE, expected-move context and market-evidence availability across researched families without scoring or ranking.
- Public observation snapshot v1 normalizes underlying/option timestamps, symbol/expiration context and provenance; stale, missing, future-dated or mismatched observations fail closed before strategy research.
- `research_public_opportunities` provides the thin Public-to-provider-free-session bridge while keeping market classification supplied by AlphaOS research rather than invented from raw quotes.

## Architecture decisions

1. **Public is the canonical market-level data provider.** Add another provider only for a documented gap and only deliberately.
2. **AlphaOS owns research and interpretation.** Provider observations remain distinguishable from AlphaOS-derived evidence.
3. **AlphaOS DB owns the durable trade journal.** ChatGPT, Streamlit, future web/mobile and API clients are interfaces to the same ledger.
4. **Candidate generator order is not a ranking.** Strategy routing identifies structures worth investigating; it does not select a winner.
5. **Unknown evidence stays unknown.** Missing IV/Greeks/liquidity/market evidence must not be fabricated or silently inferred.
6. **Preserve working infrastructure.** Extend existing interfaces rather than refactoring working AlphaOS systems for cleanliness alone.
7. **No production changes without approval.** Draft code/migrations may be prepared and tested, but production DB/deployment changes require explicit approval.

## Opportunity Engine target

Represent simultaneous market dimensions rather than force one regime label:

- direction: bullish / bearish / neutral / unknown
- premium_state: rich / fair / cheap / unknown
- movement_state: range_bound / directional / breakout / large_move_expected / pin_candidate / unknown
- time_state: standard / late_0dte
- volatility_state: elevated / normal / depressed / unknown
- evidence
- confidence / evidence sufficiency
- caveats

Missing evidence must produce `unknown`, not a default classification.

## Strategy Router target

Examples of research routes:

- bullish + premium rich -> PCS, bullish BWB, call debit spread
- bullish + premium cheap -> long call, call debit spread, bullish diagonal
- bearish + premium rich -> CCS, bearish BWB, put debit spread
- bearish + premium cheap -> long put, put debit spread, bearish diagonal
- range-bound -> IC, butterfly, BWB, calendar
- pin candidate -> butterfly, BWB
- large move expected -> long straddle/strangle, directional debit structures
- elevated IV -> credit structures, IC, butterfly
- depressed IV -> long premium, calendars/diagonals
- strong directional breakout -> long option, debit spread, directional BWB
- late 0DTE -> vertical, IC, butterfly/BWB according to observed regime and risk

Overlapping routes are allowed. No-trade / insufficient-evidence is a valid output.

## Codex reserve

Use Codex when breadth makes repo-wide context materially valuable:

1. Generic multi-leg Strategy Factory integration across strategy families.
2. Reconciliation of current AlphaOS 2.0 work with Phase 7-10 API/MCP branches while preserving approved OAuth behavior.
3. Production service-side persistence, orchestration, migration and integration testing.

Do not spend Codex usage on narrow modules/tests that can be implemented safely in the active AlphaOS 2.0 branch.

## Production blockers / decisions

- Review and apply the AlphaOS 2.0 Supabase migration.
- Finalize event/fill semantics, especially adjustments and rolls, before production journal writes.
- Reconcile Phase 7-10 API/MCP work with the eventual AlphaOS 2.0 integration branch.
- Build a non-Streamlit server-side persistence path for API/MCP journal writes.
- Preserve the approved MCP OAuth persistence/identity design.
- Run integration tests before enabling conversational journal mutations.

## Definition of done for every AlphaOS 2.0 change

A change is not complete until:

- implementation is committed on the active AlphaOS 2.0 branch;
- tests are added/updated when behavior changes;
- CI status is checked when available;
- backward compatibility is considered;
- this status file is updated if milestone/status/architecture changed;
- production remains untouched unless explicitly approved.

## Latest verified checkpoint

- PR #12 remains the active draft integration PR.
- AlphaOS 2.0 test runs through the build-tracker checkpoint were green.
- Opportunity Engine state envelope and Strategy Router v1 are committed and their latest GitHub Actions runs passed.
- Limited strategy integration implemented in `modules/structure_research.py`: debit candidates reuse the existing constructor; butterfly/BWB/IC candidates reuse `options_payoff.trade_analysis`. No duplicate payoff/pricing engine.
- `research_routed_structures` filters supplied candidates through existing overlapping routes in input order. Generic directional routes require known direction; malformed/insufficient candidates are excluded. Existing route contracts are unchanged.
- Normalized results include legs, cashflow, capital/risk, profit, breakevens/signed move distances, optional DTE/expected-move context, scenarios, observed evidence and caveats. Cached scores/probabilities/recommendations are discarded.
- Debit discovery requires observed delta rather than inheriting the legacy selector's missing-delta-to-zero fallback. It preserves midpoint rounding and nearest-available wing selection, explicitly disclosed; no executable fill is claimed.
- Missing evidence remains unavailable. No symmetric butterfly discovery factory was added: research accepts existing/explicit supported candidates. Native quantities use the shared engine's package cashflow convention; legacy selector action-format candidates require one-unit legs.
- Focused validation through the structure-integration checkpoint: 69 tests + 7 subtests passed (27 new adapter/routing cases); full local suite: 300 tests + 40 subtests passed. Exact-commit CI passed.
- Cross-strategy comparison v1 is committed with focused tests; CI for the latest comparison commit is pending/has not yet appeared at this checkpoint.
- No production Supabase migration or AlphaOS 2.0 deployment has been applied.
- Public credentials and credential-dependent archive work remain intentionally deferred. The new observation layer is testable without credentials; a live Public call still requires configured credentials.
- Public observation loader/freshness gate is committed; latest CI is pending at this checkpoint.

## Research-session integration checkpoint

- `research_market_opportunities` accepts symbol, normalized market research (`spot`, optional dollar `expected_move`, classified `opportunity_state`), Public-shaped chain, expiration, timestamp, optional objective and capital ceiling. Supplied candidates can replace discovery in input order.
- Existing long/debit/premium constructors feed shared research and `strategy_compare`; no new pricing, payoff or probability model. Positions retain observed leg fields and timestamps; absent evidence remains unknown. Unknown time is accepted explicitly while existing caller defaults remain compatible.
- Supported: long call/put, call/put debit spreads, put/call credit spreads, symmetric butterflies, bullish/bearish BWBs and iron condors. Automatic butterfly discovery uses existing iron butterflies; symmetric long butterflies require supplied candidates.
- Input contract validation excludes malformed, crossed, duplicate and conflicting-expiration observations. Context mismatch, missing spot, expired chains and unsupported routes return explicit no-candidate/unavailable results.
- Capital filtering runs after shared max-loss economics and preserves candidate order, excluded research and reasons. JSON-safe output retains unlimited profit as `unlimited`. No winner or score is added.
- Limits: one expiration, standard 100-share multiplier; no fresh provider fetch or raw-feature classification. Existing long discovery distance limit and $0.65 per-contract premium fee remain disclosed assumptions. AlphaOS explicitly uses a $0 net-credit floor and permits zero-time 0DTE construction; the legacy engine default remains $50. Missing observed delta prevents debit discovery.
- Focused validation: 98 tests + 7 subtests passed. Full regression: 329 tests + 40 subtests passed in one full run. Exact-commit CI will be checked after push and reported with the commit.
- API/MCP integration, persistence, journal writes, migrations and production deployment remain unimplemented in this milestone.

## Opportunity Classifier v1

- Dedicated classifier reuses the existing Opportunity State contract and strict completed close/EMA9/EMA21/EMA50 ordering. Mixed or conflicting breakout evidence remains unknown. A completed close outside the previous 20-session high/low is a descriptive breakout, superseding generic directional movement. Raw feature values, rules, conflicts and unavailable evidence are returned.
- Public orchestration obtains Public history (or accepts fixture history), builds existing market-state features using the research timestamp cutoff, classifies, then invokes the existing session. Legacy caller-supplied states remain explicitly labeled. No provider interpretation or production integration.
- Premium rich/fair/cheap, volatility elevated/normal/depressed, range-bound, large-move and pin states remain unknown: this branch has no established calibrated rules. IV/RV ordering alone is not treated as premium value.
- Time state requires timezone-aware timestamps and explicit exchange session bounds; the configurable late-0DTE convention is 60 minutes before session close. After-hours and missing session context remain unknown. Same-day premium construction now uses zero time with no modeled POP (see the 0DTE checkpoint below).
- Expected-move evidence retains its supplied interval; comparison requires an explicit start matching research time and end on expiration. Unknown/mismatched intervals do not enter breakeven comparisons. No horizon rescaling.
- Freshness additionally rejects partially missing contract timestamps and checks the oldest provided quote side. Completed-history validation excludes current/future sessions and retains its audit.
- Focused validation: 57 tests passed. Full local suite before the final quote-side regression: 356 tests + 40 subtests passed. Exact-commit full CI is checked after push. No deployment, API/MCP, persistence or UI changes.


## Safe 0DTE premium construction

- Same-day premium structures now use zero time in the existing premium constructor instead of being blocked outright.
- AlphaOS 2.0 opportunity sessions explicitly set the premium constructor minimum net-credit floor to $0; valid low-credit structures remain researchable. The legacy/shared constructor default is unchanged.
- Quote-based construction/payoff economics remain available at 0DTE; modeled POP intentionally remains unavailable because the probability model requires positive time.
- Opportunity-session routing can now produce 0DTE premium candidates when the existing routing/evidence rules and quoted economics support them.
- No ranking, recommendation, API/MCP integration, deployment, persistence, or broker action was added.
- Focused 0DTE regression added. Latest CI is pending at this checkpoint.

## Pre-merge integration checkpoint

### COMPLETED

- Reconciled current main `f708061` (including PRs #14/#15) into `alphaos2/trade-ledger-foundation`; no textual merge conflicts. Main remains authoritative for Public collection, session calendar, slots, immutable archives and Supabase persistence. No scheduler changes in this pass.
- Corrected only the stale Run Market test status from `research_complete` to the existing `complete` contract.
- Retained zero-time same-day premium construction and explicit AlphaOS $0 net-credit floor, with legacy $50 default unchanged. No model probabilities are fabricated.
- Archive adapter now retains slot/finish/request timestamps, provenance and quality metadata; reports rejected rows, excludes symbol/time conflicts and failed expirations, and never substitutes collection time for missing quote timestamps. Questionable-contract warnings survive into position evidence.
- Shared NYSE bounds from the existing market session module validate Run Market context, including holidays and early closes. No second session calendar implementation. Classifier version survives orchestration.
- Added a read-only helper in existing `supabase_archive.py`, using an injected client, explicit as-of/freshness policy, deterministic latest metadata selection, private Storage download, checksum/identity validation and no writes. Legacy NULL slot rows remain readable. Partial latest evidence is visible rather than silently replaced by older complete evidence.
- `run_latest_market` accepts that injected reader; `run_market` remains deterministic over supplied archive/history and has no provider/storage writes. Supabase credentials stay outside the research core. Expired contracts cannot be presented as current latest research.
- Deterministic tests exercise the actual existing collector payload, archive adapter, classifier, routing, candidates, risk/capital exclusions, comparison and Run QQQ output; fake storage clients expose no write methods.
- Focused verification: 168 tests and 7 subtests passed. Complete regression suite: 405 tests and 40 subtests passed. Final-commit GitHub CI is tracked in PR #12 and the completion report.

### REMAINING

- Production reader/client wiring and live verification are deferred; no credentials or production requests used. Latest-read freshness is caller-configured, not an executable-quote guarantee.
- Completed daily OHLC is supplied by the caller using existing history facilities. The minute archive is not assumed complete enough to synthesize daily classifier history. Missing/invalid history leaves directional evidence unknown.
- Trade-ledger SQL remains unapplied; no journal writes, backfill or changes to legacy trades. Historical caller-supplied snapshots remain explicitly as-of their original observation time.
- Older Phase 7-10 API/MCP lineage is outside these branches; no OAuth/CIMD/grant lifecycle change or deployment was attempted. Existing direct Public observation helpers remain compatibility paths, not another archive system.

### INTENTIONALLY UNKNOWN / NOT YET MODELED

- Premium richness, volatility regimes, range-bound/large-move/pin states without defensible existing rules; missing IV, Greeks, liquidity and horizon-mismatched expected moves.
- No strategy rankings, scores, winners, trade confidence or recommendations. 0DTE POP remains unavailable.

### NEXT MILESTONE

- Review this reconciled feature branch, then separately authorize a thin read-only interface integration with the existing API/MCP lineage. Preserve approved authentication and the existing market archive. No automatic merge or deployment.
