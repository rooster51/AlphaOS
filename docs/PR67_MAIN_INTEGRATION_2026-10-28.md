# PR #67 integration with production main — October 28, 2026

This is the historical early-morning assessment. The later
[release-preparation report](PR67_RELEASE_PREPARATION_2026-10-28.md) supersedes
its Preview configuration and live-backend/freshness blockers. No Render change
was made by this work; the later live backend exposed the required contract.

PR #67's five commits were rebased onto merged PR #70,
`0c2a4b38eb08129b42de27c2c6689991e606a1f2`. No textual conflicts occurred.
This report records local checks and read-only infrastructure inspection; it is
not a deployment or approval to merge.

## Integration decisions

- `StructureWorkbench.tsx` is identical to updated main, including the verified
  archive controls, saved references and quote-provenance display.
- `structure-bridge.ts` retains main's provenance error codes and exact response
  validation. Its only hosting changes replace Node environment reads with
  request-time `getServerConfig()` and safe presence diagnostics.
- Backend modules, entry-evidence code, REST/MCP schemas and Python tests are
  unchanged from main. This includes the PR #70 pytest 9.2 fixture-state fix.
- The market deadline remains **12,000 ms**. Worker configuration cannot enable
  synthetic fallback even if its demo binding is incorrectly set to true.
- New compiled-Worker tests verify SPY/QQQ provenance and comparison forwarding,
  reject missing/stale/mismatched evidence, and preserve explicit archive error
  codes. Test fixtures are synthetic, not evidence of live trading readiness.

## Local checks

Node **22.23.0** was used, matching the repository and CI configuration.

| Check | Result |
| --- | --- |
| TypeScript / generated runtime and route types | PASS |
| Website unit suite | **182 passed** |
| Next.js production build | PASS |
| Next.js browser suite | **45 passed** |
| Production Worker build / artifact validation | PASS |
| Production compiled-Worker tests | **7 passed** |
| Production Worker browser suite | **45 passed** |
| Preview-context Worker build / artifact validation | PASS |
| Preview compiled-Worker tests | **7 passed** |
| Preview Worker browser suite | **45 passed** |
| Public asset credential scans | **23 assets checked per context**, PASS |
| Full dependency audit | **0 vulnerabilities** |
| Relevant Python integrations under pytest 9.2 | **187 passed** |

Python coverage includes fixture restoration, provenance/entry integration,
entry evidence, structure economics, REST/OAuth MCP and website fixture parity.
GitHub's complete Python and website/Workers workflow results must also pass on
the pushed rebased head. No deployment command is used for artifact validation,
including Preview output. The compatibility scan retains its documented partial
App Router development StrictMode limitation; used Next.js imports are supported.

## Confirmed infrastructure state and live checks

### Cloudflare build integration does not match the intended Worker

Read-only API inspection found two different resources:

| Resource | Actual setting |
| --- | --- |
| Repository source config | `web/cloudflare.config.ts`, Worker **alphaos-web** |
| GitHub-connected Worker | **alphaos**, repository `rooster51/AlphaOS`, production branch `main` |
| Connected production root | `/web` |
| Connected production build | `npm ci && npm run cf-typegen && npm run typecheck && npm test && npm run build:vinext && npm run check:workers` |
| Connected production deploy | `npm run deploy:workers` |
| Connected preview root | **`/`** |
| Connected preview build | **empty** |
| Connected preview deploy | **`npx wrangler preview`** |
| `alphaos-web` GitHub build configuration | **None (API 404)** |
| `alphaos-web` production deployment | **None** |
| Existing `alphaos-web` PR preview | Latest deployed tag **b93c2a2**, not this rebased head |

The source uses the pinned cf CLI / native vinext Vite integration, not a
Wrangler configuration. Correct settings for the intended project are root
`web`, Node 22.23.0, the build command above, production deploy
`npm run deploy:workers`, and Preview deploy **`npm run preview:workers`**.
The latter builds in Preview context itself. Never run the production deploy
command against Preview output or reuse production artifacts with `--prebuilt`.

Before a production merge, reconcile the connected project with `alphaos-web`,
correct Preview root/commands and confirm runtime bindings on the intended
production and preview resources. Existing build-variable names on `alphaos`
do not prove runtime bindings on `alphaos-web`. No setting or credential was
changed during this work. Main pushes can trigger the existing external build
integration, so local/Actions green checks alone are not a production release gate.

### Render is reachable but runs an older backend

Render service `srv-daqillmgekts73ak0mj0` is on **Free**, tracks `main`, and has
**automatic deployment disabled**. Its live deployment is
`76a6a1696d007aeb6aab31fa33c6dad847608688` (PR #64), not merged PR #70.
The live OpenAPI confirms that `StructureLeg` has only type/strike/qty and
`StructureRequest` has no `market_data` reference. The updated verified
structure/comparison contract therefore cannot be validated against that live
backend. No Render deployment or restart was performed.

The first direct health probe timed out after 30 seconds; the next OpenAPI probe
succeeded after about 13 seconds. This is consistent with the previously
confirmed Free cold-start limitation, not proof of a new app-level timeout bug.
The frontend budget was not increased.

The existing deployed Cloudflare preview reports runtime `cloudflare`, both API
bindings present, configuration ready and demo false. Authenticated direct Render
observation calls for SPY and QQQ returned **503 `archive_stale`**. Its preview
observation and market proxies preserved **502 `archive_stale`** with no research
payload. Authentication and connectivity succeeded; fresh current data did not.

The newly compiled Preview artifact was also run locally in workerd with native
runtime bindings and a Node outbound forwarder to the actual Render service.
Both symbols returned the same explicit `archive_stale` error, without research
or synthetic substitution, in about 1.6 seconds / 0.3 seconds. Backend-correlated
request IDs: SPY `d27d31406d4a40569238b848a78c1642`,
QQQ `1c7d5f12bb354ce596f98d1da8f95cf3`. This is local artifact-to-Render
validation, not a claim that the rebased preview has been deployed at the edge.
No live option prices, contracts, probabilities or expected values were invented.

## Release conclusion

**Code build readiness: PASS locally; final Actions results belong to the pushed
head. Production merge/deploy readiness: BLOCKED by external configuration and
backend version/freshness gates.**

Required before production:

1. Reconcile the Cloudflare connected Worker and correct its Preview settings;
   preserve all existing credentials and keep production release explicit.
2. Stage the main/PR #70 backend contract and verify fresh SPY/QQQ provenance and
   comparison with the updated website and authenticated MCP. An old backend or
   stale archive cannot establish that positive path.
3. Verify the rebased deployed Preview after an approved Preview release. Review
   cold-start availability against the existing budget; retain Render rollback
   capacity and leave DNS unchanged until separately approved.

PR #67 stays open. No new PR, merge, production deploy, credential change,
collector change, infrastructure upgrade or timeout relaxation was performed.
