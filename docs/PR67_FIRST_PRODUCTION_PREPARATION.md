# PR #67: first production deployment preparation

**Authentication update:** [Password-login runbook](CLOUDFLARE_PASSWORD_LOGIN.md)
supersedes the historical Access requirement below. The guarded Worker version
and its four runtime secrets must pass that runbook's release gates. Historical
anonymous Preview results here describe the earlier unguarded code only.

Status: **NO-GO for production**. Read-only inspection and local tests on
2026-10-28. No production upload, secret write, deployment, routing, Access,
GitHub integration, DNS, OAuth or Render change was performed. PR remains draft
and unmerged. This runbook supersedes the earlier report's generic first-deploy
instructions; technical Preview success does not establish private access.

## Confirmed production build failure

Production build `f8e635de-9ce7-4a8d-8226-6f1417bfa9e0` (18:25–18:28 UTC)
uses branch `main`, root `/web`, and the PR's Cloudflare build command. Its retry
metadata has an empty commit hash. The original main push build
`c13a51f2-5a46-4fbd-a823-c5f2adfa3a04` explicitly identifies commit
`0c2a4b38eb08129b42de27c2c6689991e606a1f2` and has the same failure.
Both logs show successful `npm ci` (115 packages), followed by
`Missing script: "cf-typegen"`. That commit's `web/package.json` contains Next.js
scripts but **none** of `cf-typegen`, `build:vinext`, `check:workers` or
`deploy:workers`. They exist only on the unmerged PR branch.

The cause is **production commands configured ahead of their source revision**,
not evidence of an incorrect working directory. The repository root has no
package.json; npm successfully finding/installing the web package further
supports the `/web` setting. Do not retry this main build or change directories
to remedy a missing script. Do not merge merely to make that build run.

## Verified identities and unchanged resources

| Resource | Identity | Observed state |
| --- | --- | --- |
| GitHub | `rooster51/AlphaOS`, PR #67, `codex/cloudflare-workers` | Open, draft, unmerged; reviewed source `f741bad06fb4d693def5b08267b54d272caf3dee` |
| `alphaos` | `9570ad252c2f4a36882c9ffedd25fb55` | Owns main production Git integration and Preview build orchestration; production last deployed 2026-10-27 03:21:33 UTC |
| `alphaos-web` | `3610253e028a4a2fb3e31cf1e7dff339` | `web/cloudflare.config.ts` and output target; zero production versions, `deployed_on=null`; no Builds integration (404) |
| Working Preview | `codex-cloudflare-workers-alphaos-web.rfroux95.workers.dev` | Preserved; anonymous `/market` returns 200 |

Both Workers' production workers.dev endpoints remain disabled; neither lists
custom domains or other Worker references. This is routing state, **not auth**.
Build environment secrets on `alphaos` and runtime Preview secrets on
`alphaos-web` are separate from production runtime bindings. Secret names and
types can be inspected; values must never be logged or copied into reports.
No production runtime version exists on which to confirm binding presence.

Do not rename/delete/replace/deploy `alphaos`, reconnect its repository, reuse
its production build trigger, or select it as the deployment target. Preserve
its Preview defaults and PR override. A future main merge is separately blocked:
its existing automatic production integration would run the deployment command.
This preparation does not authorize changing that integration or merging.

## Authentication: failed release gate

`GET /accounts/<account>/access/apps` returns 403,
`access.api.error.not_enabled`: **Access is not enabled**. The connector already
has the accepted Access scopes; reconnecting is not the remedy. Source review
finds no visitor session/JWT/Access enforcement. Anonymous probes return:

- `/market`: 200 HTML, no Access redirect.
- `POST /api/research/market` with `{}`: 400 application validation, no Access
  redirect. This reaches the app without visitor authentication.

The website's server-to-Render bearer token authenticates the proxy to Render;
it does not authenticate website visitors. Account/journal features being
disabled is also not an access control. Existing Preview checks did not test
visitor authentication. Production private-access tests cannot pass before
Access exists and an approved candidate can be tested.

After explicit owner approval, enable Zero Trust as necessary and protect
**only `alphaos-web`**, using its Worker Access tab, **All traffic**, and an
owner-approved restrictive allow policy. The documented API destination is
`{ "type": "worker", "worker_id": "3610253e028a4a2fb3e31cf1e7dff339" }`.
Avoid account-wide protection, which would change other Workers. Do not select
`Previews only`, allow everyone, add bypass policies, or change MCP OAuth.
Worker-scoped protection covers production, previews, routes and associated
hostnames; this will intentionally add login to Preview after separate approval.

Verify anonymous and disallowed users are redirected/denied for `/`, `/market`,
`/structures`, `/api/health`, all `/api/research/*`, and legacy API aliases.
Repeat with forged Access headers/cookies and every version/alias URL. Confirm
an allowed user can reach research; no alternate hostname or path bypasses it.
Authentication must precede even an upload if upload creates a version URL.
If Access cannot be enabled without an unapproved plan/OAuth change, stop.

## Exact staged procedure — requires separate authorizations

None of the remote mutation commands below was run. CLI syntax was checked
against pinned `cf@1.0.0-beta.23`; version-upload documentation confirms it
does not create a production deployment. Upload can create routable version
URLs, so the authentication gate above must be satisfied first.

