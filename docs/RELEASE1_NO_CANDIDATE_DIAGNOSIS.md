# Release 1 backend no-candidate diagnosis

Date: 2026-10-13. Branch: `web/research-api-integration`, starting
`c2d4645afdf2da361a2b8df6e7fc78f1d1864563`, existing draft PR #28.
No website implementation changes. The branch was checked out in a separate
worktree; pending Release 2 edits were preserved in their original worktree.

## Actual staging observations

Read-only POSTs to the user-provided staging website's `/api/research/market`
used its existing server-side authenticated API bridge. No credentials were
retrieved or changed. These are actual responses, not fixture results.

| Request | HTTP / result | Generated candidates | Candidate exclusions | Capital exclusions |
| --- | --- | --- | --- | --- |
| QQQ, 2026-10-30, $20, width 1 | 502 bridge / archive_research_unavailable | Not reached | Not reached | Not reached |
| SPY, $150, width 1 | 200 / no_candidate | 0 | 0 | 0 |
| QQQ, $300, width 1 | 200 / no_candidate | 0 | 0 | 0 |
| QQQ, $300, width 2 | 200 / no_candidate | 0 | 0 | 0 |

SPY observation: `2026-10-13T14:55:55.553714+00:00`.
QQQ observation: `2026-10-13T14:55:59.204875+00:00`.
Both report complete archives. Both list requested expirations October 13, 14,
15, 16, 19 and 20. October 30 is absent, consistent with the unchanged seven-day
collector horizon. No expiration was substituted. The API returns 422 internally;
the existing website bridge maps the generic archive error to HTTP 502.

For the three default-expiration cases, the exact classification evidence was
`Completed market history was not supplied.` API caveats confirm the daily history
loader failed. Direction, movement, premium and volatility remain unknown. Time
is standard. No routing rule matches, so constructors and capital filters never
run. Neither width nor the capital ceilings explain these observed empty results.

The archive reader succeeds independently of Public daily-history authentication.
The staging blueprint declares archive credentials but no Public credentials.
This is a configuration hypothesis, not proof that effective environment values
are missing: existing code swallowed all history loader failures. No secret values
or environment settings were inspected. Provider authentication, rate limiting,
SDK/history validation or missing configuration remain distinguishable only after
the new safe diagnostics are available or an operator checks them independently.

## Targeted changes

- Routing sufficiency now tests actual route matches. Previously any known
  dimension, including standard time alone, incorrectly reported sufficiency.
- Session diagnostics separate route, generated, accepted, candidate-rejection,
  contract-rejection and capital-rejection counts. Blocking reasons identify
  absent history/no matching routes. Counts are scoped to this snapshot and the
  existing constructors, not an exhaustive count of possible option structures.
- Debit construction reports missing quotes, insufficient observed delta contracts,
  or no valid pair. Selection, price assumptions and payoff formulas are unchanged.
- API history-loading diagnostics expose only fixed Public error codes; arbitrary
  exception text and diagnostics remain private. `loaded` means the provider
  returned data; classifier validation remains separately authoritative.
- Missing requested expiration now returns HTTP 422 with
  `archive_expiration_unavailable`. Existing archive checksum/freshness guards and
  all other failure paths remain intact. The unchanged website currently maps this
  new API code to its generic rejected-request display; frontend work is deferred.

All strategy families, objective/classifier separation, max-loss capital filters,
fees, archive access, authentication and MCP tool contracts are preserved. No
fallback market data, estimated Greeks, fabricated prices or forced routes added.

## Tests and limits

Focused Python 3.12.14 command:
`python -m pytest -q tests/test_no_candidate_diagnostics.py tests/test_opportunity_session.py tests/test_opportunity_router.py tests/test_opportunity_classifier.py tests/test_market_archive_adapter.py tests/test_run_market.py tests/test_research2_api.py --tb=short`

Result: **108 passed in 16.05 seconds**. Includes REST/MCP parity and authentication,
actual route sufficiency, missing history/delta, unavailable expiration, capital
rejections and allowlisted error output.

Synthetic controlled-history/quote tests generate one debit candidate for each
requested symbol/capital/width case: $20 rejects it (fixture risk $50); SPY $150
and QQQ $300 width 1 accept one ($50 risk); QQQ $300 width 2 accepts one ($100 risk).
These numbers prove filtering behavior, not current market opportunities. Missing
history fixtures yield zero routes and zero candidates for all four configurations.

## Operational blocker and publication gate

An operator must restore/verify completed Public daily history in the staging API
using its supported server-side configuration. Do not weaken classification to
compensate. October 30 cannot be researched from the observed archive; choose an
actually archived expiration or separately authorize a collection-horizon change.
Neither recovery was performed here.

Read-only Render inspection, explicitly authorized for My Workspace, found
`alphaos-api-staging` autoDeploy=yes, trigger=commit, on this branch.
`alphaos-web-staging` autoDeploy=no. Therefore pushing this branch would deploy the
API. Keep the tested commit local until deployment approval or an operator disables
auto-deploy. Do not modify Render settings as part of this milestone.

No merge, push, deployment, collector change, production mutation, credential
change or database migration. PR #28 stays unchanged until publication is approved.

Full Python 3.12.14 validation: `python -m pytest -q --tb=short` — **642 passed, 40 subtests passed in 131.06 seconds**. `git diff --check` passed. No test expectations were weakened.
