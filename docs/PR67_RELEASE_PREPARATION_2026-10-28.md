# PR #67 release preparation — October 28, 2026

Scope: existing SPY/QQQ website release only. No features, UI redesign, ticker
expansion, production deployment, merge, credentials, DNS, OAuth, Render or paid
infrastructure changes. All times below are point-in-time observations, not
statements that captured prices remain current or executable.

## External check: confirmed failure and exact correction

Cloudflare build `5407476a-b556-4e27-999b-fde717f887c4` on source `7d728e7`
successfully ran `npm run preview:workers`, deployed the existing preview, then
ran `npm run deploy:workers` (`cf deploy --prebuilt`). The cf CLI correctly
refused: **This build output is for a Preview.** The failed external check did
not mean the Preview upload or vinext build failed.

The connected project's PR #67 Preview has its own override, separate from its
Preview defaults. Both non-production scopes were corrected through the Builds
API. Production settings and repository association were compared before/after
and remained unchanged; no environment-variable or credential fields were sent.

| Scope | Root | Build command | Deploy command |
| --- | --- | --- | --- |
| PR #67 Preview override (corrected) | `/web` | `npm ci && npm run cf-typegen && npm run typecheck && npm test` | `npm run preview:workers` |
| Preview defaults (corrected) | `/web` | same checks | `npm run preview:workers` |
| Production (unchanged) | `/web` | `npm ci && npm run cf-typegen && npm run typecheck && npm test && npm run build:vinext && npm run check:workers` | `npm run deploy:workers` |

`preview:workers` builds and deploys in Preview context once. Production output
and deployment remain separate. Do not retry an old build snapshot expecting it
to use new settings: create a new Preview build using the corrected settings.

New external build **`43528f81-bfa0-4750-9284-6da7305227c2` passed** on `7d728e7`.
It deployed Preview `11bd39b8eed648839707a05e6c8adbe5`, deployment
`fa368d2e-9a62-4c59-8829-e2458cd8c932`, at 18:02:56 UTC. The stable working URL
was preserved:
https://codex-cloudflare-workers-alphaos-web.rfroux95.workers.dev

## Naming and production approval boundary

These are two distinct resources, not interchangeable labels:

- **alphaos** (`9570ad252c2f4a36882c9ffedd25fb55`) owns the GitHub build
  integration, production branch `main`, and Builds Preview override
  `c88a8db0fd854a6facad5e4a096629ac` for `codex/cloudflare-workers`.
- **alphaos-web** (`3610253e028a4a2fb3e31cf1e7dff339`) is the explicit target in
  `web/cloudflare.config.ts`. The successful cf Preview command deploys to this
  resource's existing PR Preview `11bd39b8eed648839707a05e6c8adbe5`.

The Preview deploy proves the actual Preview target. It does not approve a
production resource migration or make a production deployment under either
name. `alphaos-web` has no production deployment; `alphaos` retains its prior
production deployment timestamp. Neither has a custom domain attached, and both
production workers.dev endpoints are disabled. These production settings were
not changed. Do not rename the source Worker merely to silence the naming
mismatch: that would change the working Preview target.

Before any production-triggering merge, the owner must approve **alphaos-web**
as the production target and reconcile the build integration/target ownership
or explicitly approve this orchestration arrangement. The existing main trigger
has a production deploy command, so merging is a release action, not a harmless
way to test the configuration. No automatic merge or production release is
authorized by a green Preview check.

## Automated checks rerun

Using Node 22.23.0 and the pinned adapter/runtime:

- Typecheck and generated runtime/route types: PASS.
- Website unit tests: **182 passed**.
- Next production build + browser suite: PASS, **45 browser tests**.
- Production Worker build, artifact checks, runtime/browser suites: PASS,
  **7 runtime tests + 45 browser tests**.
- Preview Worker build, artifact checks, runtime/browser suites: PASS,
  **7 runtime tests + 45 browser tests**.
- Credential canary scans: **23 public assets per context**, PASS.
- Dependency audit: **0 vulnerabilities**.
- Relevant Python integration tests under pytest 9.2: **187 passed**.

The application code remains `7d728e7`; subsequent release documentation commits
do not alter the tested code or scripts. Final-head GitHub Actions and external
Cloudflare build results are recorded in PR #67 before handoff. Test fixtures
are not evidence of live quote quality; live checks below are independent.

## Live SPY/QQQ research and provenance

The live backend now exposes `StructureLeg.contract` and
`StructureRequest.market_data`, and actual reference-pinned requests succeed.
This supersedes the earlier missing-contract observation. **No Render change
was made by this release-preparation work.**

At approximately 14:00–14:08 EDT, both Render and the actual Cloudflare Preview
returned successful research for each symbol and each exact expiration:

| Horizon | Exact expiration | SPY preview market | QQQ preview market |
| --- | --- | --- | --- |
| 0DTE | 2026-10-28 | 200 / 5,469 ms | 200 / 4,406 ms |
| Weekly | 2026-10-30 | 200 / 5,547 ms | 200 / 6,141 ms |
| Monthly | 2026-11-20 | 200 / 4,062 ms | 200 / 6,078 ms |
| Long-dated | 2027-12-17 | 200 / 2,907 ms | 200 / 2,672 ms |

The unchanged market budget is 12,000 ms. These are warm request measurements;
they do not remove the documented Render Free cold-start availability risk.

