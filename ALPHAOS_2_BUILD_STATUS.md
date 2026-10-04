# AlphaOS 2.0 Build Status

> Living implementation tracker. Update this file with every AlphaOS 2.0 code change.
> Candidate generation and strategy routing are research workflows, not recommendations or rankings.

## Current milestone

**Opportunity Engine + Strategy Router**

Goal: evolve `Run QQQ` / `Run SPY` from a credit-spread-oriented workflow into an interface-agnostic options research workflow:

`Public market data -> AlphaOS market research -> opportunity classification -> strategy routing -> candidate construction -> research/compare -> position lifecycle -> journal/calibration`

## Status dashboard

| Area | Status | Notes |
|---|---|---|
| Existing Quant Lab / market research | COMPLETE | Preserve existing market state, structure, distributions, analogs and vertical research |
| Public market-data layer | COMPLETE | Canonical provider; do not silently replace |
| Trade ledger schema | FOUNDATION COMPLETE | Additive position/event/snapshot schema; not deployed to production |
| Long call / put research | COMPLETE v1 | Risk, breakeven, required move, DTE, expected-move and structure context |
| Public long-option discovery | COMPLETE v1 | Unranked candidates from normalized Public chain; ask-based entry assumption |
| Opportunity Engine | FOUNDATION COMPLETE v1 | Validated simultaneous direction, premium, movement, time and volatility state envelope; unknown evidence remains unknown |
| Strategy Router | FOUNDATION COMPLETE v1 | Deterministic overlapping research routes; no ranking/winner; insufficient-evidence output supported |
| Debit-spread research/discovery | EXISTING PARTIAL | Existing Strategy Selector constructs call/put debit spreads; normalized adapter design is complete but repository write is currently tool-blocked |
| Butterfly / BWB research | EXISTING FOUNDATION | Generic payoff engine already supports symmetric and broken-wing butterflies; premium engine already generates iron/BWB structures; needs AlphaOS 2.0 normalized research context |
| Iron condor research | EXISTING PARTIAL | Existing vertical infrastructure; needs AlphaOS 2.0 normalized integration |
| Generic multi-leg Strategy Factory | PLANNED | Likely Codex handoff when repo-wide integration becomes worthwhile |
| Universal Analyze | PLANNED | Common research envelope plus strategy-specific evidence |
| Cross-strategy Compare | PLANNED | Same thesis/context; normalize tradeoffs; no winner/ranking |
| Account-aware filtering | PLANNED | Capital/risk constraints filter eligibility only |
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
- Existing debit-spread construction was identified for reuse rather than replacement. A normalized shared-payoff adapter was designed, but the repository write was blocked by the tool safety layer; no partial code was committed.
- Existing butterfly/BWB payoff and generation support was verified for reuse in the next normalized strategy-research layer.
- No production Supabase migration or AlphaOS 2.0 deployment has been applied.
- Public credentials and credential-dependent archive work remain intentionally deferred.
