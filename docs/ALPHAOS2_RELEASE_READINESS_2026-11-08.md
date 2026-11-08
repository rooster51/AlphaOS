# AlphaOS 2.0 release readiness — November 8, 2026

**Status: keep #87 and #88 draft.** Ready-instance API checks pass. Actual
authenticated Netlify acceptance and fresh-session workbench economics remain
unverified. The owner accepts free Render wake-up delay; it is an operating
limitation, not a requirement to upgrade, send keep-alives, or extend deadlines.
This checklist supersedes older infrastructure recommendations in the November 6
report. No production deployment, merge, paid change, or charting edit occurred.

## 1. Passed checks and exact revisions

Staging API remains `42e41062fbeadaa8cf3c7f50fc5f442d866decb9`, deploy
`dep-dbmvl3om7kps73cf4a6g`, service `srv-db6mql2d0e5s73atk5e0`,
`https://alphaos-api-staging.onrender.com`. Render auto-deploy is OFF.
PR #88 head is `e346fb8326f6d95fde82e447a20839e54e4e5057`; its final commit
only updates the November 6 report. Main is
`467724bfa7833d92a4b0c637028c9e27fd9a665b`.

Full local Python on staging's exact integration revision: **1,482 passed,
1 skipped, 64 subtests passed** (390.35 seconds). Website checks after the
release-only correlation patch: **239 unit tests**, TypeScript, production
Next build, **61 Chromium passed / 2 skipped** (12.1 seconds).
The patch returns the existing options bridge request ID to the caller and logs
whether the backend echoed it. Its regression first failed with a missing header,
then passed while asserting one authenticated upstream call per comparison batch.
It changes no pricing, authentication, freshness, deadline, or forwarding policy.
This patch is for #87 only and is not yet deployed.