Live validation covered all existing 11 representations for both symbols and
four horizons: long calls/puts, both debit and credit verticals, symmetric
call/put butterflies, bullish/bearish broken-wing butterflies, and iron condors.

- **88 observed-price hypothetical cases** passed through Render and Preview,
  preserving their hypothetical labeling and independent payoff economics.
- **88 archive-reference-pinned cases / 176 API+Preview evaluations** also
  passed with `kind=verified_archive`, `verified=true`, and explicitly
  **`verified_for_trading=false`**. No winner or recommendation was returned.
- Checks matched contract, type, strike, quantity, expiration, bid/ask and both
  timestamps across archive observations, evidence, trade/position/payoff legs
  and comparison projections. Max profit/loss, cashflow, capital at risk,
  breakevens and return on risk matched independent payoff checks and each other.
- Archive ages at evaluation were **76.2–134.0 seconds** under the 600-second
  policy; selected bid/ask ages were **76.9–147.8 seconds** under 900 seconds.
- Read-only Supabase metadata independently matched the snapshot IDs and SHA-256:
  SPY `65ba0db4-9a43-46cd-9226-985e05507082` /
  `5477ef6cb0521a6fb5f5a2c6b9028d7787b0238e8e9c1c5c9fcbe36d0e73e18b`;
  QQQ `71d73a04-e07a-4a5d-a623-9e1e63ecdbf4` /
  `b8ee9d76b3418825fa33b5f7ac7d8a7706eda50b8cd36c8996c7c4e33882c01c`.
  Both records were complete, observed at 18:01:46 / 18:01:50 UTC.

The audit derived package cashflow from actual archived buy-ask/sell-bid prices,
with explicitly zero-fee test scenarios. It did not fabricate contracts,
premiums, fees paid, fills, POP or EV. Quote verification is archive source and
freshness verification, **not verified live executable pricing**. Hypothetical
inputs were not promoted to verified evidence. Full raw responses stay ignored
locally rather than being committed as current trading data.

Actual browser checks passed for SPY/QQQ market research, manual structures,
saved comparison, desktop/mobile navigation and archive-backed structure forms.
Both verified forms displayed **VERIFIED ARCHIVE** together with **not executable
fills**, matching snapshot references and `verified_for_trading=false`.
There were no page errors or integrity warnings. Browser research requests had
no API Authorization header; server-side credentials remained server-side.

Live negative checks for both symbols:

| Input/error | Render | Preview |
| --- | --- | --- |
| Bad snapshot checksum | 422 `archive_snapshot_mismatch` | 502 same code, no research |
| Client-supplied quote injection | 422 validation rejection | 400 validation rejection |
| Missing direct API authentication | 401 | credential forwarding tested by successful protected requests |

Automated Worker/route tests additionally cover stale/dropped evidence,
missing bindings, authentication rejection, backend errors, timeouts and schema
mismatch. No live archive was corrupted, service restarted or clock altered to
induce those cases. No stale/archive-only data is described as an executable
quote. Existing calibrated-evidence limitations remain unchanged.

## Production deployment plan — requires explicit approval

1. Approve the intended `alphaos-web` production target and the GitHub integration
   arrangement. Keep automatic production release gated while reconciling names.
   Record the reviewed main/PR SHA and existing deployment/version metadata.
2. Confirm production runtime binding **presence**, directly through the approved
   secret manager/dashboard, for `ALPHAOS_API_URL` and `ALPHAOS_API_TOKEN`.
   Keep `ALPHAOS_DEMO_MODE=false`. Do not expose/copy values into a PR or build log;
   Preview bindings do not establish production binding readiness.
3. Require passing standard and both Workers-context checks on the reviewed SHA.
   Only after separate release approval, merge PR #67 and build merged `main`
   from root `web` with the production command in the table. Validate output is
   production context, Worker name `alphaos-web`, and public assets are clean.
4. Run **one** approved production `npm run deploy:workers` against that production
   artifact. Never reuse Preview output. Do not change DNS, OAuth, Render, data
   collectors or provider credentials in this release.
5. Smoke-test health/configuration booleans, SPY/QQQ current research, exact
   expirations, pinned provenance/comparison, unavailable-data responses and
   credential isolation. Stop on source mismatch, data leakage, failed auth or
   unexpected executable-price claims. Observe cold and warm behavior using the
   existing deadline; do not fix unavailability by inventing data or increasing it.

## Rollback and remaining gates

- Keep the current working Preview and its deployment history. A Preview issue
  is handled within that Preview; it is never remedied by deploying it as production.
- Keep the Render website and backend unchanged as the existing fallback. No
  DNS cutover occurs here, so existing Render entrypoints remain available.
- If a prior `alphaos-web` production version exists at approved release time,
  record it first and use Cloudflare's deployment rollback to that retained
  version if smoke tests fail. **Currently there is no prior production version**;
  a first release cannot pretend to have one. In that case stop exposure of the
  new Worker through the approved release procedure and retain Render access.
- Do not delete/rename `alphaos`, rotate credentials, disable freshness gates,
  change OAuth, or alter the Render backend as a rollback shortcut. A code
  rollback does not itself restore changed secrets or repair a stale feed.
- Remaining approval gates: production naming/integration ownership, production
  runtime binding confirmation, and acceptance or separate remediation of the
  documented Free-backend cold-start risk. These are not failing Preview builds.

Release preparation is technically green on the tested Preview. PR #67 stays
open and unmerged; a production-triggering merge/deployment still requires the
explicit production approvals above.
