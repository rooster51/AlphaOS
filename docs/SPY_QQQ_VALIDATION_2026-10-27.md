# SPY/QQQ validation — October 27, 2026

Production release remains BLOCKED. The warm Cloudflare preview and Render API
successfully researched both symbols across all four tested horizons. All 88
observed-price structure scenarios passed independent expiration-payoff checks
through both services (176 evaluations). This establishes scenario arithmetic and
transport, not trade readiness, calibrated expected returns, or executable fills.

Scope follows the [PR #67 checklist](https://github.com/rooster51/AlphaOS/pull/67#issuecomment-6447281192).
The deployed preview tested commit `9ca8303b470d0434af8fa2ac091dcb42c2b1c592`,
deployment `e11c607d-5b01-427a-974d-f0c14c80b5c3`, created 16:14:53 UTC.
The audit began 16:29:05 UTC / 12:29:05 EDT during the trading session.
Preview: https://codex-cloudflare-workers-alphaos-web.rfroux95.workers.dev
Backend: https://alphaos.onrender.com

No deployment, merge, infrastructure, credential, collector, strategy engine,
timeout, or MCP implementation change was made during this audit. PR #67 stays open.

## Capability results

| Capability | Result | Evidence / remaining limitation |
| --- | --- | --- |
| Cloudflare runtime bindings | PASS | Native Cloudflare runtime; URL/token bindings present; configuration ready; demo false. Health alone does not verify backend connectivity. |
| Authenticated preview → Render | PASS | Actual market, structure and comparison requests returned 200 for both symbols. |
| Verified Supabase archive | PASS | API snapshot IDs, SHA-256, symbol, observation time and complete status independently matched read-only Supabase queries. API freshness ages 190–276 seconds, below its 600-second policy. |
| Market research, all four horizons | PASS with limits | Exact requested expirations returned successfully, without replacement dates. Research is not a recommendation. |
| Structure economics and comparison | PASS with limits | 11 representations × 2 symbols × 4 horizons; API/preview economics equal. Comparison preserves explicit scenarios and produces no winner. |
| Automatic strategy routing / strongest opportunity | BLOCKED | Actual state had only time classified; direction, premium, movement and volatility unknown; insufficient evidence for routing. Unclassified debit research is retained. No credit-spread default was imposed. |
| Quote-bound trade validation | BLOCKED | Audit used actual observed bid/ask legs. Public structure DTO accepts explicit scenarios, without preserving contract IDs/quote timestamps as verified market evidence. It correctly labels them user-supplied scenarios. |
| POP / expected value | BLOCKED | All tested explicit scenarios had sample size 0 and `as_of_session_not_complete`. No calibrated POP/EV was claimed. Existing historical horizons are 1, 2, 3, 5 and 10 sessions; calibrated 0DTE and longer monthly/LEAPS holding horizons are not implemented. |
| Broker buying power / margin | BLOCKED | `capital_at_risk` matches maximum expiration loss; broker/account-specific margin and available funds are not implemented. |
| Website / Render consistency | PASS | Live browser submitted SPY/QQQ market requests, SPY weekly debit spread, QQQ long-dated call and saved comparison; no page errors or integrity warnings. |
| Live MCP consistency | BLOCKED | Both connected `run_market` calls returned connector `UNAUTHORIZED`, requiring reauthentication before execution. Backend parity cannot be inferred from these failures. Local MCP/API parity tests pass. |
| Cold Render availability within 12 seconds | FAIL release gate | Previously confirmed Free-service startup exceeds the fixed budget; this warm run does not disprove it. See [timeout evidence](CLOUDFLARE_RENDER_TIMEOUT.md). No paid-plan change or timeout increase made. |
| Error handling | PASS | Missing API auth → 401; invalid preview symbol → 400; empty comparison → 400; unavailable archived expiration → API 422 / preview 502 with `archive_expiration_unavailable`, no replacement data. |
| Navigation | PASS | Market, strategies, structures, session, journal, risk, settings, dashboard and mobile drawer. Foundation pages remain placeholders, not validated account functionality. |

## Strategy × expiration matrix

Every PASS below applies to **both SPY and QQQ scenario evaluation**, through
Render and the preview. All remain **BLOCKED for a trade-ready claim** for the
evidence limitations above. Each cell is one observed-price example per symbol,
not exhaustive coverage of every strike, date, quantity or market condition.

| Existing representation | 0DTE | Weekly | Monthly | Long-dated |
| --- | --- | --- | --- | --- |
| Long call | PASS | PASS | PASS | PASS |
| Long put | PASS | PASS | PASS | PASS |
| Call debit spread | PASS | PASS | PASS | PASS |
| Put debit spread | PASS | PASS | PASS | PASS |
| Put credit spread | PASS | PASS | PASS | PASS |
| Call credit spread | PASS | PASS | PASS | PASS |
| Symmetric call butterfly | PASS | PASS | PASS | PASS |
| Symmetric put butterfly | PASS | PASS | PASS | PASS |
| Bullish broken-wing butterfly (puts) | PASS | PASS | PASS | PASS |
| Bearish broken-wing butterfly (calls) | PASS | PASS | PASS | PASS |
| Iron condor | PASS | PASS | PASS | PASS |

Dates tested: 2026-10-27, 2026-10-30, 2026-11-20 and 2027-12-17
(416 calendar days). The last is a verified listed long-dated expiration;
LEAPS product branding was not independently established. Other expiration
availability must be checked separately: the provider listed 2027-01-15, but
the selected archive did not contain it; both symbols correctly failed closed.

## Real-data and economics method

The audit fetched actual underlying quotes and provider option chains through
authenticated Render endpoints. It checked OSI root/date/type/strike consistency,
finite uncrossed nonnegative bid/ask and both quote timestamps within 900 seconds
of the chain's evaluation time. Old/invalid legs were excluded, never repaired.
Natural entry prices used observed ask for purchases and bid for sales, including
leg quantities. These are **zero-fee, before-fees scenarios**, not promised fills.
No contract, premium, probability or EV was manufactured. The $500 market request
capital is a test input, not a verified account balance.

An independent piecewise-linear payoff evaluator checked max profit (including
unlimited calls), max loss, breakevens, signed premium/net cash, capital at risk,
vertical width, return on risk, exact legs and expiration. API/preview matched.
No incorrect calculation was reproduced, so no product math change was justified.
This does not validate early assignment, exercise, financing, execution costs,
broker margin, or pre-expiration mark-to-market. Historical calendar diagnostics
also remain qualified: completed daily bars exist, but session-calendar audit is
not verified. Do not infer calibrated historical results from those bars alone.

| Symbol / horizon | Fresh / total raw chain contracts | Preview market latency |
| --- | ---: | ---: |
| SPY 0DTE | 195 / 298 | 4,453 ms |
| SPY weekly | 452 / 498 | 4,969 ms |
| SPY monthly | 450 / 474 | 3,797 ms |
| SPY long-dated | 506 / 506 | 2,235 ms |
| QQQ 0DTE | 230 / 314 | 5,531 ms |
| QQQ weekly | 431 / 454 | 5,734 ms |
| QQQ monthly | 461 / 496 | 4,734 ms |
| QQQ long-dated | 376 / 376 | 2,531 ms |

All market responses were within the unchanged 12,000-ms preview budget.
Do not treat a partly stale raw chain as wholly verified; selected legs were
checked individually. Provider delay, quote executability and close status remain
qualified. Snapshot `min_dte=0/max_dte=7` metadata alone does not describe extended
coverage: actual verified archive entries included monthly and long-dated quotes.

SPY snapshot `c9995c28-51de-470e-84a3-83ca8a376a33` and QQQ snapshot
`4048fc53-7dae-4ce8-a877-8bbc0b85c457` matched Supabase. Compact observed-leg
evidence, calculated outputs, request IDs and checks are in
[the sanitized capture](validation/spy-qqq-2026-10-27.json). No credentials or raw
full-chain payloads are committed. Evidence is historical at capture time.

## Checks and reproduction

Actual results this run:

- Python: **1,184 passed**, 64 subtests passed, 4 deprecation warnings.
- Web unit tests: **161 passed**; TypeScript check passed.
- Next build and browser suite: **43 passed**.
- Workers preview build, artifact check and credential scan: passed; **23 public assets** checked.
- Workers runtime suite: **4 passed**; preview browser suite: **43 passed**.
- Dependency audit: **0 vulnerabilities**.
- Live API/preview: **88 cases / 176 independent economics evaluations**, no failures.
- Live browser: both market symbols, two actual structure submissions, comparison,
  desktop/mobile navigation passed; no page errors.
- Existing HEAD GitHub `tests` and `Workers checks` completed successfully.

Live MCP is excluded from the pass count. Stale/corrupt payload rejection and
timeouts are covered by existing automated fixtures; this run did not corrupt
the live archive or deliberately restart/idle Render. No new product defect was
confirmed to justify a product fix or a defect-specific regression test.

Read-only audit tools (explicitly opt-in, never automatic deployment steps):

```powershell
$env:PYTHONPATH=(Get-Location).Path
python scripts/validate_research_preview.py --env-file <existing-local-env-file>
cd web
node scripts/validate-preview-browser.mjs ../diagnostics/spy-qqq-validation.json
```

Use the project's Python environment and installed Playwright browser. The first
tool reads only the existing API token, never prints it, and writes ignored local
evidence. It selects the first admissible nearby observations for testing, not
the best trade. HTTP client wait bounds do not alter the BFF's 12-second budget.
Run during the session for 0DTE; closed-market or unavailable data is BLOCKED,
not permission to substitute fixtures. Inspect statuses and checks in the capture.

## Next three development priorities

1. **Bind research scenarios to verified contracts and quote provenance.** Carry
   identities, timestamps, freshness and execution-cost assumptions through the
   scenario/comparison path before presenting candidates as actionable economics.
   Preserve explicit hypothetical scenarios as clearly labeled research.
2. **Establish defensible horizon-specific evidence before ranking.** Validate
   session calendars, outcomes, sample adequacy and calibration for 0DTE, weekly,
   monthly and long-dated holding policies. Keep POP, EV and strongest-opportunity
   ranking unavailable when evidence is absent; never derive POP from raw delta.
3. **Close operational release gates and re-run parity.** Reauthenticate the
   existing MCP connection, refresh/discover its current tool schema, and compare
   actual results with website/API. Resolve or explicitly accept Render cold-start
   availability with the owner before production; this sprint authorizes no paid
   infrastructure change. Re-run warm and cold preview checks with the same budget.

No additional Cloudflare secret change is indicated by this run. Existing runtime
URL/token bindings work and demo is disabled. Keep production and DNS unchanged;
do not merge PR #67 until the release gates have been reviewed.
