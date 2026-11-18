# Production options-archive staleness audit

Date: 2026-11-18
Branch: `fix/options-archive-stale-recovery`, based on `main` at `f29ada7`
Scope: production `/workspace` (Trading Workspace) and `/market` (Options Research)
Observed message: "The latest verified options archive is stale. No older snapshot or live data was substituted."

## Conclusion

The message is produced only by Options Research. It is the backend's strict
`current`-mode archive gate (`archive_stale`), not a failed archive refresh and
not data corruption. The archive collector ran successfully throughout the last
session; the newest eligible options observation is from the completed session,
so its age necessarily exceeds the 600-second current-mode ceiling after the
close.

Trading Workspace does not read the options archive. Its only failures can come
from `/v1/market/{symbol}`, `/v1/structure/{symbol}` or the optional
`/v1/research/trade-intelligence/{symbol}` contract. A stale options archive
therefore cannot make the workspace fail. The two surfaces do not share a
failing dependency.

The safe defect is discoverability and contract affordance: Options Research
defaults to current-market mode, and its stale-archive error gave the operator no
explicit way to request the already-supported, separately labeled historical
archive research. The freshness gate itself is correct and remains unchanged.

## Page traces

| Page | Browser component | BFF route | Backend endpoint | Archive dependency |
| --- | --- | --- | --- | --- |
| Trading Workspace (`/workspace`) | `web/src/components/workspace/TradingWorkspace.tsx` -> `normalizeMarketResponse()` in `web/src/lib/workspace-evidence.ts` | `GET /api/market` -> `getMarketSnapshotServer()` in `web/src/lib/alphaos-server.ts` | `GET /v1/market/{symbol}` and `GET /v1/structure/{symbol}?snapshot_id=...`; optional `GET /v1/research/trade-intelligence/{symbol}` | None |
| Options Research (`/market`) | `web/src/components/market/MarketResearchPanel.tsx` | `POST /api/research/market` -> `marketRequest()` in `web/src/app/api/research/market/route.ts` | `POST /v1/research/market` -> `ArchiveResearchService._run()` in `alphaos_api/research2.py` | Required: latest verified Supabase `option_snapshots` row plus its private Storage object |

`web/src/app/api/market/route.ts` returns `market_evidence_unavailable` or
`market_closed`; it never returns `archive_stale`. The archive mapping exists
only in `KNOWN_UPSTREAM_CODES` and the error table of the research route.

## Archive read path and freshness rule

1. `alphaos_api/research2.py:24` defines `MAX_CURRENT_ARCHIVE_AGE_SECONDS = 600`.
2. `ArchiveResearchService._read()` (`alphaos_api/research2.py:144-162`) reads
   `ALPHAOS_ARCHIVE_MAX_AGE_SECONDS` (default `600`) and clamps it with
   `min(configured, 600)`. A deployment may lower the window, never raise it.
3. `modules/supabase_archive.py::read_latest_option_snapshot()` selects the
   newest `provider=Public`, `symbol=<SPY|QQQ>` row with
   `observed_at <= as_of` and `created_at <= as_of`, ordered by `observed_at`
   then `id`.
4. In `current` mode, `age = now - observed_at`; `age > max_age_seconds` raises
   `ArchiveUnavailable(..., code='archive_stale')`. Future-dated rows are also
   rejected.
5. `historical` mode removes only that age ceiling (`max_age_seconds=None`).
   Path, symbol, provider, session, observed-at, slot, checksum, gzip, payload,
   quality and completion checks are unchanged.
6. `alphaos_api/research2.py::_run()` reads and verifies the archive before any
   history or candidate work, so a stale current observation stops the request
   with `archive_stale` and no fallback. `tests/test_after_hours_research.py`
   asserts this, including that the history loader is not called.
7. `web/src/lib/archive-observation.ts` independently caps accepted current
   freshness at 600 seconds; the BFF also requires `max_age_seconds === null`
   for historical responses.

## Archive and ingestion evidence

- Workflow: `.github/workflows/intraday-archive.yml`, dispatched by the external
  five-minute cron described in `docs/intraday_scheduler.md`. The workflow has no
  native schedule and gates on the NYSE calendar.
- On 2026-11-17 the workflow completed successfully throughout the session:
  12 successful dispatches between 19:00Z and 20:00Z (14:00-15:00 ET), including
  runs 3370 (`19:50:44Z`) and 3371 (`19:55:31Z`), followed by successful
  post-close dispatches at 21:50:42Z and 21:55:30Z. All report
  `conclusion: success` on `main`.
- Last eligible collection slot: 15:55 ET = 20:55Z on 2026-11-17. Collection
  crossing the 16:00 ET close is skipped, so no later snapshot can exist for the
  session.
