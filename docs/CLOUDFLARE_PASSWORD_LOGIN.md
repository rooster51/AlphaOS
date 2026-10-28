# Single-user website login and release gates

This supersedes the Access requirement in the earlier PR #67 preparation.
The new Worker entrypoint enforces a single-user password session before
vinext, including RSC requests, all pages, health, research and legacy API aliases.
The Render website/API and MCP authentication remain unchanged. Cloudflare
Access is optional defense in depth; no Access, OAuth or paid service is needed
for this implementation. No remote configuration or secrets were changed.

## Runtime configuration

Configure separately on the intended **alphaos-web** production version and
Preview. Never place secrets in build variables, client bundles, NEXT_PUBLIC_*,
VITE_*, browser storage, source, PR comments or CI. Existing backend secrets
remain server-side:

| Binding | Type | Purpose |
| --- | --- | --- |
| ALPHAOS_PASSWORD_HASH | secret | bcrypt `$2b$12$...` hash, random salt, cost 12 |
| ALPHAOS_SESSION_KEY | secret | 32 cryptographically random bytes, base64url without padding (43 characters) |
| ALPHAOS_LOGIN_LIMITER | native rate-limit binding | Committed namespace `852671`, 5 login attempts per 60 seconds per location and origin, single-user bucket |
| ALPHAOS_API_URL / ALPHAOS_API_TOKEN | secrets | Existing intended Render backend origin and website bearer token |
| ALPHAOS_DEMO_MODE | text | Committed `false` |

Missing/malformed authentication secrets or limiter make sign-in unavailable;
no valid session is accepted. No development or test bypass exists. Public
endpoints are GET `/login`, POST `/auth/login`, and GET `/robots.txt`; compiled
public static assets contain no research data. Every unauthenticated `/api/*`
request returns 401 before validation or backend access. Health is now protected.

Only native Cloudflare infrastructure performs rate limiting, with no KV,
database, paid auth service or in-process counters. Five attempts includes
successful logins and malformed submissions. Cloudflare's rate limiter is
approximate and per location, **not an account-global brute-force counter**.
IP rotation in one location/origin does not evade the single-user bucket;
distributed locations or distinct version hostnames can multiply the budget.
Origins are isolated so a Preview does not consume production's login bucket.
It can also temporarily lock out the owner.
Do not claim exact global limits. Confirm namespace `852671` does not collide
with another account application before approved upload; change only this
app's namespace if required. See [rate-limit semantics](https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/).

## Offline initial setup — owner only, after authorization

Use a private terminal outside shared recording. From `web`, run:

```sh
node scripts/create-website-auth.mjs <NEW_PRIVATE_FILE_OUTSIDE_REPOSITORY>
```

Windows PowerShell or Command Prompt, from the repository root (Node 24.20.0
is supported for this offline setup tool):

```text
node .\web\scripts\create-website-auth.mjs "%USERPROFILE%\alphaos-website-auth-native.json"
```

The `%USERPROFILE%` form above is for **Command Prompt**. In **PowerShell** use:

```powershell
node .\web\scripts\create-website-auth.mjs "$env:USERPROFILE\alphaos-website-auth-native.json"
```

Use a new private filename outside this checkout and outside synced folders;
the tool intentionally refuses to overwrite an existing file. Enter/paste only
the password, then press Enter for each prompt. Windows now uses the built-in
Windows PowerShell `Read-Host -AsSecureString`, regardless of whether the tool
was launched from PowerShell or Command Prompt. Password characters are never
shown; the native host can show masking asterisks. Node does not use raw mode or
decode Windows keyboard events. There is no visible-input fallback. Buffered
empty Enter/CRLF is ignored and re-prompts; Ctrl+C cancels. Piped input is rejected.

After each input, the only diagnostic is a boolean and UTF-8 byte count, e.g.
`{"inputReceived":true,"byteLength":32}`. No characters, key events, encoded
password, hash or signing key are logged. `false`/`0` means no password was read
and causes a re-prompt; a nonzero count outside 20–72 is rejected. Confirmation
must match exactly, including spaces and Unicode. If troubleshooting is needed,
share only those boolean/count diagnostics, never a password or the output file.