CI on deployed integration: [tests 42247278448](https://github.com/rooster51/AlphaOS/actions/runs/42247278448)
and [Workers 42247278493](https://github.com/rooster51/AlphaOS/actions/runs/42247278493)
passed. #88 head: [tests 42250805424](https://github.com/rooster51/AlphaOS/actions/runs/42250805424)
and [Workers 42250805440](https://github.com/rooster51/AlphaOS/actions/runs/42250805440)
passed. The release patch's exact head and CI are recorded in #87's review body.

Existing deterministic coverage checks all twelve families and custom signed
legs, conservative executable bid/ask entry, fees, signed quantities and contract
multipliers, exact terminal payoff/breakevens, bounded/unbounded loss, capital
constraints, sorting, missing/stale/crossed quotes and response integrity.
Summary/detail tests preserve qualifying candidates, exclusions, ordering,
archive checksums, risk/evidence fields, cancellation and fail-closed behavior.
Slow/incomplete/429 cases are controlled regression fixtures, not new hosted
Netlify observations. No probability, EV, or brokerage buying power is invented.

## 2. Staging evidence and its boundary

November 8 measurements below execute the **actual website route locally** with
local test-session authentication, forwarding with the staging credential to the
real API. They do **not** establish hosted Netlify acceptance. API readiness was
confirmed first: `/health` HTTP 200 in 500 ms. No keep-alive process was used.

| Case | SPY status / total | QQQ status / total | Complete decoded body bytes SPY / QQQ |
| --- | --- | --- | --- |
| Current, $150, automatic width/expiry | 502 / 1,880 ms | 502 / 1,897 ms | 47 / 47 |
| Historical, $150, automatic width/expiry | 200 / 6,819 ms | 200 / 6,849 ms | 385,085 / 444,401 |
| Expiration discovery | 200 / 798 ms | 200 / 270 ms | 509 / 470 |
| Explicit observed chain | 200 / 2,447 ms | 200 / 1,458 ms | 150,146 / 171,392 |
| Comparison first 8 scenarios | 200 / 620 ms | 200 / 555 ms | 4,420 / 4,400 |
| Comparison remaining 5 scenarios | 200 / 633 ms | 200 / 747 ms | 3,682 / 3,662 |

Sunday current requests correctly returned `archive_stale` (upstream 503), no
partial research. Historical selected November 6 and passed complete-body schema
validation: SPY 385 generated / 56 accepted / 329 excluded; QQQ 388 / 73 / 315.
Historical age is intentionally disclosed, not presented as fresh current data.
Observed chains contained 165 calls + 165 puts for SPY, 189 + 189 for QQQ.
All twelve families plus custom signed legs were submitted for each symbol in
bounded 8+5 batches, using actual contract identities. All 26 scenarios correctly
returned `underlying_quote_ineligible`; this verifies the weekend rejection path,
not positive live economic acceptance. Each batch shares its own market evidence;
the two separate batches are not claimed to share an identical snapshot.

Correlated historical IDs (start approximately 19:37:48 UTC):

- SPY `110713c01dcf4d7192ce1a47acfedda3`
- QQQ `ad7ae9a06f904f6cb21cbe087dd40694`

Both match Render instance `6dxfd` and bridge echo diagnostics. Nested stages
(milliseconds, overlapping/enclosing spans must not be added):

| Stage | SPY | QQQ |
| --- | ---: | ---: |
| Archive read, including metadata/download/validation | 1,161 | 1,118 |
| Historical input load | 2,509 | 2,200 |
| Market classification | 0 (rounded) | 0 (rounded) |
| Width enumeration | 100 | 99 |
| Candidate payoff | 410 | 501 |
| Candidate/economics pipeline | 799 | 798 |
| Response projection | 698 | 1,108 |
| Response serialization | 110 | 94 |
| Backend request total | 6,183 | 6,522 |
| Bridge fetch through headers | 6,794 | 6,799 |
| Bridge body read | 12 | 23 |
| Bridge schema validation | 4 | 6 |

Fetch-through-headers includes connection, transit and backend execution; it is
not an isolated connection-time measurement. Earlier DNS/TCP/TLS measurements,
current strict-freshness acceptance, explicit expiry, pinned detail, simultaneous
requests, and actual cancellation are retained in
[the November 6 report](STRATEGY_RESEARCH_STABILIZATION_2026-11-06.md).
That trial reduced same-archive decoded full/summary payloads by 77–78% and
verified all qualifying candidates and exclusions remained. Current-ready
requests took 4.989–9.573 seconds. Do not relabel these local-bridge measurements
as actual hosted website measurements.

## 3. Known limitations and outstanding acceptance

- Actual Netlify page, Functions configuration/logs and production comparison
  are blocked by owner authentication. Preview deployed SHA remains unknown.
- Fresh current SPY/QQQ research and positive economics for every family/custom
  must be repeated through the hosted workbench during a valid market session.
  November 8 is Sunday; do not bypass freshness to manufacture acceptance.
- Hosted warm current/historical, automatic/explicit expiry, $150 max loss,
  NO TRADE/unavailable rendering, complete schema/body, sorting and shared-evidence
  comparison still require an authenticated preview session and matched logs.
- Source and unit tests show bounded single forwards without retry loops; actual
  Netlify duplicate forwarding or platform rate-limit behavior is unverified.
- Capture each hosted request's status, total time, decoded bytes, application ID,
  Netlify request ID, echoed backend ID, target label, and matching Render stages.
  Retain only sanitized diagnostics. Never record cookie/token/password values.

## 4. Accepted free-tier wake-up behavior

The November 6 idle trial timed out at 12 seconds before either request reached
research execution. Render began a new instance about 9.8 seconds after requests
started; static preparation consumed 12.487 seconds before the port could listen.
This demonstrates platform resume plus process initialization, rather than an
archive or payoff failure. After readiness, simultaneous SPY/QQQ completed in
7.524/9.275 seconds with complete valid bodies.

Keep the existing 12-second complete-response deadline. A sleeping free service
may return `backend_timeout`; retain fail-closed unavailable behavior and allow
an explicit user retry after readiness. No automatic keep-alives, paid plan
change, stale-result reuse, or longer deadline is proposed.

## 5. Netlify configuration verification — owner action required

Both `deploy-preview-87--alphaostrading.netlify.app` and
`deploy-preview-88--alphaostrading.netlify.app` returned HTTP 401 HTML titled
`Login Redirect`, Server Netlify, pointing to `app.netlify.com/edge-access` and
without an application correlation header. This is Netlify access protection
before the app, not evidence that the application generated a 429. The earlier
non-JSON upstream 429 was observed on `alphaos-web-staging.onrender.com`; its
exact source is still unproven. Server labels alone cannot resolve that cause.

Owner steps, preserving production and access protection:

1. Sign in to Netlify and open project **alphaostrading** (site ID
   `6799f0ac-27bd-4828-a8ef-eb3996237c13`). Open **Project configuration >
   Environment variables**. Select **Deploy Previews**, then inspect any
   branch-specific overrides for `feature/alphaos2-multi-strategy-research`
   and `fix/alphaos2-strategy-research-timeout`.
2. Verify preview `ALPHAOS_API_URL` is exactly
   `https://alphaos-api-staging.onrender.com`; `ALPHAOS_API_TOKEN` is the existing
   staging server credential. Verify `ALPHAOS_PASSWORD_HASH` and
   `ALPHAOS_SESSION_KEY` are present and demo mode is false. Compare production's
   non-secret URL and key presence only; never paste secret values into chat.
3. Ensure these server values include the **Functions** scope (covers serverless
   and Edge Functions). Include Builds scope where needed by the framework;
   all-scopes defaults are sufficient where granular scopes are unavailable.
   Runtime scope is not the Edge Functions scope. Do not put secrets/backend
   runtime bindings into `netlify.toml`: its variables are build-time only.
4. Record context, branch, exact deploy SHA and deploy ID. After target verification,
   the previously approved preview publication can proceed. Use combined **#87**
   for workbench acceptance; #88 alone does not contain that UI. Rebuild/deploy
   after environment changes. Preserve normal Netlify access and AlphaOS login.
5. In Functions/Edge logs, match the sanitized `research_bridge` or
   `option_chain_bridge` application ID to Render logs. Establish the actual 429
   origin from matched timestamps/statuses before proposing any rate-limit fix.

Both PR titles retain `[skip netlify]` until target verification. No unknown-target
preview was published. Official references:
[environment variables](https://docs.netlify.com/build/environment-variables/overview/),
[configuration](https://docs.netlify.com/build/environment-variables/get-started/).

## 6. Smallest safe merge sequence — recommendation only

Merge **#88 first, then #87, using merge commits**, after approval and hosted
acceptance. Do not squash/rebase/cherry-pick the overlapping integration.
All #88 functional changes through `b17fa2aa95734689e1f4f8f8dd79a4f2abeb9f89`
are ancestors of #87's deployed integration. The only #88 commit absent from #87
is `e346fb8`, a November 6 report update. Original feature/performance file overlap
is limited to `alphaos_api/app.py` and `modules/research_timing.py`; the existing
integration already reconciles it. REST/MCP full responses remain compatible;
the website explicitly opts into bounded summaries and pinned detail.

Read-only `git merge-tree --write-tree` rehearsal of the current remote heads was
clean (tree `fb016cc33bb3d16ef5a3ccf946d4f492ea68c18d`), differing from deployed
42e4106 only in the November 6 report. Repeat after the release patch. The new
options correlation fix belongs only in #87. No new PR or automatic merge.

## 7. Production rollout procedure — not authorized or executed

First finish the unchecked hosted cases and obtain explicit production/merge
approval. Record the final reviewed merge tree, CI, preview SHA and API deploy.
Capture Netlify's current production deploy ID/SHA and environment metadata;
these are still unknown. Production API baseline was read-only verified as
`ca78291c4d6820d66c03d04be342535aa6e271e4`, deploy
`dep-dblko2utlv9c73c1cj4g`, service `srv-daqillmgekts73ak0mj0`.

Before merging, have the owner control Netlify production publishing (lock the
currently published deploy if appropriate and approved). A main merge can itself
publish a frontend. Deploy the approved additive API integration first, confirm
health and served summary/detail schema, and verify archive integrity/current
freshness without placing orders. Then perform the approved #88 → #87 merge
sequence, validate the final tree/CI, and publish the reviewed Netlify frontend
against the verified production API. Run authenticated warm smoke checks for
both symbols and inspect matching IDs; retain NO TRADE when evidence is absent.
No brokerage execution, database migration, charting work, or paid change is part
of this release.

## 8. Rollback procedure

Under explicit rollout/rollback authorization, republish the captured prior
successful **Netlify frontend first**, then restore the prior API deploy above.
This prevents the new summary/detail UI from calling an older incompatible API.
In Netlify Deploys, open the retained successful deploy and select Publish Deploy;
control auto publishing so a later Git build cannot overwrite the rollback.
In Render's production service Deploys, select the recorded successful artifact
and Rollback, verifying the target before confirmation. If the artifact is no
longer retained, rebuild the approved old SHA instead. Check environment/group
settings separately; an artifact rollback does not restore all platform state.
Verify health, authentication, chains and fail-closed research after rollback.

Official procedures: [Netlify deploy management](https://docs.netlify.com/deploy/manage-deploys/manage-deploys-overview/),
[Render rollbacks](https://render.com/docs/rollbacks). No rollback was triggered.
