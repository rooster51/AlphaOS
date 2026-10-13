# Release 1 consolidation audit

Audit date: 2026-10-13. GitHub inventory covers every PR numbered 1–38, plus separate review of #39. #27 is an issue, so there are 37 PRs in that range.

Integration base: `7f7ef53c85151711ef5fdc3c5d092a7a3e6d84cb` (current main at fetch).
Integration branch: `release/release1-consolidation`.
Exact source heads, base branches, merge SHAs and check URLs are recorded in [release1_pr_inventory.json](release1_pr_inventory.json).

## Dependency map and reconciliation

- Release stack: #19 → #26 → #28 → #36 → #37 → #38. #29 adds independent authenticated POST/read-only contract regressions.
- Main already contains #1–3, #12–17 and #20–25. Every recorded merge commit is reachable from current main.
- The Release stack forked before #20–25. A local three-way squash reconciliation onto current main preserves historical economics, shared evidence comparisons and quote latency/freshness. It did not replace main with the older branch. No text conflicts occurred.
- #4 → #5 → #7 → #8 are historical API/MCP lineage. Their core capabilities were selectively carried forward by #16/#25, despite those original PRs remaining open. #5 OAuth, quote freshness and quote latency modules match main byte-for-byte; #7's changes in main add later index metadata. Unique #8 audit workflows/scripts are preserved on that branch, not activated here.
- #8 → #9 and #8 → #10 → #11 remain separate intraday/monitor/journal lineage.
- #18 identity/tenancy is independent and excluded, including its SQL/security infrastructure.
- #30 → #31; #31 + #32 → #33. #33 includes additional temporal checks; these are Release 2 work, not silently included.
- #34 normalization is independent. #35 overlaps historical evaluator/strategy work and needs separate reconciliation with #33/#34.
- #39 is a one-file candidate details UI delta based on #38, head `415cd27d6003027b541370527587e56c26b875d6`. Its native details/summary and full-object rendering were inspected and excluded. CI pytest/web passed. No changes to its branch or PR.

## Incorporated changes