The previous Node raw reader filtered text with Ctrl/Meta flags (including
possible Windows modified-key/AltGr events) and depended on terminal escape
decoding. A valid entered password could consequently be truncated. The prior
tests did not prove every physical Windows keyboard/host configuration. The
native secure prompt removes that path; Unix retains the keypress fallback.

The Windows child command is fixed and contains no password. Its console input
is inherited and its output is captured in private in-memory pipes. Base64 is
used only as pipe framing, not encryption; pipe contents are never forwarded to
the terminal, logs or files. Both processes briefly need password bytes in memory
for hashing; the SecureString/BSTR/byte-buffer resources are disposed/cleared.
No password is passed through command arguments, environment or clipboard reads.
If native secure input fails, the tool stops rather than falling back to visible
input. Built-in Windows PowerShell must be available at its system location;
no PowerShell profile, script file, execution-policy or system setting is changed.

The tool prompts twice without echo, rejects passwords outside 20–72 UTF-8
bytes, creates a bcrypt cost-12 salted hash and independent random signing key,
and writes JSON with only their two binding names. It never prints the password,
hash or key, never accepts a password in arguments/environment, never overwrites
a file, and never deploys. Use a password-manager generated random password;
bcrypt's 72-byte boundary is enforced on setup and login. Do not use test
fixture credentials. No production password/key was generated during this task.

Use a credential-manager/private non-synced location, not OneDrive or this
checkout. Restrict Windows ACLs explicitly: POSIX mode 0600 is not a Windows ACL.
Only the owner should read the file. Add the existing authorized API URL/token
through the private credential workflow, not shell command arguments. Do not
extract existing secret values from Cloudflare or rotate backend credentials.
Securely remove the ephemeral file after the approved upload.

## Sessions and CSRF

