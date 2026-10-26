# AlphaOS current status (2026-10-24)

This is the single dated status record. It states what is in the repository, what
has been **reported** about production, and what remains **unverified**. It does
not replace any historical report, benchmark or audit: those stay as dated
evidence with their original conclusions.

Baseline: `main` = `76a6a1696d007aeb6aab31fa33c6dad847608688` (merge of PR #64,
2026-10-22). Confirmed against the local checkout and `git ls-remote origin` on
2026-10-24.

## Completed and merged

| PR | Merge commit | Application commit(s) | Change | Record |
| --- | --- | --- | --- | --- |
| #61 | `8a374fb` | `3772a36` | Bounded research pipeline work, shared constructor budget, cooperative cancellation on client disconnect | [research performance](ISSUE60_RESEARCH_PERFORMANCE.md) |
| #62 | `b9697eb` | `27d2ac3` | Reduced historical overhead (calendar/feature reuse, chart materialization, response aliases) and fixed disconnect propagation | [reliability follow-up](ISSUE60_RELIABILITY_FOLLOWUP.md) |
| #63 | `ff0a42e` | `e60ef57`, `cc4bda2` | Additive `POST /v1/research/observation` dashboard contract and pinned `orjson` response encoding | [dashboard contract](ISSUE60_DASHBOARD_CONTRACT.md) |
| #64 | `76a6a16` | `54dcf5b`, `931fb11` | Buffered sanitized response encoding (less retained graph/GC work) and Next.js audit patch to 16.4.1 | [retained response graphs](ISSUE60_RETAINED_RESPONSE_GRAPHS.md) |

Repository facts supporting these rows: commit messages via `git log`, the
per-change documents above, and `tests/test_issue60_reliability.py`,
`tests/test_buffered_response.py`, `tests/test_research_performance.py`,
`tests/test_website_mcp_parity.py` and `web/tests/observation-contract.test.mjs`.

Current API surface: **20 OpenAPI paths** (`/health` plus **19 authenticated
`/v1` operations**). `tests/test_architecture_consolidation.py` asserts this exact
set, including `/v1/research/observation`. The MCP server still exposes **17
tools**; the observation route is website/dashboard-only and has no MCP tool.

## Reported production state (owner-confirmed, not independently verified here)

- Production baseline is `76a6a16`; **PR #64 has been deployed**.
- No Render control-plane read, deployment log, production HTTP request, Supabase
  query or provider call was made while preparing this record.
- Recorded deployment evidence in the repository is older by design:
  `docs/DEPLOYMENT.md` observed both user-facing services at `d1c9e08` on
  2026-10-16; the Issue #60 body reported both at `dd1196b` on 2026-10-21. Those
  are dated observations, not the current live SHA.

## Unresolved: Issue #60 and Milestone 1

Issue #60 remains **open**, and Milestone 1 is **not accepted**.

- The website bridge deadline is still **12,000 ms** for full research; the
  dashboard's observation request uses its own 14,000 ms upstream budget.
- Acceptance requires production evidence the repository does not contain:
  correlated request IDs across backend stages and website completion, complete
  response bodies below 12 seconds with headroom, cold and concurrent SPY/QQQ
  runs, and fail-closed checks. Every `docs/performance/issue60-*.json` artifact
  tracked on `main` was committed on 2026-10-21, before the deployment of
  PRs #61-#64; those files are synthetic fixtures and pre-change production
  traces, not post-deployment acceptance.
- Fixture timings, including the constrained 0.15-CPU runs in the PR #64 record,
  are change evidence, not production acceptance.
- The bridge timing diagnostic experiment is complete and **rejected** (owner
  confirmation). Diagnostic work is not part of `main`'s history as reviewed:
  the five `diagnostics/issue60-*` branches stand apart, and the newest of them
  (2026-10-23) records another rejection. No further Issue #60 optimization
  experiments are authorized.

## Current development restrictions

- No new Issue #60 performance work without explicit authorization.
- Public engineering is reviewing permission for historical market-data retention
  and replay. Until that review concludes, entry-aligned historical option
  evidence cannot be assumed available.
- Supabase capacity has been verified; diagnostic capture in Supabase is **not**
  authorized.
- Trade-journal SQL remains an unapplied deployment artifact per its milestone
  record. No identity, persistence, journal-write, order-execution or brokerage
  path is enabled.
- Research remains read-only. Missing evidence stays unknown; no fallback quotes,
  fabricated candidates or relaxed freshness gates.

## Documentation corrected in this change

Only demonstrably outdated currency claims were changed. Historical reports keep
their original conclusions and dates.

| Document | Stale claim | Correction |
| --- | --- | --- |
| `docs/ARCHITECTURE.md` | Presented as current the 2026-10-16 count of 19 operations / 18 `/v1` and 48 remote heads | Dated currency note: 20 paths / 19 `/v1` after the observation route; 68 remote heads on 2026-10-24; branch JSON not regenerated |
| `docs/DEPLOYMENT.md` | Dependency table predates `orjson==3.13.0`; website listed as Next 16.4.0; deployment recorded at `d1c9e08` | Dated currency note: `orjson` pinned in `requirements-api.txt`, Next 16.4.1, production baseline reported at `76a6a16` and unverified |
| `docs/ISSUE60_RESEARCH_PERFORMANCE.md` | "Milestone 1 remains open" with no merge/deployment state | Dated status header: merged as #61; deployed per owner report; acceptance still open |
| `docs/ISSUE60_RELIABILITY_FOLLOWUP.md` | Same; "This change is not deployed" | Dated status header: merged as #62; deployed per owner report |
| `docs/ISSUE60_DASHBOARD_CONTRACT.md` | "Not deployed" | Dated status header: merged as #63; deployed per owner report |
| `docs/ISSUE60_RETAINED_RESPONSE_GRAPHS.md` | "No merge or deployment is authorized" | Dated status header: merged as #64 and deployed per owner report; the statement was accurate when written |
| `docs/MCP.md` | "The new tools are not deployed by this milestone" | Dated note: all 17 tools are in `main`; live ChatGPT connector state unverified |
| `ALPHAOS_2_BUILD_STATUS.md` | "Current release status updated 2026-10-14" | Relabelled as a historical record that points here |

## Deliberately not corrected

These remain dated evidence, not current-state documentation:

- `docs/architecture-inventory.json` and `docs/architecture-branches.json` are
  static 2026-10-16 snapshots. Regenerating them is a separate, reviewable change.
- `docs/RELEASE1_GATE.md`, `docs/RELEASE1_*.md`, `docs/PRODUCTION_READINESS.md`,
  `docs/RELEASE2_READINESS_AUDIT.md`, `docs/ALPHAOS2_API_MCP.md` and the phase
  reports record reviews at named commits. Their numbers (the 760-test Release 1
  record and the 1,119/1,153/1,171/1,184 per-change runs, Next 16.4.0, staging
  SHAs) belong to those reviews.
- Test totals differ per change document because each records its own full run at
  that commit; none is a current suite total. This review did not execute the
  suite.

## Unverified live conditions

- Exact live SHAs on the backend and website services.
- Whether the ChatGPT MCP connector has been reconnected since the 2026-10-19
  `UNAUTHORIZED` observation, and its current tool declaration.
- Live Supabase schema, RLS state and archive contents.
- Real end-to-end website latency under the current deployment.
- The outcome and timing of Public's retention/replay review.

Nothing above should be read as production acceptance for Issue #60.
