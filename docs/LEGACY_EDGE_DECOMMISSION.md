# Legacy edge-hosting decommissioning

Repository cleanup is complete. The website is deployed by Netlify, the API by
Render and archive storage by Supabase. The external integration below is still
owned by the repository/account owner and must be disconnected separately.

This runbook covers only the retired Cloudflare Workers and Pages integration.
Do not change DNS, zones, other Workers or Pages projects, R2/D1 resources,
unrelated API tokens, or any other Cloudflare service.

## Observed integration

| Item | Value |
| --- | --- |
| GitHub App | Cloudflare Workers and Pages |
| App slug | `cloudflare-workers-and-pages` |
| App ID | `85455` |
| Build check | `Workers Builds: alphaos` |
| Check suite observed during removal | `116014287546` |

The repository has no branch protection or ruleset that requires this check.
Historical commits may retain the check result; new commits should not receive
one after the app is disconnected.

## 1. Disconnect the GitHub App

1. Sign in as the repository or organization owner.
2. Open repository **Settings → GitHub Apps** (or organization **Settings →
   GitHub Apps → Configure**).
3. Open **Cloudflare Workers and Pages** and remove its access to `rooster51/AlphaOS`,
   or uninstall the app if it is used only for this repository.
4. Do not remove unrelated GitHub Apps or Actions integrations.

If the app was installed organization-wide, remove only this repository from its
installation first. Uninstall the app only after confirming no other repository
depends on it.

## 2. Remove the `alphaos` Workers Builds integration

1. In the Cloudflare dashboard, open **Workers & Pages → `alphaos`**.
2. Open **Settings → Builds & deployments** (labels may vary slightly).
3. Disconnect the Git integration and delete the build configuration for
   `alphaos`.
4. Do not delete unrelated Workers, Pages projects, DNS records, zones, R2
   buckets or D1 databases while doing this.

Deleting the build integration stops new Cloudflare builds. It does not remove
the repository code, and it does not by itself delete an already-deployed
Cloudflare resource. Review any remaining deployed resource separately; this
cleanup intentionally makes no Cloudflare control-plane change.

## 3. Revoke obsolete credentials

- In Cloudflare **My Profile → API Tokens**, revoke only tokens that were created
  for this Workers Builds integration. Do not revoke tokens used by other
  services.
- In GitHub **Settings → Secrets and variables → Actions**, delete retired
  Cloudflare build secrets if they exist, for example `CLOUDFLARE_API_TOKEN` and
  `CLOUDFLARE_ACCOUNT_ID`. Never print, paste or commit secret values.
- Remove any local `.dev.vars` or `.env` Cloudflare build entries after
  confirming they are not used by another local tool. Keep those files
  untracked.
- Revoke any legacy Cloudflare API key or build hook that is no longer referenced
  by an active service.

## Verification

After the owner completes the steps above:

1. Push a new commit or re-run the PR checks.
2. Confirm the new commit no longer reports `Workers Builds: alphaos`.
3. Confirm the `tests` workflow still passes, including the deployment-boundary
   job.
4. Confirm Netlify still builds the website, Render still serves `/health`, and
   Supabase archive reads remain unchanged.

The repository guard is:

```sh
python scripts/check_deployment_boundary.py
```

It rejects active Cloudflare, Wrangler, vinext and workerd deployment artifacts
while exempting `docs/validation/` historical evidence, the retired SPY/QQQ
validation record, this runbook, and the guard's own test files.
