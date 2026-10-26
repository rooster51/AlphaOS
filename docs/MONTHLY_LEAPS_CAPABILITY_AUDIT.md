# Monthly and long-dated research capability audit

Audit date: 2026-10-26. Baseline: main `72d7babc1f539adb520bfc54d3c0c5fa062a3a88` (PR #65). Branch: `audit/monthly-leaps-capability`.

## Decision and evidence scope

Exact deterministic monthly and long-dated scenario research exists for the supported families below. Complete evidence-backed monthly/LEAPS research does **not** follow from that fact. Collection is bounded, automatic routing is evidence-dependent, historical horizons are limited, and the website lacks the explicit scenario interface on this baseline. No bounded runtime defect was established; this change adds audit tests and documentation only.

No production credentials, provider requests, archive downloads, history capture, infrastructure inspection/change, performance benchmarks or deployment were used. Existing controlled fixtures exercise the trusted archive reader; they do not prove current production inventory. Public's retention/replay permission remains pending. Freebuff's branch and all frontend files were left untouched. Issue #60 / Milestone 1 remain open and their performance work remains paused.

Status meanings:

- **SUPPORTED AND TESTED (S):** concrete executed deterministic/contract tests, limited to the named layer; not a claim of fresh production data, recommendations or complete historical modeling.
- **SUPPORTED BUT DATA-BLOCKED (D):** a working path requires verified contracts/history that this audit cannot establish. Unknown production inventory is not proof that contracts are absent.
- **PARTIALLY IMPLEMENTED (P):** a concrete code, horizon, routing, collection or interface limitation remains; additional data alone does not remove it.
- **NOT SUPPORTED (N):** canonical evaluation/construction does not implement those semantics. A router string is insufficient.

## Canonical path

Authenticated `POST /v1/research/market` -> `MarketRequest` -> `ArchiveResearchService` -> trusted checksum/identity/freshness reader -> `run_latest_market` / `run_market` -> exact-expiration normalization -> regular-session gate -> completed-history classifier -> `research_market_opportunities` -> chain cleaning -> quote-based constructors -> shared `research_position` / payoff -> capital ceiling -> historical evidence annotations. MCP `run_market` delegates to the same service. Objective is context, not a strategy selector or classification override.

Explicit `POST /v1/research/structure` and `/v1/research/structures/compare` use `StructureRequest` with an ISO expiration, as_of, spot, signed package cashflow, fees and signed option legs. MCP `research_structure` / `compare_structures` delegate to them. These are **caller-supplied scenarios**, not verified entry quotes. Deterministic economics do not require a matching archived contract; historical annotations have separate trusted-evidence gates. No per-leg expirations, capital-limit parameter or archive-priced contract selection are accepted by these explicit request contracts.

Sources: `alphaos_api/research2.py`, `alphaos_api/mcp_server.py`, `modules/run_market.py`, `modules/market_archive_adapter.py`, `modules/opportunity_session.py`, `modules/position_research.py`, `modules/options_payoff.py`, `modules/structure_economics.py`.

## SPY and QQQ capability matrix

Every row applies identically to **SPY and QQQ**. M = exact standard monthly `2030-01-18`; L = exact >=365-day `2031-01-17`, as_of `2030-01-02`. Those are existing deterministic fixture dates. L is a long-dated date, not certification of a branded LEAPS series. Explicit tests cover REST, authenticated MCP, ordered comparison, exact payoff/provenance and fail-closed missing historical evidence.

| Structure | Explicit M | Explicit L | Automatic market discovery at M/L | Full evidence-backed product state / root cause |
|---|---|---|---|---|
| Long call | S | S | S constructor; routed on breakout or qualifying premium evidence; D for actual contracts | P: routing/evidence and historical/website limits below; unlimited call profit stays `unlimited`, premium+fees risk stays finite |
| Long put | S | S | S constructor; same evidence dependence; D for actual contracts | P: same limits; put profit bounded at underlying zero |
| Call debit spread | S | S | S observed-strike enumeration, even as unclassified research when no route matches; D for actual quotes/deltas | D for verified production contracts; P for complete historical/website capabilities |
| Put debit spread | S | S | S, same constraints | D / P, same causes |
| Put credit spread | S | S | S constructor, but P canonical M/L routing: premium-rich/volatility regimes remain unknown; late-0DTE exception does not establish monthly support | P: evidence classification gap plus contract/history limitations |
| Call credit spread | S | S | Same as put credit | P, same causes |
| Long call butterfly (three legs 1:-2:1) | S | S | N: `butterfly` automatic enumeration builds iron butterflies, not long butterflies | P: explicit-only; automatic construction would be new scope |
| Long put butterfly (three legs 1:-2:1) | S | S | N, same reason | P: explicit-only |
| Bullish put broken-wing butterfly | S | S | S unequal observed wings; canonical breakout can route it; D for quotes; other routes need missing classifications | P: evidence-dependent discovery, bounded widths/history/interface |
| Bearish call broken-wing butterfly | S | S | Same | P, same causes |
| Iron condor | S | S | S constructor, P canonical M/L routing: range-bound/rich/elevated classifications not established; late-0DTE is separate | P: classification semantics, not merely missing contracts |
| Symmetric credit iron butterfly | S | S | S constructor, P canonical M/L routing as above | P, same causes |
| Calendar / diagonal (multiple expirations) | N | N | N despite route names | N: one expiration per structure; requires new contract/engine design |
| Long straddle / strangle | N | N | N despite route names | N: mixed-type two-long-leg structures rejected by `_family`; new strategy implementation required |
| Naked short options, stock/option combinations, other ratio/reversed BWB shapes | N | N | N in canonical research scope | N: supported option-only geometry/finite-positive-risk rules reject them; legacy payoff utilities do not establish canonical support |

The S automatic labels are constructor evidence, **not** a claim every strategy is returned by canonical market routing. `tests/test_width_discovery.py` tests eight spread/multileg families across both symbols and four expirations, including irregular spacing, exact/manual widths, $150 eligibility and invalid quotes. `tests/test_long_option_discovery.py` covers outright construction. New `tests/test_monthly_leaps_capability.py` closes the *test coverage* cross-product for explicit REST/MCP monthly/long-dated scenarios (48 positive cases, 16 unsupported-case failures). It does not change strategy coverage or runtime behavior.

## Expiration and archive availability

| Capability | Status | Verified behavior / limitation |
|---|---|---|
| Exact monthly / long-dated API date | S | No short-DTE request cap; exact requested expiration must exist in the selected verified archive for market research; unavailable date returns `archive_expiration_unavailable`, never a substitute |
| Standard monthly calendar labeling | S | Third-Friday session, with holiday adjustment; original provider date must be listed; calendar label does not certify series type |
| Long-dated date handling | S | >=365 calendar days is `long_dated`; not verified LEAPS branding; dates below 365 days can still be requested but are not labeled long_dated |
| 0DTE / 1DTE / weeklies | S contract/fixture path | Existing session, expiry and quote gates remain; no new latency or production acceptance claim |
| Every monthly / every long-dated listed expiry | P | `select_expirations` retains 0-7 DTE and adds at most one extra monthly and one extra long-dated expiry; does not collect the entire listed universe |
| All strikes in a selected expiry | P | `config/intraday_archive.json` retains +/-5% spot; deep ITM/OTM structures cannot be discovered from excluded contracts |
| LEAPS series certification / deliverable metadata | N as a claim | Date alone does not establish exchange series branding; economics assumes standard 100-share contracts, not adjusted deliverables |
| Actual current SPY and QQQ monthly / long-dated archives | D / unverified | No production archive inventory was inspected under the credentials restriction. Existing test archives demonstrate machinery only; do not claim live availability or proven absence |
| Missing/failed expiry, missing quotes, stale/checksum-invalid archive | S fail-closed | Fixture tests preserve exact rejection, no live-provider fallback, reason diagnostics and no fabricated candidates |

Sources/tests: `config/intraday_archive.json`, `modules/intraday_archive.py`, `modules/expiration_coverage.py`, `tests/test_expiration_coverage.py`, `tests/test_archive_read_path.py`, `tests/test_width_discovery.py`. The separate daily collector's 0-10 DTE +/-10% policy is not evidence that the intraday canonical archive contains those strikes/expirations.

Enumeration also has existing visible bounds: <=80 observed contracts per side, <=100 strike-width units, 1024 total geometry attempts shared across families. Capital does not determine that budget. Partial search is surfaced, not reported as exhaustive unaffordability. This is **partial completeness**, not a new defect to repair by silently changing breadth.

## Historical evidence, economics and capital

- Shared payoff evaluation gives exact expiration maximum profit/loss and roots from supplied/constructed cashflows, quantities and fees. Market capital screening occurs **after** that evaluation. Existing tests verify equal-to-budget acceptance, over-budget exclusion, $150 cases, irregular spacing and all automatic families. Expiration max loss is not broker margin, buying power or early-exit risk.
- `modules/market_outcomes.py` supports only **1,2,3,5,10 exchange-session** labels. `prepare_structure_evidence` returns `unsupported_expiration_session_horizon` beyond them. A monthly close enough to fit a supported horizon can use the existing evidence path; most longer-monthly and LEAPS scenarios cannot. Merely retaining more bars will not implement new horizons. New matrix cases explicitly assert missing EV and `eligible_for_consideration=false`, while exact deterministic economics remain available.
- Canonical market archives are regular-session intraday observations. `attach_market_economics` deliberately prevents completed-close analogs from being treated as intraday entry/exit evidence. That temporal mismatch is independent of horizon and provider retention permission. No daily-return POP/EV is promoted to a trade forecast.
- Explicit scenarios may have supplied spot/premium even without archived contracts. That is valid scenario math, not a quote-verification bypass: provenance says supplied scenario, and evidence-backed eligibility remains unavailable when validation fails.
- Explicit requests **do not accept available_capital**; comparison is unranked and its capital status is not assessed absent a budget. Market requests do accept it. Extending the explicit contract is a coordinated API/MCP/frontend design decision, not a contract-preserving bug fix.
- Long options have expiration/roots in `trade`/`position` and `payoff`; not every top-level field matches the multileg response shape. Consumers must use the existing contract/fallbacks, not assume a new uniform field. No schema normalization was introduced by this audit.

## Website / REST / MCP parity

| Request | REST | MCP | Website on audited main |
|---|---|---|---|
| Exact-expiration market research, Auto/manual width, capital | S | S (`run_market`) | S bridge and existing research page; forwards exact date and validates returned expiration/width |
| Explicit supported structure, supplied economics | S | S (`research_structure`) | P: no explicit structure HTTP/UI path on this baseline; independently being built by Freebuff, not assessed as shipped |
| Ordered explicit comparison | S | S (`compare_structures`) | P: same Freebuff work; no claim of complete interface parity |
| Caller-specified strategy/holding-horizon discovery | N as a new request knob | N | N: objective is context, not a strategy filter; no new contract is implied |

Read-only frontend inspection: `web/src/app/api/research/market/route.ts`, `web/src/components/market/MarketResearchPanel.tsx`, `web/src/lib/market-candidates.ts`. No frontend files changed. Existing `tests/test_website_mcp_parity.py`, `web/tests/expiration-coverage.test.mjs` and browser expiration tests cover the shipped market contract, not Freebuff's unmerged feature.

## Gap closure order

1. **Coordinate existing explicit UI work with Freebuff:** validate its adapters against the existing REST/MCP request and heterogeneous response shapes, including supplied-scenario provenance, exact date, unsupported geometry, unknown historical EV and no ranking. This has deterministic existing contracts and needs no retained provider history. No overlapping implementation is proposed here.
2. **Design review, not implementation:** decide whether long-horizon research means exact expiration scenarios, evidence-backed expiration distributions, or intraday exit research. Document that each needs different evidence. The 1/2/3/5/10-session and intraday/close mismatch cannot be fixed safely by relabeling data or extending an enum.
3. **After authorization:** inventory exact archived expirations/strikes, then review whether bounded collection is adequate. Broadening dates/strikes or retaining entry-aligned history requires provider/collection review; no capture or collection change is authorized here.
4. **Separate strategy/API proposals only if needed:** long-butterfly automatic discovery, missing market classifications, explicit capital parameter, multi-expiration structures and straddles/strangles require deliberate semantics and tests. Do not represent them as already implemented or bundle them into a monthly audit fix.

No runtime defect met the small contract-preserving-fix threshold. Do not bypass classification, widen collection, synthesize quotes/Greeks, relax freshness, infer LEAPS certification, or manufacture longer-horizon EV to make the matrix greener.

## Validation and exact change list

- Full Python run: **1,232 passed + 64 subtests**, Python 3.12.14, 500.63s, four dependency deprecation warnings. This collected all 1,184 baseline tests plus the initial 48 positive audit cases.
- Final audit module: **64 passed** in 18.88s, including the 16 negative cases added after that full run began. Together these runs cover all 1,184 existing tests and all 64 new cases; they are not a single 1,248-test invocation.
- Existing website unit tests: **100 passed**. No frontend changes; browser/typecheck/build were not rerun for this test/documentation-only change.
- `git diff --cached --check`: clean. No new dependency, provider request, production credential, performance experiment, archive write, infrastructure change or timeout change.

Only files changed: `tests/test_monthly_leaps_capability.py` and `docs/MONTHLY_LEAPS_CAPABILITY_AUDIT.md`. No runtime fix was made. The new tests use supplied scenario cashflows/geometries already exercised by existing deterministic tests, never manufactured market observations or historical evidence. No PR, merge or deployment.