- At the observed failure time (2026-11-18 04:56Z = 2026-11-17 23:56 ET), the
  newest possible observation was already about 8 hours (≈28,860 seconds) old,
  roughly 48 times the 600-second current-mode ceiling. The exact production row
  timestamp cannot be read from this environment because the Supabase
  service-role credential is server-only and Netlify Edge Access protects
  `/api/health`.

This is a historical-research freshness-gating outcome, not a refresh outage:
ingestion succeeded, the latest verified snapshot exists, and only the
current-mode age policy rejects it.

## Fail-closed behavior preserved

- No freshness threshold was changed; 600 seconds remains the maximum.
- No older snapshot is substituted. Historical mode reads the same newest
  verified row and removes only the age ceiling.
- No live quote, chain, price, probability, EV, or candidate is synthesized.
- Historical candidates keep their existing non-actionable status and labels
  (`historical_economics.eligible_for_consideration` is false).
- Current mode continues to fail with `archive_stale` without any automatic
  fallback.

## Smallest safe fix

`web/src/components/market/MarketResearchPanel.tsx` now retains the failure code
in its error state. When the request was made in current mode and the backend
returns `archive_stale`, the error panel explains the 600-second current-mode
window and offers one explicit action: **Use verified historical archive**.

The action updates the research-mode control to `historical` and submits a new
request. It is still an explicit historical request, matching the existing
contract ("Historical archive research must be requested explicitly"), the
existing select control, and the backend/MCP documentation. Nothing is fetched
or displayed automatically, so an in-session refresh failure is never masked by
historical evidence.

No backend, threshold, schema, authentication, execution or candle-display
behavior changed.

## Regression coverage

- `web/tests/browser/navigation.spec.ts`
  - Stale current archive plus valid historical market/archive evidence and zero
    candidates: one current request, explicit action, then a historical request;
    observation time and age render; historical banner renders; no current
    claim; no candidates promoted.
  - Stale current archive plus missing historical evidence: the explicit action
    surfaces `archive_missing`, no result and no historical banner.
  - Fresh current options evidence: current result renders, no stale recovery
    action, exactly one request.
- `web/tests/browser/workspace.spec.ts`
  - A mocked stale options archive does not suppress the verified closed-session
    market/structure workspace: `LAST VERIFIED SESSION`, the historical notice,
    spot and support/resistance remain visible, and no archive error appears.

## Verification

Run on 2026-11-18:

- `npm run typecheck` - passed.
- `npm test` - 304 passed, 0 failed.
- `npm run build` - production build passed.
- Playwright (`--workers=1`) - 75 passed, 0 failed. This includes the new
  stale-recovery, missing-historical and fresh-current cases and the workspace
  independence case. Parallel workers exceed this VM's memory; the single-worker
  run is an environment constraint, not a product setting.
- Focused Python (`test_after_hours_research.py`, `test_archive_read_path.py`,
  `test_research2_api.py`) - 97 passed. The existing Python suite already covers
  strict current-mode refusal after close/weekend/holiday, historical success at
  the original observation with non-actionable candidates, and missing/corrupt
  historical evidence.
- Full Python suite on this branch in two file groups - 933 + 765 = 1,698 passed,
  1 skipped, 64 subtests passed.
- `python scripts/check_deployment_boundary.py` - passed (496 tracked files).
- `npm audit --omit=dev --audit-level=moderate` - 0 vulnerabilities.
- `npm audit --audit-level=moderate` - 0 vulnerabilities under both npm 11.20.0
  and npm 10.9.8 (the version used by CI). The earlier dev-only picomatch
  advisory (`GHSA-fc5q-39xc-vjpf` / `CVE-2026-112366`) is resolved by migrating
  the frontend from `tailwindcss@3.4.19` to `tailwindcss@4.3.5`, which removes
  picomatch from the dependency tree. Audit thresholds and the CI workflow were
  not changed.

## Owner-only production checks

Netlify Edge Access still blocks unauthenticated `/workspace`, `/market` and
`/api/health`. With the owner session:

1. Read `/api/health`: `backend_target` must be `production`,
   `configuration` ready, `demo_enabled` false, `mode` read_only.
2. Open `/market`, confirm the stale current-mode message, use the explicit
   historical action, and verify the displayed observation timestamp is the
   newest verified session slot and that candidates are labeled historical.
3. Open `/workspace` and confirm the market/structure evidence loads
   independently of the options archive.
4. If the workspace still fails, capture the Netlify bridge request ID. That is
   a market/structure or trade-intelligence failure, not an archive failure.
