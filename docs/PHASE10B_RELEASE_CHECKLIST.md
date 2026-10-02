# Phase 10B release audit and production smoke test

Audited source baseline: `fff856b36c41b45806fe4bc12deccdc6d0a31d24`, draft PR #10,
base `phase9-index-support`. PR #9 remains unmerged. Only the isolated chain-quality
helper/integration/tests were carried from Phase 10A; no intraday engine or gate code
is in this lineage. One garbled DTE dash in MCP instructions was corrected.

Authoritative implementation: `alphaos_api/positions.py`; API wiring in `app.py`,
tools in `mcp_server.py`, disclosure-only consent text in `mcp_auth.py`, and
`modules/active_trades_workspace.py` / `pages/12_Active_Trades.py`.
The SQLite `positions` table has immutable entry JSON, request-id idempotency and
atomic explicit closure. No brokerage write path exists. The MCP surface has 19
tools: 14 existing research tools plus five tracking tools. Only record/close are
annotated as mutations. OAuth protocol/security behavior is unchanged.

## Deployment prerequisites (manual, not performed by this audit)

Use a persistent disk attached to the single Render service instance. Example mount
`/var/data`, environment `ALPHAOS_POSITIONS_DB=/var/data/alphaos/active-positions.sqlite3`.
The path is configurable, not hardcoded; local/test default remains
`data/active-positions.sqlite3`. An ephemeral/free filesystem is not sufficient for
durability across redeployment/replacement. Confirm disk configuration, write access,
SQLite backup/restore and exact release SHA before enabling journal use. Infrastructure
was not changed or certified here. Streamlit must point to the same HTTPS API with its
server-side owner credential, not maintain a separate database.

## Exact production smoke test (pending approved deployment)

1. Record deployed SHA and check `/health`; confirm OAuth metadata and unauthenticated
   `/mcp` rejection. Authenticate and list the expected 19 tools for Phase 10B.
2. During a usable quote session, explicitly select an available PCS/CCS and record a
   clearly labeled test entry through POST `/v1/positions`. Use a unique request UUID,
   explicit quantity, user-declared credit and timezone-aware timestamp. This is local
   test tracking, not a claim of brokerage execution. Save position ID and entry JSON.
3. Retry the identical request; verify the same position ID and no duplicate record.
4. GET `/v1/positions` and `/v1/positions/{id}`; confirm active status and exact identity.
5. GET `/v1/positions/{id}/monitor`; inspect timestamps, selected-leg quality and quote
   methodology. Reproduce P/L from raw inputs if valuation is available; stale/missing
   observations must not produce a fabricated P/L.
6. Restart the service manually without removing its disk. Re-authenticate if required
   by existing OAuth lifecycle. Retrieve/list the position and compare entry JSON exactly.
7. Monitor again; verify entry JSON is unchanged, current timestamps advance and
   underlying/contract identity remains correct. Measure actual request latency separately
   from full research; fixture timings are not production performance.
8. POST `/v1/positions/{id}/close` with explicit test close amount, cashflow direction and
   timestamp. Verify closed status and declared economics. Retry identically; no duplicate
   closure. A conflicting closure must fail.
9. Confirm GET `/v1/positions/{id}` still retrieves entry and closure, while the active
   list excludes it. Restart again and verify the closed record persists.
10. Verify Streamlit Active Trades: entry confirmation, correct position selection,
    refresh, primary valuation/quality, frozen Entry Evidence, explicit close form and
    retrieval of closed ID. Do not expose credentials in widgets/output.
11. Refresh ChatGPT tool definitions, verify local-tracking consent wording and perform
    equivalent record/list/get/monitor/close/get operations on a separate labeled test
    record. With multiple matches, require selection rather than guessing. Verify no
    brokerage operation occurred. Keep test records clearly labeled; no automatic deletion.

Do not declare production verification until this sequence has actually passed. This
source audit is a release preparation step, not authorization to merge or deploy.