Successful sign-in sets `__Host-alphaos_session`, HMAC-SHA256 signed with Web
Crypto, bound to the exact origin, with a random nonce and explicit issue/expiry
times. Cookie flags: **Secure, HttpOnly, SameSite=Strict, Path=/**, no Domain,
Max-Age 2592000 and matching Expires. It survives browser restarts until the
fixed 30-day expiry, unless the browser clears it. No rolling refresh or local
session storage. HTTP redirects to HTTPS except local loopback test servers;
non-loopback HTTP credential submissions are denied.

All non-safe requests require an exact same-origin Origin header and reject
cross-site Fetch Metadata. This includes login, logout, research and comparison
POSTs. Missing/null Origin is rejected; same-site subdomains are insufficient.
The browser supplies Origin naturally; non-browser authenticated callers must
send it explicitly. Render API/MCP callers are unaffected.

`POST /auth/logout` clears the cookie; Sign Out appears in the desktop/mobile
Worker sidebar only. Stateless logout ends that browser's session. It does
**not** revoke a copied/stolen cookie or sessions on other devices. For global
revocation, rotate ALPHAOS_SESSION_KEY. Changing ALPHAOS_PASSWORD_HASH also
invalidates all prior sessions because the hash participates in signing-key
derivation. Replace the secret on the intended target through an explicitly
approved version upload; no grace key is retained. Keep it out of build logs.
Rollback to old authentication secrets can revive old sessions, so never do so
as a code-rollback shortcut. Server-side per-session revocation is not included.

Responses are private/no-store with Vary Cookie and X-Robots-Tag noindex,nofollow;
HTML metadata and robots.txt also discourage indexing. These are preferences,
not authentication. No redirect destination supplied by the client is used.

## First production deployment — still not authorized

Keep PR #67 unmerged. Preserve `alphaos` and its current GitHub integration.
Its main builds fail because main lacks the PR's Cloudflare scripts, not because
`/web` is wrong. Do not retry that integration or use a merge to trigger release.
`alphaos-web` remains the only intended target and has no prior production
version. Use the staged version procedure from
[first production preparation](PR67_FIRST_PRODUCTION_PREPARATION.md), with
these updated gates instead of the old mandatory Access prerequisite:

1. Require passing checks on the approved SHA. Build from `web` in production
   context; verify output name `alphaos-web`, `isPreview=false`, guarded custom
   entrypoint, four secret declarations, limiter and demo false. Keep production
   workers.dev disabled and no new routes/domains. Do not run triggers deploy.
2. Obtain explicit secret/upload authorization. Upload **one undeployed version**
   with all four secrets attached using the pinned command below. The first
   version includes the login gate before any version URL could serve data:

   ```sh
   npm exec -- cf workers versions create --prebuilt --worker alphaos-web --secrets-file <PRIVATE_FILE> --tag <APPROVED_SHA>
   ```

3. Inspect only safe binding metadata; confirm names/types, demo false, target,
   version/tag and absence of a production deployment. Missing secrets must
   prevent sign-in and all protected access. Do not dump full version metadata.
   If upload fails, stop; do not deploy a placeholder or use `secret put`, which
   deploys immediately. No actual first upload was attempted in this task.
4. On the uploaded version URL, anonymously verify page redirects and API 401s
   across aliases, RSC/navigation paths and both symbols. Test real login,
   logout, cross-origin mutation rejection, persistence and forged cookies.
   Through an authenticated session, verify backend binding booleans and live
   SPY/QQQ research/provenance. Keep archive prices explicitly non-executable.
   Check Worker CPU metrics/errors during bcrypt sign-in against the **existing**
   plan limit. Cost-12 hashing is deliberately expensive; local workerd success
   does not prove the Free plan CPU allowance. Do not lower the hash cost or
   upgrade infrastructure automatically. An insufficient allowance is a blocker.
5. Stop for explicit production-deployment authorization. Deploy only the
   inspected version with `cf workers deployments create --worker alphaos-web`
   using the recorded version ID as described in the first-release runbook.
   Routing/public exposure requires separate authorization, even with login.
   Never target `alphaos`, apply account-wide Access, change DNS/OAuth/Render,
   increase the 12-second market deadline or change archive validation.

An automatic Preview rebuild after pushing this PR may lack the two **new**
runtime auth secrets. In that case it intentionally locks protected pages/APIs
and returns sign-in 503; it does not fall back to public access. Configure
Preview secrets separately only with owner authorization. Do not copy production
secrets to Preview. Preview can use a distinct password/key.

Rollback: before first routing, leave a failed version undeployed; preserve the
Render fallback and existing Preview history. There is no prior alphaos-web
production version today. After approved first exposure, restrict only newly
enabled alphaos-web exposure if checks fail; keep authentication enforced.
Never roll back to a public/unguarded artifact or reuse old session secrets.

## Tests and limitations

Actual local results for this implementation: typecheck passed; **189 website
unit tests passed**; production and Preview Worker builds/artifact checks passed,
with **10 runtime tests and 47 browser tests per context**; Next production
build and **45 browser tests passed** (the two Worker-only login tests are
intentionally not applicable to Render); **164 relevant Python integration
tests passed**. Dependency audit found zero vulnerabilities. **23 public assets
per Worker context** passed credential-reference/canary scans. New runtime
secrets were not supplied to a remote Preview or production version, so these
results do not certify the currently deployed Preview's authentication.

Unit, workerd and browser tests cover correct/incorrect password, malformed and
oversized input, 30-day expiry, forged/duplicate/future/wrong-origin cookies,
key/password rotation, configuration/limiter failures, native limiter threshold,
CSRF, API aliases, RSC, no backend call without auth, logout, persisted-cookie
reuse, mobile layout and credential isolation. Browser tests use clearly marked
test-only runtime fixtures via ignored .dev.vars, refuse to overwrite private
files, and clean them up. Production code contains no bypass. Next/Render browser
tests retain the original unauthenticated behavior by design; this is a Worker
website guard, not a Render API or MCP auth migration.

Production remains **NO-GO** until authorized runtime provisioning, actual
uploaded-version end-to-end and CPU/plan checks, and explicit release approval.
Neither local tests nor historical live research certify a deployed auth gate.