- Website foundation, navigation and explicit unavailable states from #19/#26/#28.
- Fail-closed market evidence: timestamp/freshness, symbol, schema and snapshot pairing; no fixture candidates in normal production flow.
- Server-side authenticated POST bridge to the existing /v1/research/market, preserving the full research envelope and non-tradable status.
- Archive missing/stale/configuration diagnostics, while retaining checksum, identity and age checks.
- #36 route sufficiency and construction/capital rejection counts; #37 fixed-code Public history failure classification.
- #38 canonical PUBLIC_API_SECRET and PUBLIC_ACCOUNT_NUMBER declarations with sync:false, no values; operational recovery instructions and regression tests.
- #29's three HTTP/authentication/non-executable regression cases.
- One integration repair: carry archive_expiration_unavailable through the website error allowlist and display its specific message. Tests cover the bridge and browser.
- A bridge regression verifies that main's additive historical economics, holding policy and new history diagnostics survive unchanged.
- Duplicate web/** push-only CI from #26 is intentionally omitted; existing tests.yml contains backend and website jobs including browser tests. No collection schedules change.

No runtime changes to OAuth, MCP registration, provider HTTP parsing, research mathematics, collector configuration or Supabase schema. Existing market/structure/comparison economics and quote protections remain on main's implementation. Demo fixtures remain isolated behind explicit demo mode; deployment requires that mode unset/false.

## Disposition table

“Safe to close” is a recommendation after successful integration, not an action taken. “Ready for later review” is not merge approval or live-data verification.

| PR | Subject | GitHub status | Disposition | Evidence / action |
| --- | --- | --- | --- | --- |
| #1 | Phase 5: distribution-conditioned option economics | Merged | Already merged | Merge recorded by GitHub; retain current main. |
| #2 | Phase 5.2: Option Economics robustness UI | Merged | Already merged | Merge recorded by GitHub; retain current main. |
| #3 | Phase 6 MVP: price structure and forward distribution research | Merged | Already merged | Merge recorded by GitHub; retain current main. |
| #4 | Phase 7: authenticated read-only AlphaOS research API | Open (draft) | Superseded; safe to close after integration | API foundation reused by #16; current main supersedes old implementation. |
| #5 | Phase 8: read-only MCP research with quote freshness safeguards | Open (draft) | Superseded; safe to close after integration | MCP/OAuth and quote protections reconciled by #16/#25; authentication/freshness files match. |
| #6 | Clarify missing Public API secret in daily archive | Open | Deferred outside Release 1 | Legacy daily-workflow diagnostic has unique changes; old automatic schedule remains disabled. |
| #7 | Phase 9A: unified vertical research and symbol orchestration | Open (draft) | Superseded; safe to close after integration | Unified research retained in main, subsequently extended with index metadata. |
| #8 | Phase 9: direct SPX and XSP unified trade research | Open (draft) | Deferred; partially incorporated | Index research/registry retained in main; unique index audit scripts/workflows remain outside release; preserve branch. |
| #9 | Phase 10A gate: explicit option quote coverage and intraday capability audit | Open (draft) | Deferred outside Release 1 | Intraday capability/quality gate; do not merge historical branch wholesale. |
| #10 | Phase 10B: Active Trade Monitor with immutable entry evidence | Open (draft) | Deferred outside Release 1 | Active trade monitoring, not website release. |
| #11 | Phase 10C: Trade journal and descriptive realized performance | Open (draft) | Deferred outside Release 1 | Journal depends on #10; identity/persistence approval still separate. |
| #12 | AlphaOS 2.0: trade ledger foundation and archive-backed research | Merged | Already merged | Merge recorded by GitHub; retain current main. |
| #13 | Add Public intraday market archive v1 | Merged | Already merged | Merge recorded by GitHub; retain current main. |
| #14 | Use external scheduling for the existing GitHub intraday collector | Merged | Already merged | Merge recorded by GitHub; retain current main. |
| #15 | Preserve active intraday collection across scheduler heartbeats | Merged | Already merged | Merge recorded by GitHub; retain current main. |
| #16 | Expose AlphaOS 2.0 archive research through read-only API and MCP | Merged | Already merged | Merge recorded by GitHub; retain current main. |
| #17 | Pin Render and CI to Python 3.12.14 | Merged | Already merged | Merge recorded by GitHub; retain current main. |
| #18 | AlphaOS 2.0: isolated identity boundary and MCP readiness preflight | Open (draft) | Deferred outside Release 1 | Identity/tenancy work and SQL require separate security review and approval. |
| #19 | AlphaOS website: Next.js frontend foundation (draft) | Open (draft) | Incorporated | Website foundation through #26/#28; production fixture fallbacks removed by #26. |
| #20 | Add shared historical economics contract and multi-leg scenario evaluator | Merged | Already merged | Merge recorded by GitHub; retain current main. |
| #21 | Add fail-closed adapter for historical scenario evidence | Merged | Already merged | Merge recorded by GitHub; retain current main. |
| #22 | Integrate validated historical economics into REST/MCP structure research | Merged | Already merged | Merge recorded by GitHub; retain current main. |
| #23 | Share historical expiration evidence across REST/MCP structure comparisons | Merged | Already merged | Merge recorded by GitHub; retain current main. |
| #24 | Expose market discovery economics with fail-closed intraday evidence gates | Merged | Already merged | Merge recorded by GitHub; retain current main. |
| #25 | Release: reconcile production quote freshness with historical economics | Merged | Already merged | Merge recorded by GitHub; retain current main. |
| #26 | Web: fail closed on market evidence and remove production fixture candidates | Open (draft) | Incorporated | Evidence gates, no production fixture candidates, tests; duplicate branch-only CI excluded. |
| #27 | Copilot web validation task | Open issue, not a PR | Not a PR | Retain issue until release acceptance is verified. |
| #28 | Web: introduce read-only research API bridge | Open (draft) | Incorporated | Authenticated read-only POST bridge, navigation, market page, archive errors, staging template. |
| #29 | Test: lock market research HTTP contract and capital gates | Open (draft) | Incorporated | Three HTTP/auth/non-executable contract regression cases; no runtime change. |
| #30 | Plan: guarded NVDA/IWM intraday archive expansion | Open (draft) | Deferred; covered by #33 | Foundation incorporated in #31/#33, not main; close only after later approved #33 integration. |
| #31 | Wire opt-in NVDA/IWM canary into existing intraday collector | Open (draft) | Deferred; covered by #33 | Opt-in canary collector included in #33; no activation in this release. |
| #32 | Harden existing quoted intraday round trips with NYSE session integrity | Open (draft) | Deferred; covered by #33 | Session-safe evaluator included in #33 with further temporal hardening. |
| #33 | Integrate opt-in collector canaries and session-safe intraday evaluation | Open (draft) | Independent; ready for later review | CI green; collector/evaluator integration and private-payload evidence gates remain separate. |
| #34 | Recognize unlabeled long straddles and strangles in strategy comparisons | Open (draft) | Independent; ready for later review | CI green; shape recognition is strategy expansion outside Release 1. |
| #35 | Add historical archive option evaluation | Open (draft) | Deferred outside Release 1 | Historical API/evaluator integration overlaps #33/#34 and needs separate policy/normalization reconciliation. |
| #36 | Release 1: Diagnose missing history and zero-candidate research | Open (draft) | Incorporated | Routing sufficiency and structured no-candidate/history diagnostics. |
| #37 | Release 1: Safe Public history failure diagnostics | Open (draft) | Incorporated | Safe fixed-code history failure classification. |
| #38 | Release 1: declare Public history dependencies and verify configuration failure | Open (draft) | Incorporated | Canonical Public configuration declarations and regression tests. |

All open PR heads had successful pytest checks at audit time; website checks also passed where present. Supabase Preview checks were skipped. These historical results do not replace combined-branch validation.

## Deployment risks and approval gates

1. Earlier read-only staging inspection found Public_API_Secret instead of the canonical PUBLIC_API_SECRET on Linux. No settings were changed; current credentials were not re-inspected during consolidation. An authorized operator must verify/correct the canonical key before live history validation. A secret file does not populate this key.
2. Previous live requests returned backend_timeout at the website and archive_unavailable via MCP. They are unresolved operational gates, not successful candidate tests. The bridge retains its 12-second timeout. Do not extend freshness or timeouts speculatively.
3. Staging website/API and production MCP were running different commits in the preceding audit. Deploy the same approved backend release for equivalent research requests, then compare exact inputs and provenance.
4. The existing staging template uses a 86400-second archive window versus the API default of 600 seconds. This difference is preserved, not promoted to production. Archived observations must never be labeled live/executable.
5. Website currently submits symbol-only requests (backend defaults apply); its bridge also supports capital, width, objective and expiration. Candidate display remains family labels until separately reviewed #39; no claim of complete trading UI.
6. Historical/intraday metrics remain null when evidence is unsupported. No journal/identity deployment, migrations, brokerage actions, paid services or production mutations are part of this release.
7. Render staging template still points at web/research-api-integration. Repointing services, selecting a commit, provisioning canonical environment keys or restarting needs explicit approval; this PR applies none of those operations.

## Recommended merge and cleanup sequence

1. Review this single integration PR against its pinned main base and final CI. Recheck main/source heads before approval if they move.
2. After explicit user approval only, merge this integration PR into main. Do not separately merge the old Release 1 stack and reintroduce obsolete code.
3. After successful integration, separately approve closing #19, #26, #28, #29, #36, #37 and #38 as superseded by this PR. #4, #5 and #7 can also close as already reconciled historical lineage. Preserve all branches.
4. Keep #6, #8–11, #18, #30–35 open. #30–32 can close after a later approved #33 integration, not because Release 1 merged.
5. Rebase/review #39 separately after consolidation. Do not include it automatically.
6. With separate authorization, correct staging configuration and deploy the approved release SHA to staging only. Validate health, actual SPY/QQQ archived research, supported expirations, history diagnostics, capital exclusions and equivalent MCP results. Only then seek production approval.

No PRs were merged/closed and no services, secrets or databases were modified.


## Local validation commands

Python 3.12.14; local Node 24.20.0 (CI uses the prescribed Node 22).

- Full backend: `python -m pytest -q --tb=short` (results recorded below).
- Focused: `python -m pytest -q tests/test_research2_api.py tests/test_market_economics_integration.py tests/test_structure_economics_integration.py tests/test_no_candidate_diagnostics.py tests/test_staging_history_dependencies.py tests/test_public_history.py tests/test_archive_read_path.py tests/test_quote_freshness.py tests/test_mcp_api.py --tb=short`: 211 passed, 11 subtests passed.
- `npm ci --no-audit --no-fund`: existing lockfile installed, no dependency changes.
- `npm run typecheck`: passed.
- `npm test`: 38 passed, zero failures.
- `npm run build`: passed with demo mode disabled and no backend token; no live market evidence fetched for the build.
- `CI=true npm run test:e2e`: 9 Chromium tests passed, zero failures.
- API/MCP import/startup modules and git diff --check: passed.

REST/OAuth MCP parity tests cover actual service orchestration with verified synthetic archive fixtures. Website bridge tests preserve the complete envelope, including diagnostics and historical economics. These tests establish contract compatibility, not real market-data availability. No live request or production validation was performed in this consolidation task.

Full local backend run: 757 passed, 40 subtests passed (353.62s), zero failures.
The three #29 cases were added after that run's collection and passed in the
211-test focused run. Final-commit CI runs all 760 together on Linux.
No test expectations or evidence safeguards were weakened.