1. Obtain approval for Worker-scoped Access and its allowed identities, then
   verify it. Separately obtain approval to upload production secrets/code,
   and later approval to create a deployment. Do not change `alphaos` or merge.
2. Use a clean checkout of the exact owner-approved PR/release SHA. Record SHA,
   account and Worker ID. Use Node 22.23.0 and root `web`; remove Preview CI
   context (`CLOUDFLARE_PREVIEW_BUILD`) before building. Do not inherit runtime
   research credentials as build variables. Use the existing account's approved
   deployment credential; do not use `alphaos`'s Builds job/token.
3. Run locally, without production API credentials:

   ```sh
   npm ci
   npm run cf-typegen
   npm run typecheck
   npm test
   npm run build:vinext
   npm run check:workers
   npm run test:workers
   # Set ALPHAOS_TEST_WORKERS=true for the next command.
   npm run test:e2e
   ```

   Inspect `.cloudflare/output/v0/config.json`: `buildContext.isPreview=false`.
   Inspect `workers/default/worker.config.json`: name is exactly `alphaos-web`,
   both required bindings are secret declarations and demo text is `false`.
   Check public assets for credential leakage. Do not reuse Preview artifacts.
4. Only after explicit secret/upload authorization, have the credential owner
   provide the existing intended backend URL and bearer credential through an
   access-restricted, ephemeral JSON/.env file **outside the repository**. The
   file must contain only `ALPHAOS_API_URL` and `ALPHAOS_API_TOKEN`; never put
   values on the command line, in shell history, logs, build variables or PRs.
   Supply `ALPHAOS_DEMO_MODE=false` from the committed text binding, not a
   conflicting secret. Use the installed pinned CLI:

   ```sh
   npm run upload:workers -- --secrets-file <PRIVATE_FILE_PATH> --tag <APPROVED_SHA>
   ```

   This uploads code and secrets together as an **undeployed** version, avoiding
   dashboard's missing-production-version dependency. Do not use dashboard
   **Deploy**, `wrangler secret put`, `cf deploy`, or a placeholder first deploy
   to unlock settings. Securely discard the ephemeral file after upload. Do
   not copy any existing secret out of Cloudflare; use the credential owner.
5. Read back version metadata safely, projecting only binding names/types and
   demo's non-secret false value. Assert target ID, version ID, tag, secret
   presence, production context, and that production `deployed_on` is still
   null. Do not dump full version metadata (it can include asset tokens).
   Enumerate returned version URLs and test Access before any research probe;
   under an allowed session test health binding booleans and SPY/QQQ research.
   If first-version upload is rejected, stop with the exact error; do not fall
   back to an immediate deployment. This remote path is not yet executed.
6. Stop for deployment approval. Keep workers.dev disabled, no custom domains,
   no DNS changes. Only after that approval, deploy the recorded version:

   ```sh
   npm exec -- cf workers deployments create --worker alphaos-web --strategy percentage --versions '[{"version_id":"<APPROVED_VERSION_ID>","percentage":100}]'
   ```

   This selects one existing version and does not apply routing triggers. Do
   not run `cf workers triggers deploy` or the `alphaos` production build.
   Enabling any production route requires its own approval and Access tests;
   a deployment with disabled routing is not a publicly launched website.
7. Under authenticated access validate SPY/QQQ current archive freshness,
   pinned contract/quote provenance, structures/comparison, error handling,
   absent browser credentials and `verified_for_trading=false`. Archived
   bid/ask observations are not executable fills. Retain the 12-second market
   deadline and fail closed on unavailable/stale/unverified data.

## Rollback and stop conditions

Before any approved action, capture safe target/version/routing metadata for
both Workers and record the unchanged Preview. `alphaos-web` has **no previous
production version**; there is no valid previous-version rollback today.
Before routing approval, a failed candidate stays undeployed and inaccessible
except through verified Access; no routing cutover needs undoing. After a first
deployment/exposure, use an owner-approved restriction of **only newly enabled
alphaos-web exposure**, retaining Access and the existing Render entrypoint.
Do not delete either Worker, change `alphaos`, disable Access/freshness, expose
secrets, change Render/DNS/OAuth or claim that code rollback restores secrets.
Do not bypass platform deployment checks. Once a known-good production version
exists, record it and use an approved version deployment rollback.

Remaining gates: owner-approved Access/policy and successful private-access
tests; explicit secret/upload authorization; successful undeployed-version
binding and research verification; deployment/routing authorization; separate
resolution of future main auto-deploy ownership without changing `alphaos`
implicitly. Existing Render cold-start availability risk remains unchanged.

## Actual local verification in this preparation

- Typecheck: passed; website units: **182 passed**.
- Production Worker build/artifact check: passed; runtime tests: **7 passed**.
- Production Worker browser suite: **45 passed**.
- Python provenance, entry evidence, combined integration, structure research
  and website/MCP parity: **164 passed**. An initial invocation named a
  nonexistent test file and collected no tests; corrected invocation passed.
- No application code, schemas, strategies, tests, credentials or infrastructure
  was changed. Earlier live 88-case validation is recorded in the prior report;
  it was not rerun or reclassified as live executable pricing here.

References: [cf staged version upload](https://developers.cloudflare.com/cf/projects/),
[Worker-scoped Access](https://developers.cloudflare.com/workers/configuration/cloudflare-access/),
[secret deployment semantics](https://developers.cloudflare.com/workers/configuration/secrets/).
